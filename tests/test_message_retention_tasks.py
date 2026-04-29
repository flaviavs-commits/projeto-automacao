import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.core.config import settings
from app.models.contact import Contact
from app.models.contact_memory import ContactMemory
from app.models.conversation import Conversation
from app.models.message import Message
from app.workers.tasks import _prune_conversation_messages


class MessageRetentionTasksTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_prune_keeps_recent_messages_without_deleting_memories(self) -> None:
        original_limit = settings.message_retention_max_per_conversation
        settings.message_retention_max_per_conversation = 3
        try:
            contact = Contact(name="Teste", phone="5511999999999")
            self.db.add(contact)
            self.db.flush()
            conversation = Conversation(contact_id=contact.id, platform="whatsapp", status="open")
            self.db.add(conversation)
            self.db.flush()

            now_utc = datetime.now(timezone.utc)
            created_messages: list[Message] = []
            for index in range(5):
                message = Message(
                    conversation_id=conversation.id,
                    platform="whatsapp",
                    direction="inbound",
                    message_type="text",
                    text_content=f"msg-{index}",
                    raw_payload={},
                    ai_generated=False,
                    created_at=now_utc + timedelta(seconds=index),
                )
                self.db.add(message)
                self.db.flush()
                created_messages.append(message)

            self.db.add(
                ContactMemory(
                    contact_id=contact.id,
                    source_message_id=created_messages[0].id,
                    memory_key="nome_cliente",
                    memory_value="Teste",
                    status="active",
                    importance=5,
                    confidence=0.9,
                )
            )
            self.db.commit()

            removed = _prune_conversation_messages(db=self.db, conversation_id=conversation.id)
            self.db.commit()

            self.assertEqual(removed, 2)
            remaining_messages = (
                self.db.query(Message)
                .filter(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
                .all()
            )
            self.assertEqual(len(remaining_messages), 3)
            self.assertEqual(
                [message.text_content for message in remaining_messages],
                ["msg-2", "msg-3", "msg-4"],
            )
            self.assertEqual(self.db.query(ContactMemory).count(), 1)
        finally:
            settings.message_retention_max_per_conversation = original_limit


if __name__ == "__main__":
    unittest.main()
