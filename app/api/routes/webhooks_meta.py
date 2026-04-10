from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import safe_compare
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.webhook import MetaWebhookEnvelope
from app.workers.tasks import process_incoming_message


router = APIRouter(prefix="/webhooks/meta", tags=["webhooks"])
logger = get_logger(__name__)


def _to_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _extract_whatsapp_messages(envelope_payload: dict) -> list[dict]:
    extracted: list[dict] = []

    for entry in envelope_payload.get("entry", []):
        if not isinstance(entry, dict):
            continue

        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue

            value = _to_dict(change.get("value"))
            if not value:
                continue

            metadata = value.get("metadata")
            phone_number_id = None
            if isinstance(metadata, dict):
                phone_number_id = str(metadata.get("phone_number_id") or "").strip() or None

            messages = value.get("messages") or []
            if not isinstance(messages, list):
                continue

            contacts = value.get("contacts") or []
            contacts_by_wa_id: dict[str, dict] = {}
            if isinstance(contacts, list):
                for contact in contacts:
                    if not isinstance(contact, dict):
                        continue
                    wa_id = str(contact.get("wa_id") or "").strip()
                    if wa_id:
                        contacts_by_wa_id[wa_id] = contact

            for message in messages:
                if not isinstance(message, dict):
                    continue

                wa_id = str(message.get("from") or "").strip()
                external_message_id = str(message.get("id") or "").strip()
                message_type = str(message.get("type") or "unknown")
                type_payload = message.get(message_type)
                if not isinstance(type_payload, dict):
                    type_payload = {}

                text_payload = message.get("text")
                text_content = None
                if isinstance(text_payload, dict):
                    text_content = text_payload.get("body")

                media_url = type_payload.get("link") or type_payload.get("id")
                contact_payload = contacts_by_wa_id.get(wa_id, {})
                profile_payload = contact_payload.get("profile")
                profile_name = None
                if isinstance(profile_payload, dict):
                    profile_name = profile_payload.get("name")

                extracted.append(
                    {
                        "platform": "whatsapp",
                        "wa_id": wa_id,
                        "profile_name": profile_name,
                        "external_message_id": external_message_id,
                        "message_type": message_type,
                        "text_content": text_content,
                        "media_url": str(media_url) if media_url else None,
                        "phone_number_id": phone_number_id,
                        "raw_payload": message,
                    }
                )

    return extracted


def _get_or_create_contact(db: Session, wa_id: str, profile_name: str | None) -> Contact:
    contact = db.query(Contact).filter(Contact.phone == wa_id).first()
    if contact is None:
        contact = Contact(phone=wa_id, name=profile_name)
        db.add(contact)
        db.flush()
        return contact

    if profile_name and not contact.name:
        contact.name = profile_name
    return contact


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


@router.get("")
def verify_meta_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> str:
    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hub.mode",
        )

    if not safe_compare(hub_verify_token, settings.meta_verify_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verification token",
        )

    return hub_challenge


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def receive_meta_webhook(
    envelope: Annotated[
        MetaWebhookEnvelope,
        Body(
            examples=[
                {
                    "object": "page",
                    "entry": [
                        {
                            "id": "1234567890",
                            "time": 1710000000,
                            "changes": [
                                {
                                    "field": "messages",
                                    "value": {
                                        "messaging_product": "whatsapp",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        ),
    ],
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    if not settings.meta_enabled:
        logger.info(
            "meta_webhook_ignored",
            extra={
                "path": str(request.url.path),
                "environment": settings.app_env,
                "reason": "meta_disabled",
            },
        )
        return {
            "status": "accepted",
            "object": envelope.object,
            "messages_detected": 0,
            "messages_created": 0,
            "messages_duplicated": 0,
            "messages_queued": 0,
            "ignored_reason": "meta_disabled",
        }

    envelope_payload = envelope.model_dump(mode="json")
    extracted_messages = _extract_whatsapp_messages(envelope_payload)
    now_utc = datetime.now(timezone.utc)
    created_messages_count = 0
    duplicate_messages_count = 0
    queued_messages_count = 0
    queued_task_payloads: list[dict] = []

    db.add(
        AuditLog(
            entity_type="webhook",
            event_type="meta_webhook_received",
            details={
                "object": envelope.object,
                "entries_count": len(envelope_payload.get("entry", [])),
                "messages_detected": len(extracted_messages),
                "payload": envelope_payload,
            },
        )
    )

    for item in extracted_messages:
        wa_id = item.get("wa_id")
        if not wa_id:
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

        contact = _get_or_create_contact(
            db=db,
            wa_id=wa_id,
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
                "platform": message.platform,
                "message_type": message.message_type,
                "external_message_id": message.external_message_id,
                "phone_number_id": item.get("phone_number_id"),
            }
        )

    db.commit()

    logger.info(
        "meta_webhook_received",
        extra={
            "path": str(request.url.path),
            "environment": settings.app_env,
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
                "meta_webhook_queue_failed",
                extra={
                    "path": str(request.url.path),
                    "message_id": payload.get("message_id"),
                },
            )

    return {
        "status": "accepted",
        "object": envelope.object,
        "messages_detected": len(extracted_messages),
        "messages_created": created_messages_count,
        "messages_duplicated": duplicate_messages_count,
        "messages_queued": queued_messages_count,
    }
