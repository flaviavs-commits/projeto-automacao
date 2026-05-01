import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.webhook_ingestion_service import WebhookIngestionService


class WebhookIngestionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_persist_inbound_updates_last_inbound_fields(self) -> None:
        payload = {
            "platform": "whatsapp",
            "platform_user_id": "5511999999999",
            "external_message_id": "MSG-1",
            "message_type": "text",
            "text_content": "Ola",
            "raw_payload": {},
        }
        result = WebhookIngestionService().persist_inbound_messages(
            db=self.db,
            extracted_messages=[payload],
            audit_event_type="test_webhook",
            audit_details={"source": "unit"},
        )
        self.assertEqual(result.get("messages_created"), 1)

        conversation = self.db.query(Conversation).first()
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.last_inbound_message_text, "Ola")
        self.assertIsNotNone(conversation.last_inbound_message_at)

    def test_persist_inbound_deduplicates_by_external_message_id(self) -> None:
        payload = {
            "platform": "whatsapp",
            "platform_user_id": "5511999999999",
            "external_message_id": "MSG-DEDUP-1",
            "message_type": "text",
            "text_content": "Primeira",
            "raw_payload": {},
        }
        first = WebhookIngestionService().persist_inbound_messages(
            db=self.db,
            extracted_messages=[payload],
            audit_event_type="test_webhook",
            audit_details={"source": "unit"},
        )
        second = WebhookIngestionService().persist_inbound_messages(
            db=self.db,
            extracted_messages=[payload],
            audit_event_type="test_webhook",
            audit_details={"source": "unit"},
        )
        self.assertEqual(first.get("messages_created"), 1)
        self.assertEqual(second.get("messages_created"), 0)
        self.assertEqual(second.get("messages_duplicated"), 1)

    def test_persist_inbound_ignores_group_jid(self) -> None:
        payload = {
            "platform": "whatsapp",
            "platform_user_id": "120363111111111111@g.us",
            "external_message_id": "MSG-GRP-1",
            "message_type": "text",
            "text_content": "Grupo",
            "raw_payload": {},
        }

        result = WebhookIngestionService().persist_inbound_messages(
            db=self.db,
            extracted_messages=[payload],
            audit_event_type="test_webhook",
            audit_details={"source": "unit"},
        )

        self.assertEqual(result.get("messages_created"), 0)
        self.assertEqual(self.db.query(Contact).count(), 0)
        self.assertEqual(self.db.query(Conversation).count(), 0)
        self.assertEqual(self.db.query(Message).count(), 0)


if __name__ == "__main__":
    unittest.main()
