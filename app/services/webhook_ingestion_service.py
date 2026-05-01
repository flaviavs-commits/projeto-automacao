from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.customer_identity_service import CustomerIdentityService
from app.services.whatsapp_jid_utils import isGroupJid


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
            platform = str(item.get("platform") or "whatsapp")
            platform_user_id = str(item.get("platform_user_id") or "").strip()
            if not platform_user_id:
                continue
            if platform == "whatsapp" and isGroupJid(platform_user_id):
                continue
            alternate_platform_user_ids = [
                str(value or "").strip()
                for value in (item.get("alternate_platform_user_ids") or [])
                if str(value or "").strip()
                and not (platform == "whatsapp" and isGroupJid(str(value or "").strip()))
            ]
            preferred_phone_number = str(item.get("preferred_phone_number") or "").strip() or None

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

            identity_resolution_meta: dict = {}
            contact = CustomerIdentityService().resolve_or_create_contact(
                db=db,
                platform=platform,
                platform_user_id=platform_user_id,
                profile_name=item.get("profile_name"),
                alternate_platform_user_ids=alternate_platform_user_ids,
                preferred_phone_number=preferred_phone_number,
                resolution_meta=identity_resolution_meta,
            )
            if identity_resolution_meta.get("identity_enriched"):
                db.add(
                    AuditLog(
                        entity_type="contact",
                        entity_id=contact.id,
                        event_type="identity_enriched",
                        details={
                            "contact_id": str(contact.id),
                            "platform": platform,
                            "platform_user_id": platform_user_id,
                            "preferred_phone_number": preferred_phone_number,
                        },
                    )
                )
            for conflict in identity_resolution_meta.get("identity_conflicts") or []:
                db.add(
                    AuditLog(
                        entity_type="contact_identity",
                        entity_id=contact.id,
                        event_type="identity_conflict",
                        details={
                            "contact_id": str(contact.id),
                            "platform": platform,
                            "platform_user_id": platform_user_id,
                            "conflict": conflict,
                        },
                    )
                )
            conversation = self._get_or_create_open_conversation(
                db=db,
                contact_id=contact.id,
                platform=platform,
            )
            conversation.last_message_at = now_utc
            conversation.last_inbound_message_text = str(item.get("text_content") or "").strip() or None
            conversation.last_inbound_message_at = now_utc

            message = Message(
                conversation_id=conversation.id,
                platform=platform,
                direction="inbound",
                message_type=str(item.get("message_type") or "unknown"),
                external_message_id=external_message_id,
                text_content=item.get("text_content"),
                media_url=item.get("media_url"),
                raw_payload={
                    **to_payload_dict(item.get("raw_payload")),
                    "_alternate_platform_user_ids": alternate_platform_user_ids,
                    "_phone_number_id": item.get("phone_number_id"),
                    "_preferred_phone_number": preferred_phone_number,
                    "_resolved_platform_user_id": platform_user_id,
                    "_identity_resolution_meta": identity_resolution_meta,
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
            contact = db.get(Contact, contact_id)
            contact_phone = str((contact.phone if contact else "") or "").strip()
            if contact_phone:
                conversation = (
                    db.query(Conversation)
                    .join(Contact, Contact.id == Conversation.contact_id)
                    .filter(
                        Conversation.platform == platform,
                        Conversation.status == "open",
                        Contact.phone == contact_phone,
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
