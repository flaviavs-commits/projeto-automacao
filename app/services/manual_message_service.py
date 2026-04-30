from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.instagram_service import InstagramService
from app.services.whatsapp_service import WhatsAppService


class ManualMessageService:
    """Validates and dispatches manual operator messages via backend services."""

    SUPPORTED_CHANNELS = {"whatsapp", "instagram", "facebook", "tiktok"}

    def send(
        self,
        *,
        db: Session,
        conversation_id: UUID,
        channel: str,
        text: str,
        contact_identity_id: UUID | None = None,
        actor: str | None = None,
    ) -> dict:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            return {"status": "failed", "detail": "Essa conversa nao existe."}
        if str(conversation.status or "").strip().lower() == "closed":
            # Operator can resume a closed conversation from dashboard.
            conversation.status = "open"
            conversation.needs_human = False
            conversation.human_status = "closed"
            conversation.human_reason = None
            conversation.human_requested_at = None

        contact = db.get(Contact, conversation.contact_id)
        if contact is None:
            return {"status": "failed", "detail": "Nao encontramos esse cliente."}

        clean_channel = str(channel or "").strip().lower()
        clean_text = str(text or "").strip()
        if not clean_text:
            return {"status": "failed", "detail": "Digite uma mensagem antes de enviar.", "status_code": 400}
        if clean_channel not in self.SUPPORTED_CHANNELS:
            return {"status": "blocked_channel_unavailable", "detail": "Canal indisponivel no momento.", "status_code": 400}

        recipient = self._resolve_recipient(
            db=db,
            contact=contact,
            channel=clean_channel,
            contact_identity_id=contact_identity_id,
        )
        if not recipient:
            return {
                "status": "blocked_channel_unavailable",
                "detail": "Nao foi possivel enviar por este canal agora.",
                "status_code": 400,
            }

        dispatch = self._dispatch(channel=clean_channel, recipient=recipient, text=clean_text)
        dispatch_status = str(dispatch.get("status") or "").strip().lower()
        if dispatch_status not in {"completed", "ok", "success"}:
            return {
                "status": "failed",
                "detail": "Canal indisponivel no momento.",
                "status_code": 400,
            }

        outbound = Message(
            conversation_id=conversation.id,
            platform=clean_channel,
            direction="outbound",
            message_type="text",
            text_content=clean_text,
            raw_payload={
                "source": "dashboard_manual",
                "channel": clean_channel,
            },
            ai_generated=False,
        )
        db.add(outbound)
        conversation.last_message_at = datetime.now(timezone.utc)
        db.flush()

        db.add(
            AuditLog(
                entity_type="conversation",
                entity_id=conversation.id,
                event_type="manual_message_sent",
                details={
                    "conversation_id": str(conversation.id),
                    "message_id": str(outbound.id),
                    "channel": clean_channel,
                    "actor": actor,
                },
            )
        )
        db.commit()
        db.refresh(outbound)
        return {"status": "sent", "message_id": str(outbound.id)}

    def _resolve_recipient(
        self,
        *,
        db: Session,
        contact: Contact,
        channel: str,
        contact_identity_id: UUID | None,
    ) -> str:
        if contact_identity_id is not None:
            chosen = db.get(ContactIdentity, contact_identity_id)
            if chosen is None or chosen.contact_id != contact.id or chosen.platform != channel:
                return ""
            return self._normalize_identity(channel=channel, value=chosen.platform_user_id)

        if channel == "whatsapp":
            phone = self._normalize_identity(channel=channel, value=contact.phone or "")
            if phone:
                return phone
        if channel == "instagram":
            direct = self._normalize_identity(channel=channel, value=contact.instagram_user_id or "")
            if direct:
                return direct

        identity = (
            db.execute(
                select(ContactIdentity)
                .where(
                    ContactIdentity.contact_id == contact.id,
                    ContactIdentity.platform == channel,
                )
                .order_by(ContactIdentity.is_primary.desc(), ContactIdentity.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if identity is None:
            return ""
        return self._normalize_identity(channel=channel, value=identity.platform_user_id)

    def _normalize_identity(self, *, channel: str, value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        if channel == "whatsapp":
            lowered = raw.lower()
            for suffix in ("@s.whatsapp.net", "@c.us"):
                if lowered.endswith(suffix):
                    raw = raw[: -len(suffix)]
                    lowered = raw.lower()
            if lowered.endswith("@lid") or "@" in lowered:
                return ""
            digits = "".join(ch for ch in raw if ch.isdigit())
            return digits
        return raw

    def _dispatch(self, *, channel: str, recipient: str, text: str) -> dict:
        if channel == "whatsapp":
            if not settings.whatsapp_dispatch_ready:
                return {"status": "missing_credentials"}
            return WhatsAppService().send_text_message({"to": recipient, "text": text})
        if channel == "instagram":
            return InstagramService().send_text_message({"to": recipient, "text": text})
        return {"status": "integration_disabled"}
