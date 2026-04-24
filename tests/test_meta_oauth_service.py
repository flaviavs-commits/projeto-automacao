import unittest
from unittest.mock import patch

import httpx

from app.core.config import settings
from app.services.meta_oauth_service import MetaOAuthService


class MetaOAuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MetaOAuthService()
        self.original_graph = settings.meta_graph_base_url
        self.original_api_version = settings.meta_api_version
        settings.meta_graph_base_url = "https://graph.facebook.com"
        settings.meta_api_version = "v23.0"

    def tearDown(self) -> None:
        settings.meta_graph_base_url = self.original_graph
        settings.meta_api_version = self.original_api_version

    def test_subscribe_instagram_app_calls_subscribed_apps_endpoint(self) -> None:
        request = httpx.Request(
            "POST",
            "https://graph.facebook.com/v23.0/17841440950793819/subscribed_apps",
        )
        response = httpx.Response(200, request=request, json={"success": True})

        with patch("app.services.base.httpx.Client.request", return_value=response) as request_mock:
            result = self.service.subscribe_instagram_app(
                instagram_business_account_id="17841440950793819",
                access_token="token_abc",
            )

        self.assertEqual(result.get("status"), "ok")
        kwargs = request_mock.call_args.kwargs
        self.assertEqual(kwargs.get("method"), "POST")
        self.assertEqual(
            kwargs.get("url"),
            "https://graph.facebook.com/v23.0/17841440950793819/subscribed_apps",
        )
        self.assertEqual(
            kwargs.get("data"),
            {
                "subscribed_fields": "messages,messaging_postbacks,message_reactions,messaging_seen",
                "access_token": "token_abc",
            },
        )


if __name__ == "__main__":
    unittest.main()
