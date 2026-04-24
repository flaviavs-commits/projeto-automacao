from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.webhook_evolution import EvolutionWebhookEnvelope
from app.services.webhook_ingestion_service import WebhookIngestionService, to_payload_dict
from app.workers.tasks import process_incoming_message


router = APIRouter(prefix="/webhooks/evolution", tags=["webhooks"])
logger = get_logger(__name__)


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

    extended_text_message = to_payload_dict(message_payload.get("extendedTextMessage"))
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
        key_payload = to_payload_dict(item.get("key"))
        from_me = bool(key_payload.get("fromMe"))
        if from_me:
            continue

        remote_jid = str(key_payload.get("remoteJid") or item.get("remoteJid") or "").strip()
        platform_user_id = _normalize_whatsapp_jid(remote_jid)
        if not platform_user_id:
            continue

        message_payload = to_payload_dict(item.get("message"))
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
    queued_messages_count = 0
    ingestion_result = WebhookIngestionService().persist_inbound_messages(
        db=db,
        extracted_messages=extracted_messages,
        audit_event_type="evolution_webhook_received",
        audit_details={
            "path": str(request.url.path),
            "event": envelope_payload.get("event"),
            "payload": envelope_payload,
        },
    )
    created_messages_count = int(ingestion_result.get("messages_created") or 0)
    duplicate_messages_count = int(ingestion_result.get("messages_duplicated") or 0)
    queued_task_payloads = ingestion_result.get("queued_task_payloads") or []

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
