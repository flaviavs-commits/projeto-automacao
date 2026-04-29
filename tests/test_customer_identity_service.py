import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.contact import Contact
from app.models.contact_identity import ContactIdentity
from app.services.customer_identity_service import CustomerIdentityService


class CustomerIdentityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CustomerIdentityService()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_normalize_whatsapp_evolution_suffix_s_whatsapp(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "whatsapp",
            "5511999999999@s.whatsapp.net",
        )
        self.assertEqual(normalized, "5511999999999")

    def test_normalize_whatsapp_evolution_suffix_c_us(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "whatsapp",
            "5511888888888@c.us",
        )
        self.assertEqual(normalized, "5511888888888")

    def test_normalize_instagram_keeps_username_shape(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "instagram",
            "@MeuUsuario",
        )
        self.assertEqual(normalized, "@meuusuario")

    def test_normalize_whatsapp_lid_keeps_lid_suffix(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "whatsapp",
            "133595024851015@lid",
        )
        self.assertEqual(normalized, "133595024851015@lid")

    def test_resolve_or_create_contact_merges_phone_with_existing_lid_identity(self) -> None:
        first_contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="133595024851015@lid",
            profile_name="Gabriel Fernandes",
        )
        self.db.commit()
        self.assertTrue(first_contact.is_temporary)

        merged_contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="5524999849231",
            profile_name="Gabriel Fernandes",
            alternate_platform_user_ids=["133595024851015@lid"],
            preferred_phone_number="5524999849231",
        )
        self.db.commit()

        self.assertEqual(first_contact.id, merged_contact.id)
        self.assertEqual(merged_contact.phone, "5524999849231")
        self.assertFalse(merged_contact.is_temporary)

        identities = (
            self.db.query(ContactIdentity)
            .filter(ContactIdentity.contact_id == merged_contact.id)
            .order_by(ContactIdentity.platform_user_id.asc())
            .all()
        )
        self.assertEqual(
            [identity.platform_user_id for identity in identities],
            ["133595024851015@lid", "5524999849231"],
        )

        contact_count = self.db.query(Contact).count()
        self.assertEqual(contact_count, 1)

    def test_resolve_or_create_contact_recovers_legacy_numeric_lid_records(self) -> None:
        legacy_contact = Contact(name="Gabriel Fernandes", phone="133595024851015")
        self.db.add(legacy_contact)
        self.db.flush()
        self.db.add(
            ContactIdentity(
                contact_id=legacy_contact.id,
                platform="whatsapp",
                platform_user_id="133595024851015",
                normalized_value="133595024851015",
                is_primary=True,
                metadata_json={},
            )
        )
        self.db.commit()

        resolved_contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="5524999849231",
            profile_name="Gabriel Fernandes",
            alternate_platform_user_ids=["133595024851015@lid"],
            preferred_phone_number="5524999849231",
        )
        self.db.commit()

        self.assertEqual(resolved_contact.id, legacy_contact.id)
        self.assertEqual(resolved_contact.phone, "5524999849231")

    def test_resolve_or_create_contact_whatsapp_does_not_persist_profile_name(self) -> None:
        contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="5524999849231",
            profile_name="Nome do WhatsApp",
            preferred_phone_number="5524999849231",
        )
        self.db.commit()

        self.assertEqual(contact.phone, "5524999849231")
        self.assertIsNone(contact.name)
        self.assertFalse(contact.is_temporary)

    def test_resolve_or_create_contact_instagram_persists_profile_name(self) -> None:
        contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="instagram",
            platform_user_id="@cliente_teste",
            profile_name="Cliente Instagram",
        )
        self.db.commit()

        self.assertEqual(contact.name, "Cliente Instagram")

    def test_resolve_or_create_contact_conflict_between_phone_and_lid_does_not_merge(self) -> None:
        phone_contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="5524999849231",
            preferred_phone_number="5524999849231",
        )
        lid_contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="133595024851015@lid",
        )
        self.db.commit()
        self.assertNotEqual(phone_contact.id, lid_contact.id)

        resolution_meta: dict = {}
        resolved_contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="133595024851015@lid",
            alternate_platform_user_ids=["5524999849231"],
            preferred_phone_number="5524999849231",
            resolution_meta=resolution_meta,
        )
        self.db.commit()

        self.assertEqual(resolved_contact.id, phone_contact.id)
        self.assertTrue(resolution_meta.get("identity_conflicts"))

    def test_resolve_or_create_contact_creates_temporary_when_no_match(self) -> None:
        contact = self.service.resolve_or_create_contact(
            db=self.db,
            platform="whatsapp",
            platform_user_id="998877665544@lid",
        )
        self.db.commit()
        self.assertTrue(contact.is_temporary)


if __name__ == "__main__":
    unittest.main()
