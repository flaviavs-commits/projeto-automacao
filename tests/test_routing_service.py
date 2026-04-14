import unittest

from app.services.routing_service import RoutingService


class RoutingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RoutingService()

    def test_audio_with_media_routes_to_transcription(self) -> None:
        result = self.service.route_intent(
            {
                "platform": "whatsapp",
                "message_type": "audio",
                "has_text": False,
                "has_media": True,
            }
        )
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("route"), "transcribe_then_reply")

    def test_text_routes_to_generate_reply(self) -> None:
        result = self.service.route_intent(
            {
                "platform": "whatsapp",
                "message_type": "text",
                "has_text": True,
                "has_media": False,
            }
        )
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("route"), "generate_reply")

    def test_invalid_payload_routes_to_noop(self) -> None:
        result = self.service.route_intent(payload=None)  # type: ignore[arg-type]
        self.assertEqual(result.get("status"), "invalid_payload")
        self.assertEqual(result.get("route"), "noop")


if __name__ == "__main__":
    unittest.main()
