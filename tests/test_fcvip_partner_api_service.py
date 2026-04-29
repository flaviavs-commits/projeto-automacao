import unittest
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.services.fcvip_partner_api_service import FCVIPPartnerAPIService


class FCVIPPartnerAPIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FCVIPPartnerAPIService()
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

    def test_lookup_requires_credentials(self) -> None:
        settings.fcvip_partner_api_key = ""
        result = self.service.lookup_customer_by_whatsapp(phone_number="5511999999999")
        self.assertEqual(result.get("status"), "missing_credentials")
        self.assertIn("FCVIP_PARTNER_API_KEY", result.get("required") or [])

    def test_lookup_matches_whatsapp_in_leads(self) -> None:
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
                    "leads": [
                        {"id": 10, "whatsapp": "5511888888888"},
                        {"id": 11, "whatsapp": "5511999999999"},
                    ],
                    "total_pages": 1,
                },
            },
        )

        with patch("app.services.base.httpx.Client.request", return_value=response):
            result = self.service.lookup_customer_by_whatsapp(phone_number="+55 (11) 99999-9999")

        self.assertEqual(result.get("status"), "completed")
        self.assertTrue(result.get("customer_exists"))
        self.assertEqual(result.get("matched_lead_id"), 11)

    def test_lookup_returns_new_customer_when_not_found(self) -> None:
        request = httpx.Request(
            "GET",
            "https://vs-production-c4dd.up.railway.app/api/partner/leads/",
        )
        first_page = httpx.Response(
            200,
            request=request,
            json={
                "success": True,
                "data": {
                    "leads": [{"id": 1, "whatsapp": "5511888888888"}],
                    "total_pages": 2,
                },
            },
        )
        second_page = httpx.Response(
            200,
            request=request,
            json={
                "success": True,
                "data": {
                    "leads": [{"id": 2, "whatsapp": "5511777777777"}],
                    "total_pages": 2,
                },
            },
        )

        with patch("app.services.base.httpx.Client.request", side_effect=[first_page, second_page]):
            result = self.service.lookup_customer_by_whatsapp(phone_number="5511999999999")

        self.assertEqual(result.get("status"), "completed")
        self.assertFalse(result.get("customer_exists"))
        self.assertEqual(result.get("customer_status"), "novo")

    def test_lookup_maps_partner_error(self) -> None:
        request = httpx.Request(
            "GET",
            "https://vs-production-c4dd.up.railway.app/api/partner/leads/",
        )
        response = httpx.Response(
            403,
            request=request,
            json={"detail": "Invalid API key"},
        )

        with patch("app.services.base.httpx.Client.request", return_value=response):
            result = self.service.lookup_customer_by_whatsapp(phone_number="5511999999999")

        self.assertEqual(result.get("status"), "request_failed")
        self.assertEqual(result.get("status_code"), 403)


if __name__ == "__main__":
    unittest.main()
