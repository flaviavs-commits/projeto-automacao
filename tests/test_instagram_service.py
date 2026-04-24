import unittest
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.services.instagram_service import InstagramService


class InstagramServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InstagramService()
        self.original_meta_enabled = settings.meta_enabled
        self.original_graph_base_url = settings.meta_graph_base_url
        self.original_meta_api_version = settings.meta_api_version
        self.original_instagram_business_account_id = settings.instagram_business_account_id
        self.original_meta_access_token = settings.meta_access_token

        settings.meta_enabled = True
        settings.meta_graph_base_url = "https://graph.facebook.com"
        settings.meta_api_version = "v23.0"
        settings.instagram_business_account_id = "17841440950793819"
        settings.meta_access_token = "env-meta-token"

    def tearDown(self) -> None:
        settings.meta_enabled = self.original_meta_enabled
        settings.meta_graph_base_url = self.original_graph_base_url
        settings.meta_api_version = self.original_meta_api_version
        settings.instagram_business_account_id = self.original_instagram_business_account_id
        settings.meta_access_token = self.original_meta_access_token

    @patch("app.services.instagram_service.PlatformAccountService.resolve_meta_credentials")
    def test_send_text_message_uses_graph_messages_endpoint(self, resolve_meta_credentials_mock) -> None:
        resolve_meta_credentials_mock.return_value = {
            "access_token": "oauth-token",
            "instagram_business_account_id": "17841440950793819",
        }

        lookup_request = httpx.Request(
            "GET",
            "https://graph.facebook.com/v23.0/me/accounts",
        )
        lookup_response = httpx.Response(
            200,
            request=lookup_request,
            json={
                "data": [
                    {
                        "id": "983332878206687",
                        "instagram_business_account": {"id": "17841440950793819"},
                        "access_token": "page-token",
                    }
                ]
            },
        )
        send_request = httpx.Request(
            "POST",
            "https://graph.facebook.com/v23.0/17841440950793819/messages",
        )
        send_response = httpx.Response(
            200,
            request=send_request,
            json={"message_id": "mid.abc123"},
        )

        with patch(
            "app.services.base.httpx.Client.request",
            side_effect=[lookup_response, send_response],
        ) as request_mock:
            result = self.service.send_text_message(
                {
                    "to": "900001111222333",
                    "text": "Ola via instagram",
                }
            )

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(result.get("message_id"), "mid.abc123")
        self.assertEqual(result.get("action"), "send_text_message")
        self.assertEqual(result.get("page_id"), "983332878206687")

        lookup_kwargs = request_mock.call_args_list[0].kwargs
        self.assertEqual(lookup_kwargs.get("url"), "https://graph.facebook.com/v23.0/me/accounts")
        self.assertEqual(lookup_kwargs.get("method"), "GET")

        request_kwargs = request_mock.call_args_list[1].kwargs
        self.assertEqual(
            request_kwargs.get("url"),
            "https://graph.facebook.com/v23.0/17841440950793819/messages",
        )
        self.assertEqual(request_kwargs.get("method"), "POST")
        sent_form = request_kwargs.get("data") or {}
        self.assertEqual(sent_form.get("access_token"), "page-token")
        self.assertIn('"id":"900001111222333"', sent_form.get("recipient", ""))
        self.assertIn('"text":"Ola via instagram"', sent_form.get("message", ""))

    def test_send_text_message_requires_recipient_and_text(self) -> None:
        result = self.service.send_text_message({"to": "", "text": ""})
        self.assertEqual(result.get("status"), "invalid_payload")

    @patch("app.services.instagram_service.PlatformAccountService.resolve_meta_credentials")
    def test_send_text_message_missing_credentials(self, resolve_meta_credentials_mock) -> None:
        resolve_meta_credentials_mock.return_value = {
            "access_token": "",
            "instagram_business_account_id": "",
        }
        settings.meta_access_token = ""
        settings.instagram_business_account_id = ""

        result = self.service.send_text_message(
            {
                "to": "900001111222333",
                "text": "Oi",
            }
        )

        self.assertEqual(result.get("status"), "missing_credentials")
        self.assertIn("INSTAGRAM_BUSINESS_ACCOUNT_ID (or OAuth metadata)", result.get("required") or [])

    @patch("app.services.instagram_service.PlatformAccountService.resolve_meta_credentials")
    def test_send_text_message_maps_http_error_to_request_failed(self, resolve_meta_credentials_mock) -> None:
        resolve_meta_credentials_mock.return_value = {
            "access_token": "oauth-token",
            "instagram_business_account_id": "17841440950793819",
        }

        lookup_request = httpx.Request(
            "GET",
            "https://graph.facebook.com/v23.0/me/accounts",
        )
        lookup_response = httpx.Response(
            200,
            request=lookup_request,
            json={
                "data": [
                    {
                        "id": "983332878206687",
                        "instagram_business_account": {"id": "17841440950793819"},
                        "access_token": "page-token",
                    }
                ]
            },
        )
        send_request = httpx.Request(
            "POST",
            "https://graph.facebook.com/v23.0/17841440950793819/messages",
        )
        send_response = httpx.Response(
            400,
            request=send_request,
            json={"error": {"message": "Unsupported post request."}},
        )

        with patch(
            "app.services.base.httpx.Client.request",
            side_effect=[lookup_response, send_response],
        ):
            result = self.service.send_text_message(
                {
                    "to": "900001111222333",
                    "text": "Ola",
                }
            )

        self.assertEqual(result.get("status"), "request_failed")
        self.assertEqual(result.get("status_code"), 400)


if __name__ == "__main__":
    unittest.main()
