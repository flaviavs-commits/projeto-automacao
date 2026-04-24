import unittest

from app.api.routes.webhooks_meta import _extract_meta_messages


class MetaWebhookExtractionTests(unittest.TestCase):
    def test_defaults_to_instagram_when_object_is_instagram_and_messaging_product_missing(self) -> None:
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "17841440950793819",
                    "messaging": [
                        {
                            "sender": {"id": "900001111222333", "name": "Tester"},
                            "recipient": {"id": "17841440950793819"},
                            "timestamp": 1777000000000,
                            "message": {"mid": "ig-mid-001", "text": "real-03"},
                        }
                    ],
                }
            ],
        }

        extracted = _extract_meta_messages(payload)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].get("platform"), "instagram")
        self.assertEqual(extracted[0].get("platform_user_id"), "900001111222333")
        self.assertEqual(extracted[0].get("external_message_id"), "ig-mid-001")

    def test_defaults_to_facebook_when_object_is_page_and_messaging_product_missing(self) -> None:
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "123",
                    "messaging": [
                        {
                            "sender": {"id": "42", "name": "FB Tester"},
                            "recipient": {"id": "page-id"},
                            "timestamp": 1777000000000,
                            "message": {"mid": "fb-mid-001", "text": "hello"},
                        }
                    ],
                }
            ],
        }

        extracted = _extract_meta_messages(payload)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].get("platform"), "facebook")
        self.assertEqual(extracted[0].get("platform_user_id"), "42")


if __name__ == "__main__":
    unittest.main()
