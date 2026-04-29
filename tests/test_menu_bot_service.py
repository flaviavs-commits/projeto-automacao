import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services.menu_bot_service import MenuBotService


class MenuBotServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = MenuBotService()

    def _contact(self, *, name=None, phone=None, is_temporary=False):
        return SimpleNamespace(name=name, phone=phone, is_temporary=is_temporary)

    def _conversation(self, *, menu_state=None, is_new=True):
        return SimpleNamespace(menu_state=menu_state, is_new_chat=is_new)

    def test_new_chat_unknown_customer_collects_name_first(self) -> None:
        result = self.service.handle_message(
            message_text="oi",
            conversation=self._conversation(menu_state=None, is_new=True),
            contact=self._contact(name=None, phone="5524999999999", is_temporary=True),
            customer_exists=False,
        )
        self.assertEqual(result["next_state"], "collect_new_customer_data")
        self.assertIn("nome completo", result["reply_text"].lower())

    def test_new_chat_existing_customer_gets_welcome_menu(self) -> None:
        result = self.service.handle_message(
            message_text="oi",
            conversation=self._conversation(menu_state=None, is_new=True),
            contact=self._contact(name="Flavia", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "main_menu")
        self.assertIn("ola, flavia", result["reply_text"].lower())
        self.assertIn("1 - agendamento", result["reply_text"].lower())

    def test_new_chat_existing_customer_with_unreliable_name_collects_name(self) -> None:
        result = self.service.handle_message(
            message_text="oi",
            conversation=self._conversation(menu_state=None, is_new=True),
            contact=self._contact(name="Teste Codex WhatsApp", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "collect_new_customer_data")
        self.assertIn("nome completo", result["reply_text"].lower())

    def test_existing_customer_booking_link_is_agendamentos(self) -> None:
        result = self.service.handle_message(
            message_text="1",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="Flavia", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertIn("/agendamentos", result["reply_text"])
        self.assertNotIn("/formulario", result["reply_text"])

    def test_new_customer_booking_link_is_formulario(self) -> None:
        result = self.service.handle_message(
            message_text="1",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="Novo", phone="5524999999999", is_temporary=True),
            customer_exists=False,
        )
        self.assertIn("/formulario", result["reply_text"])

    def test_old_customer_never_receives_formulario(self) -> None:
        result = self.service.handle_message(
            message_text="1",
            conversation=self._conversation(menu_state="location_menu", is_new=False),
            contact=self._contact(name="Flavia", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertIn("/agendamentos", result["reply_text"])
        self.assertNotIn("/formulario", result["reply_text"])

    def test_greeting_in_new_chat_uses_new_start_rule(self) -> None:
        result = self.service.handle_message(
            message_text="bom dia",
            conversation=self._conversation(menu_state=None, is_new=True),
            contact=self._contact(name=None, phone=None, is_temporary=True),
            customer_exists=False,
        )
        self.assertEqual(result["next_state"], "collect_new_customer_data")

    def test_main_menu_option_1_routes_booking(self) -> None:
        result = self.service.handle_message(
            message_text="1",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "booking_after_link")

    def test_main_menu_option_2_opens_pricing_menu(self) -> None:
        result = self.service.handle_message(
            message_text="2",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "pricing_menu")

    def test_pricing_menu_option_1_returns_one_hour_price(self) -> None:
        result = self.service.handle_message(
            message_text="1",
            conversation=self._conversation(menu_state="pricing_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertIn("1 hora", result["reply_text"].lower())
        self.assertIn("r$130", result["reply_text"].lower())

    def test_pricing_menu_option_4_returns_all_prices(self) -> None:
        result = self.service.handle_message(
            message_text="4",
            conversation=self._conversation(menu_state="pricing_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertIn("valores da fc vip", result["reply_text"].lower())
        self.assertIn("3 horas", result["reply_text"].lower())

    def test_main_menu_option_4_returns_correct_address(self) -> None:
        result = self.service.handle_message(
            message_text="4",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        lowered = result["reply_text"].lower()
        self.assertIn("jardim amalia 1", lowered)
        self.assertNotIn("jardim amalia 2", lowered)

    def test_location_menu_has_booking_option(self) -> None:
        result = self.service.handle_message(
            message_text="4",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        lowered = result["reply_text"].lower()
        self.assertIn("1 - fazer agendamento", lowered)
        self.assertNotIn("ver endereco novamente", lowered)

    def test_main_menu_option_5_opens_structure_menu(self) -> None:
        result = self.service.handle_message(
            message_text="5",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "structure_menu")

    def test_structure_options_texts_and_states(self) -> None:
        expected = {
            "1": ("fundos fotograficos", "backgrounds_menu"),
            "2": ("iluminacao", "lighting_menu"),
            "3": ("tripes e suportes", "supports_menu"),
            "4": ("cenografia", "scenography_menu"),
            "5": ("infraestrutura", "infrastructure_menu"),
        }
        for option, (marker, next_state) in expected.items():
            result = self.service.handle_message(
                message_text=option,
                conversation=self._conversation(menu_state="structure_menu", is_new=False),
                contact=self._contact(name="X", phone="5524999999999"),
                customer_exists=True,
            )
            self.assertIn(marker, result["reply_text"].lower())
            self.assertIn("https://www.fcvip.com.br", result["reply_text"].lower())
            self.assertEqual(result["next_state"], next_state)

    def test_human_menu_marks_human_request(self) -> None:
        result = self.service.handle_message(
            message_text="1",
            conversation=self._conversation(menu_state="human_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertTrue(result["needs_human"])
        self.assertEqual(result["human_reason"], "agendamento")
        self.assertTrue(result["dashboard_notification"])

    def test_option_9_returns_main_menu(self) -> None:
        result = self.service.handle_message(
            message_text="9",
            conversation=self._conversation(menu_state="pricing_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "main_menu")

    def test_option_0_ends_conversation(self) -> None:
        result = self.service.handle_message(
            message_text="0",
            conversation=self._conversation(menu_state="pricing_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertEqual(result["next_state"], "end")
        self.assertTrue(result["close_conversation"])

    def test_free_text_is_not_interpreted(self) -> None:
        result = self.service.handle_message(
            message_text="quanto custa?",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertIn("digitando apenas o numero", result["reply_text"].lower())
        self.assertEqual(result["next_state"], "main_menu")

    def test_invalid_numeric_option_repeats_menu(self) -> None:
        result = self.service.handle_message(
            message_text="8",
            conversation=self._conversation(menu_state="main_menu", is_new=False),
            contact=self._contact(name="X", phone="5524999999999"),
            customer_exists=True,
        )
        self.assertIn("opcao invalida", result["reply_text"].lower())
        self.assertEqual(result["next_state"], "main_menu")

    def test_address_old_reference_removed_from_prompt(self) -> None:
        prompt_path = Path("app/prompts/studio_agendamento.md")
        content = prompt_path.read_text(encoding="utf-8").lower()
        self.assertNotIn("jardim amalia 2", content)


if __name__ == "__main__":
    unittest.main()
