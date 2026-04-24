import json
from hashlib import sha1, sha256
from hmac import new as hmac_new
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import safe_compare, verify_meta_signature
from app.models.audit_log import AuditLog
from app.schemas.webhook import MetaWebhookEnvelope
from app.services.webhook_ingestion_service import WebhookIngestionService, to_payload_dict
from app.workers.tasks import process_incoming_message


router = APIRouter(prefix="/webhooks/meta", tags=["webhooks"])
logger = get_logger(__name__)


def _extract_meta_messages(envelope_payload: dict) -> list[dict]:
    extracted: list[dict] = []
    envelope_object = str(envelope_payload.get("object") or "").strip().lower()

    for entry in envelope_payload.get("entry", []):
        if not isinstance(entry, dict):
            continue

        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue

            value = to_payload_dict(change.get("value"))
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

                if wa_id:
                    extracted.append(
                        {
                            "platform": "whatsapp",
                            "platform_user_id": wa_id,
                            "profile_name": profile_name,
                            "external_message_id": external_message_id,
                            "message_type": message_type,
                            "text_content": text_content,
                            "media_url": str(media_url) if media_url else None,
                            "phone_number_id": phone_number_id,
                            "raw_payload": message,
                        }
                    )

        messaging_events = entry.get("messaging")
        if not isinstance(messaging_events, list):
            continue

        for event in messaging_events:
            if not isinstance(event, dict):
                continue

            message = to_payload_dict(event.get("message"))
            if not message:
                continue

            sender = to_payload_dict(event.get("sender"))
            sender_id = str(sender.get("id") or "").strip()
            if not sender_id:
                continue
            profile_name = str(sender.get("name") or "").strip() or None

            messaging_product = str(event.get("messaging_product") or "").strip().lower()
            platform = "facebook"
            if messaging_product == "instagram" or (not messaging_product and envelope_object == "instagram"):
                platform = "instagram"
            text_content = message.get("text")
            external_message_id = str(message.get("mid") or message.get("id") or "").strip()

            media_url = None
            attachments = message.get("attachments")
            if isinstance(attachments, list) and attachments:
                first_attachment = attachments[0] if isinstance(attachments[0], dict) else {}
                payload = to_payload_dict(first_attachment.get("payload"))
                media_url = str(payload.get("url") or "").strip() or None

            extracted.append(
                {
                    "platform": platform,
                    "platform_user_id": sender_id,
                    "profile_name": profile_name,
                    "external_message_id": external_message_id,
                    "message_type": str(message.get("type") or "text"),
                    "text_content": text_content,
                    "media_url": media_url,
                    "phone_number_id": None,
                    "raw_payload": event,
                }
            )

    return extracted


@router.get("", response_class=PlainTextResponse)
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
    raw_body = await request.body()
    candidate_secrets: list[tuple[str, str]] = []
    effective_meta_secret = settings.effective_meta_app_secret.strip()
    if effective_meta_secret:
        candidate_secrets.append(("primary", effective_meta_secret))
    previous_meta_secret = settings.meta_app_secret_previous.strip()
    if previous_meta_secret and previous_meta_secret != effective_meta_secret:
        candidate_secrets.append(("previous", previous_meta_secret))

    if candidate_secrets:
        signature_candidates: list[tuple[str, str]] = []
        for header_name in ("X-Hub-Signature-256", "X-Hub-Signature"):
            header_value = str(request.headers.get(header_name) or "").strip()
            if header_value:
                signature_candidates.append((header_name, header_value))

        signature_ok = False
        matched_signature_header_name = None
        matched_signature_header_prefix = None
        matched_secret_source = None
        for secret_source, secret_value in candidate_secrets:
            for header_name, header_value in signature_candidates:
                if verify_meta_signature(
                    body=raw_body,
                    signature_header=header_value,
                    app_secret=secret_value,
                ):
                    signature_ok = True
                    matched_signature_header_name = header_name
                    matched_signature_header_prefix = header_value[:24]
                    matched_secret_source = secret_source
                    break
            if signature_ok:
                break
        if not signature_ok:
            signature_256 = str(request.headers.get("X-Hub-Signature-256") or "")
            signature_legacy = str(request.headers.get("X-Hub-Signature") or "")
            body_sha256_prefix = sha256(raw_body).hexdigest()[:24]
            invalid_object = None
            invalid_entry_id = None
            try:
                invalid_payload = json.loads(raw_body.decode("utf-8"))
                if isinstance(invalid_payload, dict):
                    invalid_object = str(invalid_payload.get("object") or "").strip() or None
                    entries = invalid_payload.get("entry")
                    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
                        invalid_entry_id = str(entries[0].get("id") or "").strip() or None
            except Exception:
                invalid_object = None
                invalid_entry_id = None
            user_agent_prefix = str(request.headers.get("User-Agent") or "")[:80]
            expected_digests: list[dict[str, str]] = []
            for source, secret_value in candidate_secrets:
                expected_digests.append(
                    {
                        "source": source,
                        "sha256_prefix": hmac_new(secret_value.encode("utf-8"), raw_body, sha256).hexdigest()[:24],
                        "sha1_prefix": hmac_new(secret_value.encode("utf-8"), raw_body, sha1).hexdigest()[:24],
                    }
                )
            try:
                db.add(
                    AuditLog(
                        entity_type="webhook",
                        event_type="meta_webhook_invalid_signature",
                        details={
                            "path": str(request.url.path),
                            "environment": settings.app_env,
                            "signature_present": bool(signature_candidates),
                            "signature_header_name": signature_candidates[0][0] if signature_candidates else None,
                            "signature_header_prefix": signature_candidates[0][1][:24] if signature_candidates else "",
                            "signature_256_prefix": signature_256[:24],
                            "signature_legacy_prefix": signature_legacy[:24],
                            "user_agent_prefix": user_agent_prefix,
                            "x_forwarded_for": str(request.headers.get("X-Forwarded-For") or "")[:120],
                            "object": invalid_object,
                            "entry_id": invalid_entry_id,
                            "candidate_secret_sources": [source for source, _ in candidate_secrets],
                            "body_sha256_prefix": body_sha256_prefix,
                            "expected_digests": expected_digests,
                        },
                    )
                )
                db.commit()
            except Exception:
                db.rollback()
            logger.warning(
                (
                    "meta_webhook_invalid_signature "
                    f"header_name={signature_candidates[0][0] if signature_candidates else None} "
                    f"sig256_prefix={signature_256[:24]} "
                    f"sig_prefix={signature_legacy[:24]} "
                    f"body_sha256_prefix={body_sha256_prefix} "
                    f"object={invalid_object} entry_id={invalid_entry_id} "
                    f"user_agent_prefix={user_agent_prefix}"
                ),
                extra={
                    "path": str(request.url.path),
                    "environment": settings.app_env,
                    "signature_header_name": signature_candidates[0][0] if signature_candidates else None,
                    "signature_header_prefix": signature_candidates[0][1][:24] if signature_candidates else "",
                    "signature_256_prefix": signature_256[:24],
                    "signature_legacy_prefix": signature_legacy[:24],
                    "user_agent_prefix": user_agent_prefix,
                    "candidate_secret_sources": [source for source, _ in candidate_secrets],
                    "body_sha256_prefix": body_sha256_prefix,
                    "expected_digests": expected_digests,
                },
            )
            bypass_unsigned_instagram = (
                settings.meta_allow_unsigned_instagram
                and invalid_object == "instagram"
                and bool(signature_candidates)
            )
            if bypass_unsigned_instagram:
                try:
                    db.add(
                        AuditLog(
                            entity_type="webhook",
                            event_type="meta_webhook_signature_bypassed",
                            details={
                                "path": str(request.url.path),
                                "environment": settings.app_env,
                                "object": invalid_object,
                                "entry_id": invalid_entry_id,
                                "signature_header_name": signature_candidates[0][0] if signature_candidates else None,
                                "signature_header_prefix": signature_candidates[0][1][:24] if signature_candidates else "",
                                "user_agent_prefix": user_agent_prefix,
                            },
                        )
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                logger.warning(
                    "meta_webhook_signature_bypassed",
                    extra={
                        "path": str(request.url.path),
                        "environment": settings.app_env,
                        "object": invalid_object,
                        "entry_id": invalid_entry_id,
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Meta signature",
                )
        logger.info(
            "meta_webhook_signature_valid",
            extra={
                "path": str(request.url.path),
                "environment": settings.app_env,
                "matched_signature_header_name": matched_signature_header_name,
                "matched_signature_header_prefix": matched_signature_header_prefix,
                "matched_secret_source": matched_secret_source,
            },
        )

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
    extracted_messages = _extract_meta_messages(envelope_payload)
    queued_messages_count = 0
    ingestion_result = WebhookIngestionService().persist_inbound_messages(
        db=db,
        extracted_messages=extracted_messages,
        audit_event_type="meta_webhook_received",
        audit_details={
            "object": envelope.object,
            "entries_count": len(envelope_payload.get("entry", [])),
            "payload": envelope_payload,
        },
    )
    created_messages_count = int(ingestion_result.get("messages_created") or 0)
    duplicate_messages_count = int(ingestion_result.get("messages_duplicated") or 0)
    queued_task_payloads = ingestion_result.get("queued_task_payloads") or []

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
