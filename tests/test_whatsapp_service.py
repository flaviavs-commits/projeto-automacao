import unittest
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.services.whatsapp_service import WhatsAppService


class WhatsAppServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WhatsAppService()
        self.original_base_url = settings.evolution_api_base_url
        self.original_api_key = settings.evolution_api_key
        self.original_instance_name = settings.evolution_instance_name

        settings.evolution_api_base_url = "https://evolution.example"
        settings.evolution_api_key = "test-api-key"
        settings.evolution_instance_name = "main-instance"

    def tearDown(self) -> None:
        settings.evolution_api_base_url = self.original_base_url
        settings.evolution_api_key = self.original_api_key
        settings.evolution_instance_name = self.original_instance_name

    def test_send_text_message_uses_evolution_http_endpoint(self) -> None:
        request = httpx.Request(
            "POST",
            "https://evolution.example/message/sendText/main-instance",
        )
        response = httpx.Response(
            200,
            request=request,
            json={"key": {"id": "EVOLUTION_MSG_ID"}},
        )

        with patch("app.services.base.httpx.Client.request", return_value=response) as request_mock:
            result = self.service.send_text_message(
                {
                    "to": "5511999999999@s.whatsapp.net",
                    "text": "Ola!",
                }
            )

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(result.get("message_id"), "EVOLUTION_MSG_ID")
        self.assertEqual(result.get("action"), "send_text_message")

        request_kwargs = request_mock.call_args.kwargs
        self.assertEqual(request_kwargs.get("url"), "https://evolution.example/message/sendText/main-instance")
        self.assertEqual(request_kwargs.get("method"), "POST")
        self.assertEqual(request_kwargs.get("headers"), {"apikey": "test-api-key", "Content-Type": "application/json"})
        self.assertEqual(request_kwargs.get("json"), {"number": "5511999999999", "text": "Ola!"})

    def test_send_text_message_missing_evolution_credentials(self) -> None:
        settings.evolution_api_key = ""

        result = self.service.send_text_message(
            {
                "to": "5511999999999",
                "text": "Ola",
            }
        )

        self.assertEqual(result.get("status"), "missing_credentials")
        self.assertIn("EVOLUTION_API_KEY", result.get("required") or [])

    def test_send_text_message_maps_http_error_to_request_failed(self) -> None:
        request = httpx.Request(
            "POST",
            "https://evolution.example/message/sendText/main-instance",
        )
        response = httpx.Response(
            401,
            request=request,
            json={"error": {"message": "invalid apikey"}},
        )

        with patch("app.services.base.httpx.Client.request", return_value=response):
            result = self.service.send_text_message(
                {
                    "to": "5511999999999",
                    "text": "Ola",
                }
            )

        self.assertEqual(result.get("status"), "request_failed")
        self.assertEqual(result.get("status_code"), 401)

    def test_send_text_message_retries_after_connection_closed(self) -> None:
        send_request = httpx.Request(
            "POST",
            "https://evolution.example/message/sendText/main-instance",
        )
        state_request = httpx.Request(
            "GET",
            "https://evolution.example/instance/connectionState/main-instance",
        )
        connect_request = httpx.Request(
            "GET",
            "https://evolution.example/instance/connect/main-instance",
        )

        first_send = httpx.Response(
            500,
            request=send_request,
            json={"message": "Connection Closed"},
        )
        state_response = httpx.Response(
            200,
            request=state_request,
            json={"instance": {"instanceName": "main-instance", "state": "close"}},
        )
        connect_response = httpx.Response(
            200,
            request=connect_request,
            json={"base64": "data:image/png;base64,abcd", "pairingCode": None},
        )
        second_send = httpx.Response(
            200,
            request=send_request,
            json={"key": {"id": "EVOLUTION_RETRIED_MSG_ID"}},
        )

        with patch(
            "app.services.base.httpx.Client.request",
            side_effect=[first_send, state_response, connect_response, second_send],
        ) as request_mock:
            result = self.service.send_text_message(
                {
                    "to": "5511999999999@s.whatsapp.net",
                    "text": "Ola!",
                }
            )

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(result.get("message_id"), "EVOLUTION_RETRIED_MSG_ID")
        self.assertTrue(result.get("retried"))
        self.assertEqual(result.get("reconnect_attempt", {}).get("status"), "connect_triggered")
        self.assertEqual(request_mock.call_count, 4)


if __name__ == "__main__":
    unittest.main()
