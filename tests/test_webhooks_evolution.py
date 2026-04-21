import unittest

from app.api.routes.webhooks_evolution import _extract_evolution_messages
from app.schemas.webhook_evolution import EvolutionWebhookEnvelope


class EvolutionWebhookExtractionTests(unittest.TestCase):
    def test_extract_messages_upsert_text_payload(self) -> None:
        envelope = EvolutionWebhookEnvelope(
            event="messages.upsert",
            data={
                "key": {
                    "id": "ABCD1234",
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                },
                "pushName": "Cliente Teste",
                "message": {
                    "conversation": "Ola, tudo bem?",
                },
            },
        )

        extracted = _extract_evolution_messages(envelope.model_dump(mode="json"))
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].get("platform"), "whatsapp")
        self.assertEqual(extracted[0].get("platform_user_id"), "5511999999999")
        self.assertEqual(extracted[0].get("profile_name"), "Cliente Teste")
        self.assertEqual(extracted[0].get("text_content"), "Ola, tudo bem?")
        self.assertEqual(extracted[0].get("external_message_id"), "ABCD1234")

    def test_extract_messages_supports_extended_text_message(self) -> None:
        envelope = EvolutionWebhookEnvelope(
            event="messages.upsert",
            data={
                "key": {
                    "id": "XYZ-1",
                    "remoteJid": "5511888888888@c.us",
                    "fromMe": False,
                },
                "message": {
                    "extendedTextMessage": {
                        "text": "Mensagem extended",
                    }
                },
            },
        )

        extracted = _extract_evolution_messages(envelope.model_dump(mode="json"))
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0].get("platform_user_id"), "5511888888888")
        self.assertEqual(extracted[0].get("text_content"), "Mensagem extended")

    def test_extract_messages_ignores_from_me(self) -> None:
        envelope = EvolutionWebhookEnvelope(
            event="messages.upsert",
            data={
                "key": {
                    "id": "SELF1",
                    "remoteJid": "5511777777777@s.whatsapp.net",
                    "fromMe": True,
                },
                "message": {
                    "conversation": "Mensagem enviada pelo bot",
                },
            },
        )

        extracted = _extract_evolution_messages(envelope.model_dump(mode="json"))
        self.assertEqual(extracted, [])


if __name__ == "__main__":
    unittest.main()
