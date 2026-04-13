from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.contact_memory import ContactMemory
from app.models.conversation import Conversation
from app.models.message import Message


class MemoryService:
    """Builds compact conversation context for prompt assembly."""

    def build_context(self, conversation_id: str | None = None) -> dict:
        if not conversation_id:
            return {
                "status": "ready",
                "conversation_id": conversation_id,
                "memory_items": [],
                "key_memories": [],
            }

        try:
            conversation_uuid = UUID(str(conversation_id))
        except Exception:  # noqa: BLE001
            return {
                "status": "invalid_conversation_id",
                "conversation_id": conversation_id,
                "memory_items": [],
                "key_memories": [],
            }

        with SessionLocal() as db:
            conversation = db.get(Conversation, conversation_uuid)
            if conversation is None:
                return {
                    "status": "conversation_not_found",
                    "conversation_id": conversation_id,
                    "memory_items": [],
                    "key_memories": [],
                }

            messages = (
                db.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_uuid)
                    .order_by(Message.created_at.desc())
                    .limit(max(1, settings.llm_context_messages)),
                )
                .scalars()
                .all()
            )
            key_memories_rows = (
                db.execute(
                    select(ContactMemory)
                    .where(
                        ContactMemory.contact_id == conversation.contact_id,
                        ContactMemory.status == "active",
                    )
                    .order_by(
                        ContactMemory.importance.desc(),
                        ContactMemory.updated_at.desc(),
                    )
                    .limit(20),
                )
                .scalars()
                .all()
            )

        memory_items: list[dict] = []
        for message in reversed(messages):
            text = " ".join((message.transcription or message.text_content or "").split()).strip()
            if not text:
                continue

            role = "assistant" if str(message.direction or "").lower() == "outbound" else "user"
            memory_items.append(
                {
                    "role": role,
                    "text": text[:1200],
                    "message_type": message.message_type,
                    "created_at": message.created_at.isoformat() if message.created_at else None,
                }
            )

        key_memories: list[dict] = []
        for memory in key_memories_rows:
            key_memories.append(
                {
                    "key": memory.memory_key,
                    "value": memory.memory_value,
                    "importance": memory.importance,
                    "confidence": memory.confidence,
                    "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
                }
            )

        return {
            "status": "ready",
            "conversation_id": conversation_id,
            "memory_items": memory_items,
            "key_memories": key_memories,
        }
