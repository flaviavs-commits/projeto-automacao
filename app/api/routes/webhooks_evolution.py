from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.webhook_evolution import EvolutionWebhookEnvelope
from app.services.customer_identity_service import CustomerIdentityService
from app.workers.tasks import process_incoming_message


router = APIRouter(prefix="/webhooks/evolution", tags=["webhooks"])
logger = get_logger(__name__)


def _to_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _normalize_whatsapp_jid(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    normalized = raw_value
    lowered = normalized.lower()
    for suffix in ("@s.whatsapp.net", "@c.us"):
        if lowered.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break

    digits = "".join(ch for ch in normalized if ch.isdigit())
    return digits or normalized


def _extract_text_content(message_payload: dict) -> str | None:
    conversation_text = str(message_payload.get("conversation") or "").strip()
    if conversation_text:
        return conversation_text

    extended_text_message = _to_dict(message_payload.get("extendedTextMessage"))
    extended_text = str(extended_text_message.get("text") or "").strip()
    if extended_text:
        return extended_text
    return None


def _extract_evolution_messages(envelope_payload: dict) -> list[dict]:
    extracted: list[dict] = []
    data_payload = envelope_payload.get("data")

    rows: list[dict] = []
    if isinstance(data_payload, dict):
        rows = [data_payload]
    elif isinstance(data_payload, list):
        rows = [item for item in data_payload if isinstance(item, dict)]

    for item in rows:
        key_payload = _to_dict(item.get("key"))
        from_me = bool(key_payload.get("fromMe"))
        if from_me:
            continue

        remote_jid = str(key_payload.get("remoteJid") or item.get("remoteJid") or "").strip()
        platform_user_id = _normalize_whatsapp_jid(remote_jid)
        if not platform_user_id:
            continue

        message_payload = _to_dict(item.get("message"))
        text_content = _extract_text_content(message_payload)
        if not text_content:
            continue

        external_message_id = str(key_payload.get("id") or item.get("id") or "").strip()
        profile_name = str(item.get("pushName") or item.get("senderName") or "").strip() or None

        extracted.append(
            {
                "platform": "whatsapp",
                "platform_user_id": platform_user_id,
                "profile_name": profile_name,
                "external_message_id": external_message_id or None,
                "message_type": "text",
                "text_content": text_content,
                "media_url": None,
                "phone_number_id": None,
                "raw_payload": item,
            }
        )
    return extracted


def _get_or_create_open_conversation(
    db: Session,
    contact_id,
    platform: str,
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.contact_id == contact_id,
            Conversation.platform == platform,
            Conversation.status == "open",
        )
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if conversation is None:
        conversation = Conversation(
            contact_id=contact_id,
            platform=platform,
            status="open",
        )
        db.add(conversation)
        db.flush()
    return conversation


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def receive_evolution_webhook(
    envelope: Annotated[
        EvolutionWebhookEnvelope,
        Body(
            examples=[
                {
                    "event": "messages.upsert",
                    "data": {
                        "key": {
                            "id": "ABCD123",
                            "remoteJid": "5511999999999@s.whatsapp.net",
                            "fromMe": False,
                        },
                        "pushName": "Cliente",
                        "message": {"conversation": "Oi"},
                    },
                }
            ]
        ),
    ],
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    envelope_payload = envelope.model_dump(mode="json")
    event_name = str(envelope_payload.get("event") or "").strip().lower()
    if event_name != "messages.upsert":
        return {
            "status": "accepted",
            "event": envelope_payload.get("event"),
            "messages_detected": 0,
            "messages_created": 0,
            "messages_duplicated": 0,
            "messages_queued": 0,
            "ignored_reason": "unsupported_event",
        }

    extracted_messages = _extract_evolution_messages(envelope_payload)
    now_utc = datetime.now(timezone.utc)
    created_messages_count = 0
    duplicate_messages_count = 0
    queued_messages_count = 0
    queued_task_payloads: list[dict] = []

    db.add(
        AuditLog(
            entity_type="webhook",
            event_type="evolution_webhook_received",
            details={
                "path": str(request.url.path),
                "event": envelope_payload.get("event"),
                "messages_detected": len(extracted_messages),
                "payload": envelope_payload,
            },
        )
    )

    for item in extracted_messages:
        platform_user_id = str(item.get("platform_user_id") or "").strip()
        if not platform_user_id:
            continue

        external_message_id = item.get("external_message_id")
        if external_message_id:
            already_exists = (
                db.query(Message)
                .filter(Message.external_message_id == external_message_id)
                .first()
            )
            if already_exists is not None:
                duplicate_messages_count += 1
                continue

        contact = CustomerIdentityService().resolve_or_create_contact(
            db=db,
            platform=item.get("platform", "whatsapp"),
            platform_user_id=platform_user_id,
            profile_name=item.get("profile_name"),
        )
        conversation = _get_or_create_open_conversation(
            db=db,
            contact_id=contact.id,
            platform=item.get("platform", "whatsapp"),
        )
        conversation.last_message_at = now_utc

        message = Message(
            conversation_id=conversation.id,
            platform=item.get("platform", "whatsapp"),
            direction="inbound",
            message_type=item.get("message_type", "unknown"),
            external_message_id=external_message_id or None,
            text_content=item.get("text_content"),
            media_url=item.get("media_url"),
            raw_payload={
                **_to_dict(item.get("raw_payload")),
                "_phone_number_id": item.get("phone_number_id"),
            },
            ai_generated=False,
        )
        db.add(message)
        db.flush()
        created_messages_count += 1

        queued_task_payloads.append(
            {
                "message_id": str(message.id),
                "conversation_id": str(conversation.id),
                "contact_id": str(contact.id),
                "customer_id": contact.customer_id,
                "platform": message.platform,
                "message_type": message.message_type,
                "external_message_id": message.external_message_id,
                "phone_number_id": item.get("phone_number_id"),
            }
        )

    db.commit()

    logger.info(
        "evolution_webhook_received",
        extra={
            "path": str(request.url.path),
            "event": envelope_payload.get("event"),
            "messages_detected": len(extracted_messages),
            "messages_created": created_messages_count,
            "messages_duplicated": duplicate_messages_count,
        },
    )

    for payload in queued_task_payloads:
        try:
            process_incoming_message.delay(payload)
            queued_messages_count += 1
        except Exception:
            logger.exception(
                "evolution_webhook_queue_failed",
                extra={
                    "path": str(request.url.path),
                    "message_id": payload.get("message_id"),
                },
            )

    return {
        "status": "accepted",
        "event": envelope_payload.get("event"),
        "messages_detected": len(extracted_messages),
        "messages_created": created_messages_count,
        "messages_duplicated": duplicate_messages_count,
        "messages_queued": queued_messages_count,
    }
