import unittest

from app.services.contact_memory_service import ContactMemoryService


class ContactMemoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ContactMemoryService()

    def test_extracts_name_location_time_and_intent(self) -> None:
        result = self.service.analyze_text(
            "Meu nome e Joao da Silva, moro em Volta Redonda e queria agendar para 19h."
        )
        self.assertEqual(result.get("status"), "candidate_found")
        candidates = result.get("candidates") or []
        keys = {item.get("memory_key"): item.get("memory_value") for item in candidates}

        self.assertEqual(keys.get("nome_cliente"), "Joao Da Silva")
        self.assertEqual(keys.get("localidade_cliente"), "Volta Redonda")
        self.assertEqual(keys.get("intencao_principal"), "agendar")
        self.assertEqual(keys.get("preferencia_horario"), "19h")
        self.assertEqual(keys.get("horario_perguntado"), "19h")

    def test_extracts_hours_question_memory(self) -> None:
        result = self.service.analyze_text("Que horas abre? Tem horario 18h hoje?")
        self.assertEqual(result.get("status"), "candidate_found")
        candidates = result.get("candidates") or []
        keys = {item.get("memory_key"): item.get("memory_value") for item in candidates}
        self.assertEqual(keys.get("perguntou_horario_funcionamento"), "true")
        self.assertEqual(keys.get("horario_perguntado"), "18h")

    def test_ignores_ambiguous_message(self) -> None:
        result = self.service.analyze_text("Talvez eu veja depois, nao tenho certeza.")
        self.assertEqual(result.get("status"), "ignored_ambiguous")
        self.assertEqual(result.get("candidates"), [])


if __name__ == "__main__":
    unittest.main()
