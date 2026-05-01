import unittest
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.services.whatsapp_service import WhatsAppService


class WhatsAppServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WhatsAppService()
        self.original_provider = settings.whatsapp_provider
        self.original_gateway_base_url = settings.whatsapp_gateway_base_url
        self.original_gateway_api_key = settings.whatsapp_gateway_api_key
        self.original_session_name = settings.whatsapp_session_name
        self.original_base_url = settings.evolution_api_base_url
        self.original_api_key = settings.evolution_api_key
        self.original_instance_name = settings.evolution_instance_name

        settings.whatsapp_provider = "evolution"
        settings.whatsapp_gateway_base_url = ""
        settings.whatsapp_gateway_api_key = ""
        settings.whatsapp_session_name = ""
        settings.evolution_api_base_url = "https://evolution.example"
        settings.evolution_api_key = "test-api-key"
        settings.evolution_instance_name = "main-instance"

    def tearDown(self) -> None:
        settings.whatsapp_provider = self.original_provider
        settings.whatsapp_gateway_base_url = self.original_gateway_base_url
        settings.whatsapp_gateway_api_key = self.original_gateway_api_key
        settings.whatsapp_session_name = self.original_session_name
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

    def test_send_text_message_uses_baileys_gateway_when_provider_selected(self) -> None:
        settings.whatsapp_provider = "baileys"
        settings.whatsapp_gateway_base_url = "https://gateway.example"
        settings.whatsapp_gateway_api_key = "gateway-api-key"
        settings.whatsapp_session_name = "sales-session"

        request = httpx.Request(
            "POST",
            "https://gateway.example/message/sendText/sales-session",
        )
        response = httpx.Response(
            200,
            request=request,
            json={"messageId": "BAILEYS_MSG_ID"},
        )

        with patch("app.services.base.httpx.Client.request", return_value=response) as request_mock:
            result = self.service.send_text_message(
                {
                    "to": "+55 11 99999-9999",
                    "text": "Ola via gateway!",
                }
            )

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(result.get("message_id"), "BAILEYS_MSG_ID")

        request_kwargs = request_mock.call_args.kwargs
        self.assertEqual(request_kwargs.get("url"), "https://gateway.example/message/sendText/sales-session")
        self.assertEqual(request_kwargs.get("method"), "POST")
        self.assertEqual(
            request_kwargs.get("headers"),
            {"apikey": "gateway-api-key", "Content-Type": "application/json"},
        )
        self.assertEqual(request_kwargs.get("json"), {"number": "5511999999999", "text": "Ola via gateway!"})

    def test_send_text_message_missing_baileys_gateway_credentials(self) -> None:
        settings.whatsapp_provider = "baileys"
        settings.whatsapp_gateway_base_url = ""
        settings.whatsapp_session_name = ""

        result = self.service.send_text_message(
            {
                "to": "5511999999999",
                "text": "Ola",
            }
        )

        self.assertEqual(result.get("status"), "missing_credentials")
        self.assertIn("WHATSAPP_GATEWAY_BASE_URL", result.get("required") or [])
        self.assertIn("WHATSAPP_SESSION_NAME", result.get("required") or [])

    def test_send_text_message_rejects_lid_recipient(self) -> None:
        settings.whatsapp_provider = "baileys"
        settings.whatsapp_gateway_base_url = "https://gateway.example"
        settings.whatsapp_gateway_api_key = "gateway-api-key"
        settings.whatsapp_session_name = "sales-session"

        result = self.service.send_text_message(
            {
                "to": "133595024851015@lid",
                "text": "Ola",
            }
        )

        self.assertEqual(result.get("status"), "invalid_payload")

    def test_send_text_message_ignores_group_jid(self) -> None:
        with patch("app.services.base.httpx.Client.request") as request_mock:
            result = self.service.send_text_message(
                {
                    "to": "120363111111111111@g.us",
                    "text": "Ola grupo",
                }
            )

        self.assertEqual(result.get("status"), "ignored_group_jid")
        self.assertEqual(request_mock.call_count, 0)

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

    def test_send_text_message_retries_after_gateway_session_closed(self) -> None:
        settings.whatsapp_provider = "baileys"
        settings.whatsapp_gateway_base_url = "https://gateway.example"
        settings.whatsapp_gateway_api_key = "gateway-api-key"
        settings.whatsapp_session_name = "sales-session"

        send_request = httpx.Request(
            "POST",
            "https://gateway.example/message/sendText/sales-session",
        )
        state_request = httpx.Request(
            "GET",
            "https://gateway.example/instance/connectionState/sales-session",
        )
        connect_request = httpx.Request(
            "GET",
            "https://gateway.example/instance/connect/sales-session",
        )

        first_send = httpx.Response(
            409,
            request=send_request,
            json={"error": {"message": "session_not_open"}},
        )
        state_response = httpx.Response(
            200,
            request=state_request,
            json={"instance": {"instanceName": "sales-session", "state": "close"}},
        )
        connect_response = httpx.Response(
            200,
            request=connect_request,
            json={"base64": "data:image/png;base64,abcd", "pairingCode": None},
        )
        second_send = httpx.Response(
            200,
            request=send_request,
            json={"messageId": "BAILEYS_RETRIED_MSG_ID"},
        )

        with patch(
            "app.services.base.httpx.Client.request",
            side_effect=[first_send, state_response, connect_response, second_send],
        ) as request_mock:
            result = self.service.send_text_message(
                {
                    "to": "5511999999999",
                    "text": "Ola!",
                }
            )

        self.assertEqual(result.get("status"), "completed")
        self.assertEqual(result.get("message_id"), "BAILEYS_RETRIED_MSG_ID")
        self.assertTrue(result.get("retried"))
        self.assertEqual(result.get("reconnect_attempt", {}).get("status"), "connect_triggered")
        self.assertEqual(request_mock.call_count, 4)


if __name__ == "__main__":
    unittest.main()
