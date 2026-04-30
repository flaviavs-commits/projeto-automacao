import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.audit_log import AuditLog
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.models.conversation import Conversation
from app.models.message import Message
from app.workers.tasks import _finalize_collected_customer_data


class MenuBotCollectionFinalizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_finalize_collected_data_creates_contact_profile_and_audit(self) -> None:
        contact = Contact(name=None, phone=None, email=None, is_temporary=True)
        self.db.add(contact)
        self.db.flush()
        conversation = Conversation(contact_id=contact.id, platform="whatsapp", status="open")
        self.db.add(conversation)
        self.db.flush()
        source_message = Message(
            conversation_id=conversation.id,
            platform="whatsapp",
            direction="inbound",
            message_type="text",
            text_content="cadastro",
            raw_payload={"_resolved_platform_user_id": "5524999999999@c.us"},
            ai_generated=False,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(source_message)
        self.db.flush()

        result = _finalize_collected_customer_data(
            db=self.db,
            conversation=conversation,
            contact=contact,
            source_message=source_message,
            collection_data={
                "name": "Maria Silva",
                "phone_normalized": "+5524999999999",
                "email": "maria@email.com",
                "instagram": "@maria.silva",
                "facebook": "maria.silva",
            },
        )
        self.db.commit()

        self.assertEqual(result.get("status"), "completed")
        refreshed_contact = self.db.get(Contact, contact.id)
        assert refreshed_contact is not None
        self.assertEqual(refreshed_contact.name, "Maria Silva")
        self.assertEqual(refreshed_contact.phone, "+5524999999999")
        self.assertEqual(refreshed_contact.email, "maria@email.com")
        self.assertEqual(refreshed_contact.instagram_user_id, "maria.silva")
        self.assertFalse(refreshed_contact.is_temporary)

        refreshed_conversation = self.db.get(Conversation, conversation.id)
        assert refreshed_conversation is not None
        self.assertEqual(refreshed_conversation.customer_collection_data, {})
        self.assertIsNone(refreshed_conversation.customer_collection_step)

        identities = (
            self.db.execute(
                select(ContactIdentity).where(ContactIdentity.contact_id == refreshed_contact.id)
            )
            .scalars()
            .all()
        )
        identity_pairs = {(identity.platform, identity.platform_user_id) for identity in identities}
        self.assertIn(("whatsapp", "5524999999999"), identity_pairs)
        self.assertIn(("instagram", "maria.silva"), identity_pairs)
        self.assertIn(("facebook", "maria.silva"), identity_pairs)

        audit = (
            self.db.execute(
                select(AuditLog).where(
                    AuditLog.entity_type == "contact",
                    AuditLog.entity_id == refreshed_contact.id,
                    AuditLog.event_type == "customer_data_collected",
                )
            )
            .scalars()
            .first()
        )
        self.assertIsNotNone(audit)

    def test_finalize_uses_existing_contact_and_keeps_conflicting_fields(self) -> None:
        existing = Contact(
            name="Ana Antiga",
            phone="+5524988887777",
            email="ana@old.com",
            is_temporary=False,
        )
        temp_contact = Contact(name=None, phone="5524991112222", email=None, is_temporary=True)
        self.db.add(existing)
        self.db.add(temp_contact)
        self.db.flush()

        conversation = Conversation(contact_id=temp_contact.id, platform="whatsapp", status="open")
        self.db.add(conversation)
        self.db.flush()
        source_message = Message(
            conversation_id=conversation.id,
            platform="whatsapp",
            direction="inbound",
            message_type="text",
            text_content="cadastro",
            raw_payload={"_resolved_platform_user_id": "5524991112222@c.us"},
            ai_generated=False,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(source_message)
        self.db.flush()

        result = _finalize_collected_customer_data(
            db=self.db,
            conversation=conversation,
            contact=temp_contact,
            source_message=source_message,
            collection_data={
                "name": "Nome Novo",
                "phone_normalized": "+5524977776666",
                "email": "ana@old.com",
                "instagram": None,
                "facebook": None,
            },
        )
        self.db.commit()

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(str(conversation.contact_id), str(existing.id))
        refreshed_existing = self.db.get(Contact, existing.id)
        assert refreshed_existing is not None
        self.assertEqual(refreshed_existing.name, "Ana Antiga")
        self.assertEqual(refreshed_existing.phone, "+5524988887777")
        self.assertEqual(refreshed_existing.email, "ana@old.com")
        self.assertGreaterEqual(len(result.get("field_conflicts") or []), 1)


if __name__ == "__main__":
    unittest.main()
