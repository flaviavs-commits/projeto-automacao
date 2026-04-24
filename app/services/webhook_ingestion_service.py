from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.customer_identity_service import CustomerIdentityService


def to_payload_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


class WebhookIngestionService:
    """Persists inbound webhook messages and returns task payloads for async processing."""

    def persist_inbound_messages(
        self,
        *,
        db: Session,
        extracted_messages: list[dict[str, Any]],
        audit_event_type: str,
        audit_details: dict[str, Any],
    ) -> dict[str, Any]:
        now_utc = datetime.now(timezone.utc)
        created_messages_count = 0
        duplicate_messages_count = 0
        queued_task_payloads: list[dict[str, Any]] = []

        db.add(
            AuditLog(
                entity_type="webhook",
                event_type=audit_event_type,
                details={
                    **audit_details,
                    "messages_detected": len(extracted_messages),
                },
            )
        )

        for item in extracted_messages:
            platform_user_id = str(item.get("platform_user_id") or "").strip()
            if not platform_user_id:
                continue

            external_message_id = str(item.get("external_message_id") or "").strip() or None
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
                platform=str(item.get("platform") or "whatsapp"),
                platform_user_id=platform_user_id,
                profile_name=item.get("profile_name"),
            )
            conversation = self._get_or_create_open_conversation(
                db=db,
                contact_id=contact.id,
                platform=str(item.get("platform") or "whatsapp"),
            )
            conversation.last_message_at = now_utc

            message = Message(
                conversation_id=conversation.id,
                platform=str(item.get("platform") or "whatsapp"),
                direction="inbound",
                message_type=str(item.get("message_type") or "unknown"),
                external_message_id=external_message_id,
                text_content=item.get("text_content"),
                media_url=item.get("media_url"),
                raw_payload={
                    **to_payload_dict(item.get("raw_payload")),
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
        return {
            "messages_created": created_messages_count,
            "messages_duplicated": duplicate_messages_count,
            "queued_task_payloads": queued_task_payloads,
        }

    def _get_or_create_open_conversation(
        self,
        *,
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
