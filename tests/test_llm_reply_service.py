import unittest

from app.core.config import settings
from app.services.llm_reply_service import LLMReplyService


class LLMReplyServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = LLMReplyService()

    def test_build_messages_limits_context_window(self) -> None:
        context_messages = []
        for idx in range(10):
            role = "user" if idx % 2 == 0 else "assistant"
            context_messages.append({"role": role, "text": f"mensagem {idx}"})

        messages = self.service._build_messages(  # noqa: SLF001
            user_text="quero seguir",
            context_messages=context_messages,
            key_memories=[],
        )

        expected_window = settings.llm_effective_context_messages
        self.assertEqual(len(messages), 1 + expected_window + 1)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-1]["content"], "quero seguir")

    def test_select_cta_link_uses_context_and_memory_for_follow_up(self) -> None:
        context_messages = [
            {"role": "user", "text": "Oi, quero agendar para semana que vem"},
            {"role": "assistant", "text": "Perfeito, me confirma o horario desejado"},
        ]
        key_memories = [
            {"key": "intencao_principal", "value": "agendar"},
            {"key": "cliente_status", "value": "antigo"},
        ]

        link = self.service._select_cta_link("pode ser", context_messages, key_memories)  # noqa: SLF001
        self.assertEqual(link, "https://www.fcvip.com.br/agendamentos")

    def test_select_cta_link_for_discover_intent(self) -> None:
        context_messages = [{"role": "assistant", "text": "Posso te explicar como funciona o estudio"}]
        key_memories = [{"key": "intencao_principal", "value": "conhecer"}]

        link = self.service._select_cta_link("quero ver melhor", context_messages, key_memories)  # noqa: SLF001
        self.assertEqual(link, "https://www.fcvip.com.br")


if __name__ == "__main__":
    unittest.main()
