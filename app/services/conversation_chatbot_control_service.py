from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.conversation import Conversation


class ConversationChatbotControlService:
    """Toggles chatbot behavior per conversation with audit trail."""

    def set_enabled(
        self,
        *,
        db: Session,
        conversation_id: UUID,
        enabled: bool,
        actor: str | None,
    ) -> dict:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None:
            raise ValueError("conversation_not_found")

        conversation.chatbot_enabled = bool(enabled)
        event_type = "chatbot_enabled" if conversation.chatbot_enabled else "chatbot_disabled"
        db.add(
            AuditLog(
                entity_type="conversation",
                entity_id=conversation.id,
                event_type=event_type,
                details={
                    "conversation_id": str(conversation.id),
                    "chatbot_enabled": conversation.chatbot_enabled,
                    "actor": actor,
                },
            )
        )
        db.commit()
        return {
            "conversation_id": str(conversation.id),
            "chatbot_enabled": conversation.chatbot_enabled,
        }
