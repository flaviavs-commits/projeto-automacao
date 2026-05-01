from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import get_logger
from app.schemas.webhook_evolution import EvolutionWebhookEnvelope
from app.services.whatsapp_jid_utils import isGroupJid
from app.services.webhook_ingestion_service import WebhookIngestionService, to_payload_dict
from app.workers.tasks import process_incoming_message

router = APIRouter(tags=["webhooks"])
logger = get_logger(__name__)

_WHATSAPP_NUMERIC_JID_SUFFIXES = ("@s.whatsapp.net", "@c.us")
_WHATSAPP_LID_SUFFIX = "@lid"


def _normalize_whatsapp_jid(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    lowered = raw_value.lower()
    for suffix in _WHATSAPP_NUMERIC_JID_SUFFIXES:
        if lowered.endswith(suffix):
            normalized = raw_value[: -len(suffix)]
            digits = "".join(ch for ch in normalized if ch.isdigit())
            return digits or normalized

    if lowered.endswith(_WHATSAPP_LID_SUFFIX):
        normalized = raw_value[: -len(_WHATSAPP_LID_SUFFIX)]
        digits = "".join(ch for ch in normalized if ch.isdigit())
        return f"{digits}{_WHATSAPP_LID_SUFFIX}" if digits else lowered

    if "@" in lowered:
        return lowered

    digits = "".join(ch for ch in raw_value if ch.isdigit())
    return digits or raw_value


def _normalize_whatsapp_phone_number_candidate(value: str | None) -> str | None:
    normalized = _normalize_whatsapp_jid(str(value or "").strip())
    if not normalized:
        return None
    if normalized.endswith(_WHATSAPP_LID_SUFFIX) or "@" in normalized:
        return None
    digits = "".join(ch for ch in normalized if ch.isdigit())
    return digits or None


def _unique_preserving_order(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        unique_values.append(cleaned)
        seen.add(cleaned)
    return unique_values


def _extract_preferred_whatsapp_phone_number(item: dict, key_payload: dict) -> str | None:
    candidate_values = [
        key_payload.get("senderPn"),
        key_payload.get("participantPn"),
        key_payload.get("remoteJidAlt"),
        item.get("senderPn"),
        item.get("participantPn"),
        item.get("remoteJidAlt"),
        key_payload.get("remoteJid"),
        item.get("remoteJid"),
    ]
    for candidate in candidate_values:
        normalized_phone = _normalize_whatsapp_phone_number_candidate(str(candidate or "").strip())
        if normalized_phone:
            return normalized_phone
    return None


def _build_whatsapp_identity_candidates(item: dict, key_payload: dict) -> list[str]:
    normalized_candidates: list[str] = []
    raw_candidates = [
        key_payload.get("senderPn"),
        key_payload.get("participantPn"),
        key_payload.get("remoteJidAlt"),
        key_payload.get("remoteJid"),
        key_payload.get("senderLid"),
        key_payload.get("participant"),
        key_payload.get("participantLid"),
        item.get("senderPn"),
        item.get("participantPn"),
        item.get("remoteJidAlt"),
        item.get("remoteJid"),
        item.get("senderLid"),
        item.get("participant"),
        item.get("participantLid"),
    ]
    for candidate in raw_candidates:
        normalized = _normalize_whatsapp_jid(str(candidate or "").strip())
        if normalized:
            normalized_candidates.append(normalized)
    return _unique_preserving_order(normalized_candidates)


def _extract_text_content(message_payload: dict) -> str | None:
    conversation_text = str(message_payload.get("conversation") or "").strip()
    if conversation_text:
        return conversation_text

    extended_text_message = to_payload_dict(message_payload.get("extendedTextMessage"))
    extended_text = str(extended_text_message.get("text") or "").strip()
    if extended_text:
        return extended_text
    return None


def _extract_media_payload(message_payload: dict) -> tuple[str | None, str | None]:
    media_map = (
        ("imageMessage", "image"),
        ("videoMessage", "video"),
        ("audioMessage", "audio"),
        ("documentMessage", "document"),
        ("stickerMessage", "sticker"),
    )
    for key, message_type in media_map:
        media_payload = to_payload_dict(message_payload.get(key))
        if not media_payload:
            continue
        media_url = str(
            media_payload.get("url")
            or media_payload.get("directPath")
            or media_payload.get("mediaUrl")
            or ""
        ).strip()
        if media_url:
            return media_url, message_type
    return None, None


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
        if isGroupJid(platform_user_id):
            continue
        identity_candidates = _build_whatsapp_identity_candidates(item, key_payload)
        preferred_phone_number = _extract_preferred_whatsapp_phone_number(item, key_payload)
        if preferred_phone_number:
            identity_candidates = _unique_preserving_order(
                [preferred_phone_number, *identity_candidates]
            )
        platform_user_id = identity_candidates[0] if identity_candidates else platform_user_id
        if isGroupJid(platform_user_id):
            continue
        if not platform_user_id:
            continue

        message_payload = to_payload_dict(item.get("message"))
        text_content = _extract_text_content(message_payload)
        media_url, media_message_type = _extract_media_payload(message_payload)
        if not text_content and not media_url:
            continue

        external_message_id = str(key_payload.get("id") or item.get("id") or "").strip()
        profile_name = str(item.get("pushName") or item.get("senderName") or "").strip() or None

        extracted.append(
            {
                "platform": "whatsapp",
                "platform_user_id": platform_user_id,
                "alternate_platform_user_ids": identity_candidates[1:],
                "preferred_phone_number": preferred_phone_number,
                "profile_name": profile_name,
                "external_message_id": external_message_id or None,
                "message_type": media_message_type or "text",
                "text_content": text_content,
                "media_url": media_url,
                "phone_number_id": None,
                "raw_payload": item,
            }
        )
    return extracted


@router.post("/webhooks/evolution", status_code=status.HTTP_202_ACCEPTED)
@router.post("/webhooks/whatsapp", status_code=status.HTTP_202_ACCEPTED)
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
