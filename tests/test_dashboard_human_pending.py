import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.api.routes.dashboard import dashboard_op_state


class DashboardHumanPendingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_human_request_is_counted_on_dashboard(self) -> None:
        contact = Contact(name="Cliente", phone="5524999999999")
        self.db.add(contact)
        self.db.flush()
        conversation = Conversation(
            contact_id=contact.id,
            platform="whatsapp",
            status="open",
            menu_state="human_menu",
            needs_human=True,
            human_reason="agendamento",
            human_requested_at=datetime.now(timezone.utc),
        )
        self.db.add(conversation)
        self.db.flush()
        self.db.add(
            Message(
                conversation_id=conversation.id,
                platform="whatsapp",
                direction="inbound",
                message_type="text",
                text_content="quero falar com atendente",
                raw_payload={},
                ai_generated=False,
            )
        )
        self.db.commit()

        payload = dashboard_op_state(
            conversation_id=None,
            conversation_limit=60,
            message_limit=120,
            db=self.db,
        )
        self.assertEqual(payload["kpis"]["human_pending_total"], 1)
        self.assertEqual(len(payload["human_pending"]), 1)
        self.assertEqual(payload["human_pending"][0]["human_reason"], "agendamento")


if __name__ == "__main__":
    unittest.main()
