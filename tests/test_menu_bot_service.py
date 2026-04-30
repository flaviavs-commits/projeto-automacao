import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services.menu_bot_service import MenuBotService


class MenuBotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MenuBotService()

    def _contact(self, *, name=None, phone=None, email=None, is_temporary=False):
        return SimpleNamespace(name=name, phone=phone, email=email, is_temporary=is_temporary)

    def _conversation(self, *, menu_state=None, is_new=True):
        return SimpleNamespace(menu_state=menu_state, is_new_chat=is_new)

    def _run(
        self,
        *,
        text: str,
        state: str | None,
        customer_exists: bool,
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        identities: list[dict] | None = None,
        memories: list[dict] | None = None,
        collection_data: dict | None = None,
    ) -> dict:
        return self.service.handle_message(
            message_text=text,
            conversation=self._conversation(menu_state=state, is_new=state is None),
            contact=self._contact(name=name, phone=phone, email=email, is_temporary=not customer_exists),
            customer_exists=customer_exists,
            identities=identities or [],
            memories=memories or [],
            collection_data=collection_data or {},
        )

    def test_new_chat_unknown_customer_collects_name_first(self) -> None:
        result = self._run(text="oi", state=None, customer_exists=False)
        self.assertEqual(result["next_state"], "collect_name")
        self.assertIn("etapa 1 de 5", result["reply_text"].lower())
        self.assertNotIn("1 - agendamento", result["reply_text"].lower())

    def test_new_chat_existing_customer_gets_welcome_menu(self) -> None:
        result = self._run(text="oi", state=None, customer_exists=True, name="Flavia Lima")
        self.assertEqual(result["next_state"], "main_menu")
        self.assertIn("ola, flavia lima", result["reply_text"].lower())
        self.assertIn("1 - agendamento", result["reply_text"].lower())

    def test_unknown_customer_cannot_open_menu_before_collection(self) -> None:
        result = self._run(text="1", state="collect_name", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_name")
        self.assertIn("nome completo", result["reply_text"].lower())

    def test_unknown_customer_cannot_receive_price_before_collection(self) -> None:
        result = self._run(text="2", state="collect_phone", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_phone")
        self.assertNotIn("r$130", result["reply_text"].lower())

    def test_unknown_customer_cannot_receive_booking_link_before_collection(self) -> None:
        result = self._run(text="1", state="collect_email", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_email")
        self.assertNotIn("/formulario", result["reply_text"].lower())
        self.assertNotIn("/agendamentos", result["reply_text"].lower())

    def test_name_is_required(self) -> None:
        result = self._run(text=" ", state="collect_name", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_name")
        self.assertIn("nome completo", result["reply_text"].lower())

    def test_name_must_have_two_words(self) -> None:
        result = self._run(text="Maria", state="collect_name", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_name")
        self.assertIn("nome completo", result["reply_text"].lower())

    def test_invalid_name_repeats_collect_name(self) -> None:
        result = self._run(text="123456", state="collect_name", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_name")
        self.assertIn("nome completo", result["reply_text"].lower())

    def test_valid_name_goes_to_collect_phone(self) -> None:
        result = self._run(text="Maria Silva", state="collect_name", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_phone")
        self.assertIn("etapa 2 de 5", result["reply_text"].lower())
        self.assertEqual(result["collected_customer_data"]["name"], "Maria Silva")

    def test_phone_is_required(self) -> None:
        result = self._run(text="", state="collect_phone", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_phone")
        self.assertIn("telefone", result["reply_text"].lower())

    def test_phone_invalid_repeats_collect_phone(self) -> None:
        result = self._run(text="abc", state="collect_phone", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_phone")
        self.assertIn("telefone", result["reply_text"].lower())

    def test_phone_repeated_sequence_is_invalid(self) -> None:
        result = self._run(text="11111111111", state="collect_phone", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_phone")
        self.assertIn("nao parece valido", result["reply_text"].lower())

    def test_phone_is_normalized_to_e164(self) -> None:
        result = self._run(text="+55 (24) 99999-9999", state="collect_phone", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_email")
        self.assertEqual(result["collected_customer_data"]["phone_normalized"], "+5524999999999")
        self.assertEqual(result["collected_customer_data"]["phone_original"], "+55 (24) 99999-9999")

    def test_email_is_required(self) -> None:
        result = self._run(text=" ", state="collect_email", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_email")
        self.assertIn("email", result["reply_text"].lower())

    def test_email_invalid_repeats_collect_email(self) -> None:
        result = self._run(text="sem-arroba", state="collect_email", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_email")
        self.assertIn("email", result["reply_text"].lower())

    def test_valid_email_advances_to_instagram(self) -> None:
        result = self._run(text="Cliente@Email.com", state="collect_email", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_instagram")
        self.assertIn("etapa 4 de 5", result["reply_text"].lower())
        self.assertEqual(result["collected_customer_data"]["email"], "cliente@email.com")

    def test_instagram_is_asked_as_step_4(self) -> None:
        result = self._run(text="ok@email.com", state="collect_email", customer_exists=False)
        self.assertIn("etapa 4 de 5", result["reply_text"].lower())
        self.assertIn("instagram", result["reply_text"].lower())

    def test_instagram_valid_is_saved(self) -> None:
        result = self._run(
            text="https://instagram.com/fc.vip",
            state="collect_instagram",
            customer_exists=False,
            collection_data={
                "name": "Maria Silva",
                "phone_original": "24999999999",
                "phone_normalized": "+5524999999999",
                "email": "maria@email.com",
            },
        )
        self.assertEqual(result["next_state"], "collect_facebook")
        self.assertEqual(result["collected_customer_data"]["instagram"], "@fc.vip")

    def test_instagram_skip_terms_do_not_block(self) -> None:
        for term in ("0", "pular", "nao tenho", "nao", ""):
            result = self._run(
                text=term,
                state="collect_instagram",
                customer_exists=False,
                collection_data={
                    "name": "Maria Silva",
                    "phone_original": "24999999999",
                    "phone_normalized": "+5524999999999",
                    "email": "maria@email.com",
                },
            )
            self.assertEqual(result["next_state"], "collect_facebook")

    def test_facebook_is_asked_as_step_5(self) -> None:
        result = self._run(text="@fcvip", state="collect_instagram", customer_exists=False)
        self.assertIn("etapa 5 de 5", result["reply_text"].lower())
        self.assertIn("facebook", result["reply_text"].lower())

    def test_facebook_valid_is_saved(self) -> None:
        result = self._run(
            text="facebook.com/fc.vip",
            state="collect_facebook",
            customer_exists=False,
            collection_data={
                "name": "Maria Silva",
                "phone_original": "24999999999",
                "phone_normalized": "+5524999999999",
                "email": "maria@email.com",
                "instagram": "@fcvip",
            },
        )
        self.assertEqual(result["next_state"], "main_menu")
        self.assertEqual(result["collected_customer_data"]["facebook"], "fc.vip")

    def test_facebook_skip_terms_do_not_block(self) -> None:
        for term in ("0", "pular", "nao tenho", "nao", ""):
            result = self._run(
                text=term,
                state="collect_facebook",
                customer_exists=False,
                collection_data={
                    "name": "Maria Silva",
                    "phone_original": "24999999999",
                    "phone_normalized": "+5524999999999",
                    "email": "maria@email.com",
                    "instagram": None,
                },
            )
            self.assertEqual(result["next_state"], "main_menu")

    def test_required_fields_complete_registration_without_instagram_or_facebook(self) -> None:
        result = self._run(
            text="nao",
            state="collect_facebook",
            customer_exists=False,
            collection_data={
                "name": "Maria Silva",
                "phone_original": "24999999999",
                "phone_normalized": "+5524999999999",
                "email": "maria@email.com",
                "instagram": None,
            },
        )
        self.assertEqual(result["next_state"], "main_menu")
        self.assertIn("cadastro concluido", result["reply_text"].lower())

    def test_after_registration_main_menu_is_displayed(self) -> None:
        result = self._run(
            text="nao",
            state="collect_facebook",
            customer_exists=False,
            collection_data={
                "name": "Maria Silva",
                "phone_original": "24999999999",
                "phone_normalized": "+5524999999999",
                "email": "maria@email.com",
            },
        )
        self.assertIn("1 - agendamento", result["reply_text"].lower())
        self.assertIn("2 - valores", result["reply_text"].lower())

    def test_existing_customer_skips_collection(self) -> None:
        result = self._run(text="menu", state="main_menu", customer_exists=True, name="Flavia")
        self.assertEqual(result["next_state"], "main_menu")
        self.assertNotIn("etapa 1 de 5", result["reply_text"].lower())

    def test_existing_customer_booking_is_agendamentos(self) -> None:
        result = self._run(text="1", state="main_menu", customer_exists=True, name="Flavia")
        self.assertIn("/agendamentos", result["reply_text"].lower())
        self.assertNotIn("/formulario", result["reply_text"].lower())

    def test_new_customer_booking_is_formulario(self) -> None:
        result = self._run(text="1", state="main_menu", customer_exists=False, name="Novo")
        self.assertIn("/formulario", result["reply_text"].lower())

    def test_old_customer_never_receives_formulario(self) -> None:
        result = self._run(text="1", state="location_menu", customer_exists=True, name="Flavia")
        self.assertIn("/agendamentos", result["reply_text"].lower())
        self.assertNotIn("/formulario", result["reply_text"].lower())

    def test_main_menu_option_2_opens_pricing_menu(self) -> None:
        result = self._run(text="2", state="main_menu", customer_exists=True, name="Flavia")
        self.assertEqual(result["next_state"], "pricing_menu")

    def test_pricing_menu_option_1_returns_price(self) -> None:
        result = self._run(text="1", state="pricing_menu", customer_exists=True, name="Flavia")
        lowered = result["reply_text"].lower()
        self.assertIn("1 hora", lowered)
        self.assertIn("r$130", lowered)

    def test_pricing_menu_option_4_returns_all_prices(self) -> None:
        result = self._run(text="4", state="pricing_menu", customer_exists=True, name="Flavia")
        lowered = result["reply_text"].lower()
        self.assertIn("valores da fc vip", lowered)
        self.assertIn("3 horas", lowered)

    def test_main_menu_option_4_returns_correct_address(self) -> None:
        result = self._run(text="4", state="main_menu", customer_exists=True, name="Flavia")
        lowered = result["reply_text"].lower()
        self.assertIn("jardim amalia 1", lowered)
        self.assertNotIn("jardim amalia 2", lowered)

    def test_location_menu_does_not_have_old_option(self) -> None:
        result = self._run(text="4", state="main_menu", customer_exists=True, name="Flavia")
        lowered = result["reply_text"].lower()
        self.assertNotIn("ver endereco novamente", lowered)
        self.assertIn("1 - fazer agendamento", lowered)

    def test_main_menu_option_5_opens_structure_menu(self) -> None:
        result = self._run(text="5", state="main_menu", customer_exists=True, name="Flavia")
        self.assertEqual(result["next_state"], "structure_menu")

    def test_structure_menu_options_return_expected_text(self) -> None:
        expected_markers = {
            "1": "fundos fotograficos",
            "2": "iluminacao",
            "3": "tripes e suportes",
            "4": "cenografia",
            "5": "infraestrutura",
        }
        for option, marker in expected_markers.items():
            result = self._run(text=option, state="structure_menu", customer_exists=True, name="Flavia")
            lowered = result["reply_text"].lower()
            self.assertIn(marker, lowered)
            self.assertIn("https://www.fcvip.com.br", lowered)

    def test_human_menu_marks_needs_human(self) -> None:
        result = self._run(text="3", state="human_menu", customer_exists=True, name="Flavia")
        self.assertTrue(result["needs_human"])
        self.assertEqual(result["human_reason"], "problema_agendamento")

    def test_option_9_returns_main_menu_from_any_menu(self) -> None:
        for state in ("pricing_menu", "studio_menu", "location_menu", "structure_menu", "human_menu"):
            result = self._run(text="9", state=state, customer_exists=True, name="Flavia")
            self.assertEqual(result["next_state"], "main_menu")
            self.assertIn("1 - agendamento", result["reply_text"].lower())

    def test_option_0_ends_from_any_menu(self) -> None:
        for state in ("main_menu", "pricing_menu", "studio_menu", "location_menu", "structure_menu", "human_menu"):
            result = self._run(text="0", state=state, customer_exists=True, name="Flavia")
            self.assertEqual(result["next_state"], "end")
            self.assertTrue(result["close_conversation"])

    def test_free_text_outside_collection_is_not_interpreted(self) -> None:
        result = self._run(text="quanto custa?", state="main_menu", customer_exists=True, name="Flavia")
        self.assertIn("digitando apenas o numero", result["reply_text"].lower())
        self.assertEqual(result["next_state"], "main_menu")

    def test_invalid_numeric_option_repeats_menu(self) -> None:
        result = self._run(text="8", state="main_menu", customer_exists=True, name="Flavia")
        self.assertIn("opcao invalida", result["reply_text"].lower())
        self.assertEqual(result["next_state"], "main_menu")

    def test_non_numeric_in_collect_phone_repeats_collect_phone(self) -> None:
        result = self._run(text="telefone", state="collect_phone", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_phone")
        self.assertIn("telefone", result["reply_text"].lower())

    def test_non_numeric_in_collect_email_repeats_collect_email(self) -> None:
        result = self._run(text="quanto custa?", state="collect_email", customer_exists=False)
        self.assertEqual(result["next_state"], "collect_email")
        self.assertIn("email", result["reply_text"].lower())

    def test_registration_response_contains_expected_keys(self) -> None:
        result = self._run(
            text="nao",
            state="collect_facebook",
            customer_exists=False,
            collection_data={
                "name": "Maria Silva",
                "phone_original": "24999999999",
                "phone_normalized": "+5524999999999",
                "email": "maria@email.com",
                "instagram": "@maria",
            },
        )
        self.assertIn("chatbot_should_reply", result)
        self.assertIn("collected_customer_data", result)
        self.assertIn("memory_updates", result)
        self.assertTrue(result["chatbot_should_reply"])

    def test_address_old_reference_removed_from_prompt(self) -> None:
        prompt_path = Path("app/prompts/studio_agendamento.md")
        content = prompt_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("jardim amalia 2", content)


if __name__ == "__main__":
    unittest.main()
