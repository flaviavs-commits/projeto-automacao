import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.config import settings
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.workers import tasks


class WorkerGroupGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()
        self.original_tasks_session_local = tasks.SessionLocal
        self.original_llm_enabled = settings.llm_enabled
        tasks.SessionLocal = self.SessionLocal
        settings.llm_enabled = False

    def tearDown(self) -> None:
        tasks.SessionLocal = self.original_tasks_session_local
        settings.llm_enabled = self.original_llm_enabled
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_process_incoming_message_ignores_group_jid(self) -> None:
        contact = Contact(name="Grupo", phone="")
        self.db.add(contact)
        self.db.flush()
        conversation = Conversation(contact_id=contact.id, platform="whatsapp", status="open")
        self.db.add(conversation)
        self.db.flush()
        inbound = Message(
            conversation_id=conversation.id,
            platform="whatsapp",
            direction="inbound",
            message_type="text",
            text_content="Mensagem grupo",
            raw_payload={"_resolved_platform_user_id": "120363111111111111@g.us"},
            ai_generated=False,
        )
        self.db.add(inbound)
        self.db.commit()

        with patch("app.workers.tasks.generate_reply") as generate_mock:
            result = tasks.process_incoming_message({"message_id": str(inbound.id), "platform": "whatsapp"})

        self.assertEqual(result.get("status"), "ignored_group_jid")
        self.assertEqual(generate_mock.call_count, 0)
        outbound_count = (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation.id, Message.direction == "outbound")
            .count()
        )
        self.assertEqual(outbound_count, 0)


if __name__ == "__main__":
    unittest.main()
