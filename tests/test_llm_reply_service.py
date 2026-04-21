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

        link, reason = self.service._select_cta_link("pode ser", context_messages, key_memories)  # noqa: SLF001
        self.assertEqual(link, "https://www.fcvip.com.br/agendamentos")
        self.assertEqual(reason, "agendar")

    def test_select_cta_link_for_discover_intent(self) -> None:
        context_messages = [{"role": "assistant", "text": "Posso te explicar como funciona o estudio"}]
        key_memories = [{"key": "intencao_principal", "value": "conhecer"}]

        link, reason = self.service._select_cta_link("quero ver melhor", context_messages, key_memories)  # noqa: SLF001
        self.assertEqual(link, "https://www.fcvip.com.br")
        self.assertEqual(reason, "tour")

    def test_detect_escalation_reason_for_paid_change_variations(self) -> None:
        reason = self.service._detect_escalation_reason("ja esta pago, posso mudar o dia?")  # noqa: SLF001
        self.assertEqual(reason, "cancelamento/reagendamento de horario ja pago")

    def test_detect_escalation_reason_for_group_size_without_people_keyword(self) -> None:
        reason = self.service._detect_escalation_reason("somos 6, consegue liberar?")  # noqa: SLF001
        self.assertEqual(reason, "quantidade de pessoas acima do permitido")

    def test_apply_domain_policy_guards_for_location(self) -> None:
        reply = self.service._apply_domain_policy_guards(  # noqa: SLF001
            user_text="tem estacionamento?",
            reply_text="Nao consigo confirmar essa informacao agora.",
        )
        normalized_reply = self.service._normalize_for_quality(reply)  # noqa: SLF001
        self.assertIn("corifeu marques", normalized_reply)
        self.assertIn("jardim amalia", normalized_reply)
        self.assertIn("volta redonda", normalized_reply)

    def test_apply_domain_policy_guards_for_audio(self) -> None:
        reply = self.service._apply_domain_policy_guards(  # noqa: SLF001
            user_text="fornecem microfones?",
            reply_text="Sim, temos varios modelos disponiveis.",
        )
        normalized_reply = self.service._normalize_for_quality(reply)  # noqa: SLF001
        self.assertIn("audio", normalized_reply)
        self.assertIn("nao", normalized_reply)

    def test_apply_domain_policy_guards_for_location_shopping_question(self) -> None:
        reply = self.service._apply_domain_policy_guards(  # noqa: SLF001
            user_text="fica na rua ou em shopping?",
            reply_text="Talvez em shopping, depende do local.",
        )
        normalized_reply = self.service._normalize_for_quality(reply)  # noqa: SLF001
        self.assertIn("corifeu marques", normalized_reply)
        self.assertIn("volta redonda", normalized_reply)

    def test_audio_policy_compliance_rejects_generic_technical_text(self) -> None:
        normalized_reply = self.service._normalize_for_quality(  # noqa: SLF001
            "Sim, o cliente pode usar audio para transmitir mensagens no sistema."
        )
        compliant = self.service._is_audio_policy_compliant(normalized_reply)  # noqa: SLF001
        self.assertFalse(compliant)

    def test_audio_policy_compliance_rejects_interface_without_audio_context(self) -> None:
        normalized_reply = self.service._normalize_for_quality(  # noqa: SLF001
            "Nao ha opcao padrao no interface atual para esse fluxo."
        )
        compliant = self.service._is_audio_policy_compliant(normalized_reply)  # noqa: SLF001
        self.assertFalse(compliant)

    def test_explicit_schedule_request_rejects_exploratory_wording(self) -> None:
        is_explicit = self.service._is_explicit_schedule_request(  # noqa: SLF001
            "sou novo cliente, como funciona para reservar e pagar?"
        )
        self.assertFalse(is_explicit)

    def test_explicit_schedule_request_accepts_direct_booking(self) -> None:
        is_explicit = self.service._is_explicit_schedule_request("quero reservar sexta as 18h")  # noqa: SLF001
        self.assertTrue(is_explicit)

    def test_explicit_schedule_request_accepts_time_range_without_keyword(self) -> None:
        is_explicit = self.service._is_explicit_schedule_request("precisava de 7 as 9h pode ser?")  # noqa: SLF001
        self.assertTrue(is_explicit)

    def test_generate_reply_schedule_out_of_business_hours(self) -> None:
        result = self.service.generate_reply(
            user_text="quero agendar das 7h as 9h, pode ser?",
            context_messages=[],
            key_memories=[],
        )
        self.assertEqual(result.get("model"), "rule_schedule_site_only")
        normalized_reply = self.service._normalize_for_quality(str(result.get("reply_text") or ""))  # noqa: SLF001
        self.assertIn("nesse horario nao trabalhamos", normalized_reply)
        self.assertIn("fcvip.com.br", normalized_reply)

    def test_generate_reply_values_are_routed_to_site(self) -> None:
        result = self.service.generate_reply(
            user_text="qual o valor de 2h no estudio?",
            context_messages=[],
            key_memories=[],
        )
        self.assertEqual(result.get("model"), "rule_values_site_only")
        normalized_reply = self.service._normalize_for_quality(str(result.get("reply_text") or ""))  # noqa: SLF001
        self.assertIn("pacotes e valores", normalized_reply)
        self.assertIn("fcvip.com.br", normalized_reply)

    def test_generate_reply_short_greeting_does_not_close_conversation(self) -> None:
        result = self.service.generate_reply(
            user_text="ols",
            context_messages=[
                {
                    "role": "assistant",
                    "text": "Por nada! Sempre que precisar de ajuda e so entrar em contato.",
                },
            ],
            key_memories=[],
        )
        self.assertEqual(result.get("model"), "rule_greeting")
        normalized_reply = self.service._normalize_for_quality(str(result.get("reply_text") or ""))  # noqa: SLF001
        self.assertIn("agente fc vip", normalized_reply)
        self.assertNotIn("por nada", normalized_reply)

    def test_generate_reply_greeting_first_contact_mentions_first_contact(self) -> None:
        result = self.service.generate_reply(
            user_text="ola",
            context_messages=[],
            key_memories=[],
        )
        self.assertEqual(result.get("model"), "rule_greeting")
        normalized_reply = self.service._normalize_for_quality(str(result.get("reply_text") or ""))  # noqa: SLF001
        self.assertIn("primeiro contato", normalized_reply)

    def test_should_close_conversation_rejects_thanks_with_service_intent(self) -> None:
        should_close = self.service._should_close_conversation(  # noqa: SLF001
            "obrigado, queria saber os valores de 2h"
        )
        self.assertFalse(should_close)

    def test_should_close_conversation_accepts_short_thanks(self) -> None:
        should_close = self.service._should_close_conversation("obrigado")  # noqa: SLF001
        self.assertTrue(should_close)

    def test_sanitize_unexpected_closing_for_non_final_message(self) -> None:
        sanitized = self.service._sanitize_low_quality_reply(  # noqa: SLF001
            user_text="ola",
            reply_text="Por nada! Sempre que precisar de ajuda e so entrar em contato a FC VIP agradece seu contato",
        )
        normalized = self.service._normalize_for_quality(sanitized)  # noqa: SLF001
        self.assertIn("agente fc vip", normalized)
        self.assertNotIn("por nada", normalized)

    def test_generate_reply_personal_question_redirects_to_domain(self) -> None:
        result = self.service.generate_reply(
            user_text="voce e casada?",
            context_messages=[],
            key_memories=[],
        )
        self.assertEqual(result.get("model"), "rule_domain_redirect")
        normalized_reply = self.service._normalize_for_quality(str(result.get("reply_text") or ""))  # noqa: SLF001
        self.assertIn("foco no atendimento do estudio", normalized_reply)

    def test_generate_reply_visit_experience_feedback_prompt(self) -> None:
        result = self.service.generate_reply(
            user_text="fui ai na sexta e queria te contar",
            context_messages=[],
            key_memories=[],
        )
        self.assertEqual(result.get("model"), "rule_visit_feedback")
        normalized_reply = self.service._normalize_for_quality(str(result.get("reply_text") or ""))  # noqa: SLF001
        self.assertIn("qual nota de 0 a 10", normalized_reply)

    def test_generate_reply_appends_contact_intake_when_name_missing(self) -> None:
        reply_text = self.service._append_contact_intake_if_needed(  # noqa: SLF001
            reply_text="Posso te ajudar com valores e horarios.",
            user_text="qual o valor de 2h?",
            key_memories=[],
        )
        normalized_reply = self.service._normalize_for_quality(reply_text)  # noqa: SLF001
        self.assertIn("nome completo", normalized_reply)
        self.assertIn("instagram", normalized_reply)

    def test_generate_reply_does_not_append_contact_intake_when_name_known(self) -> None:
        reply_text = self.service._append_contact_intake_if_needed(  # noqa: SLF001
            reply_text="Posso te ajudar com valores e horarios.",
            user_text="qual o valor de 2h?",
            key_memories=[{"key": "nome_contato", "value": "Gabriel"}],
        )
        normalized_reply = self.service._normalize_for_quality(reply_text)  # noqa: SLF001
        self.assertNotIn("nome completo", normalized_reply)

    def test_sanitize_low_quality_reply_for_values_intent(self) -> None:
        sanitized = self.service._sanitize_low_quality_reply(  # noqa: SLF001
            user_text="qual valor de 2h?",
            reply_text="Como assistente virtual, nao tenho acesso a informacoes especificas.",
        )
        normalized = self.service._normalize_for_quality(sanitized)  # noqa: SLF001
        self.assertIn("pacotes", normalized)
        self.assertIn("site oficial", normalized)


if __name__ == "__main__":
    unittest.main()
