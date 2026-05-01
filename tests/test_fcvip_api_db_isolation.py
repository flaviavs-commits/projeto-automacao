import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.models.contact import Contact
from app.models.contact_memory import ContactMemory
from app.services.dashboard_op_service import DashboardOpService
from app.services.fcvip_partner_api_service import FCVIPPartnerAPIService


class FCVIPApiDbIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()
        self.service = FCVIPPartnerAPIService()
        self.service._lookup_cache.clear()

        self.original_enabled = settings.fcvip_partner_api_enabled
        self.original_base_url = settings.fcvip_partner_api_base_url
        self.original_api_key = settings.fcvip_partner_api_key
        self.original_timeout = settings.fcvip_partner_api_timeout_seconds
        self.original_page_size = settings.fcvip_partner_api_page_size
        self.original_max_pages = settings.fcvip_partner_api_leads_max_pages

        settings.fcvip_partner_api_enabled = True
        settings.fcvip_partner_api_base_url = "https://vs-production-c4dd.up.railway.app"
        settings.fcvip_partner_api_key = "partner-test-key"
        settings.fcvip_partner_api_timeout_seconds = 10
        settings.fcvip_partner_api_page_size = 50
        settings.fcvip_partner_api_leads_max_pages = 3

    def tearDown(self) -> None:
        settings.fcvip_partner_api_enabled = self.original_enabled
        settings.fcvip_partner_api_base_url = self.original_base_url
        settings.fcvip_partner_api_key = self.original_api_key
        settings.fcvip_partner_api_timeout_seconds = self.original_timeout
        settings.fcvip_partner_api_page_size = self.original_page_size
        settings.fcvip_partner_api_leads_max_pages = self.original_max_pages
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_lookup_customer_by_whatsapp_does_not_create_contacts(self) -> None:
        request = httpx.Request(
            "GET",
            "https://vs-production-c4dd.up.railway.app/api/partner/leads/",
        )
        response = httpx.Response(
            200,
            request=request,
            json={
                "success": True,
                "data": {
                    "leads": [{"id": 11, "whatsapp": "5511999999999"}],
                    "total_pages": 1,
                },
            },
        )

        with patch("app.services.base.httpx.Client.request", return_value=response):
            result = self.service.lookup_customer_by_whatsapp(phone_number="5511999999999")

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(self.db.query(Contact).count(), 0)

    def test_dashboard_contact_detail_works_with_api_disabled(self) -> None:
        settings.fcvip_partner_api_enabled = False
        contact = Contact(name="Ana", phone="5511988887777")
        self.db.add(contact)
        self.db.commit()

        payload = DashboardOpService().get_contact_detail(db=self.db, contact_id=contact.id)

        self.assertIsNotNone(payload)
        self.assertEqual((payload or {}).get("fcvip_api", {}).get("status"), "integration_disabled")
        self.assertIn("message", (payload or {}).get("fcvip_api", {}))
        self.assertEqual(self.db.query(Contact).count(), 1)

    def test_dashboard_contact_detail_fcvip_lookup_keeps_local_rows_unchanged(self) -> None:
        contact = Contact(name="Bruno", phone="5511977776666")
        self.db.add(contact)
        self.db.flush()
        self.db.add(
            ContactMemory(
                contact_id=contact.id,
                source_message_id=None,
                memory_key="interesse",
                memory_value="agendamento",
                status="active",
                importance=4,
                confidence=0.9,
            )
        )
        self.db.commit()

        with patch(
            "app.services.dashboard_op_service.FCVIPPartnerAPIService.lookup_customer_by_whatsapp",
            return_value={"status": "completed", "customer_exists": True, "customer_status": "antigo", "checked_pages": 1},
        ):
            payload = DashboardOpService().get_contact_detail(db=self.db, contact_id=contact.id)

        self.assertIsNotNone(payload)
        self.assertEqual((payload or {}).get("fcvip_api", {}).get("status"), "completed")
        self.assertEqual(self.db.query(Contact).count(), 1)
        self.assertEqual(self.db.query(ContactMemory).count(), 1)


if __name__ == "__main__":
    unittest.main()
