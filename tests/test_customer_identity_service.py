import unittest

from app.services.customer_identity_service import CustomerIdentityService


class CustomerIdentityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CustomerIdentityService()

    def test_normalize_whatsapp_evolution_suffix_s_whatsapp(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "whatsapp",
            "5511999999999@s.whatsapp.net",
        )
        self.assertEqual(normalized, "5511999999999")

    def test_normalize_whatsapp_evolution_suffix_c_us(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "whatsapp",
            "5511888888888@c.us",
        )
        self.assertEqual(normalized, "5511888888888")

    def test_normalize_instagram_keeps_username_shape(self) -> None:
        normalized = self.service._normalize_identity_value(  # noqa: SLF001
            "instagram",
            "@MeuUsuario",
        )
        self.assertEqual(normalized, "@meuusuario")


if __name__ == "__main__":
    unittest.main()
