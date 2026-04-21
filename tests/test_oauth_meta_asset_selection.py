import unittest

from app.api.routes.oauth_meta import _extract_meta_assets_from_pages_payload


class OAuthMetaAssetSelectionTests(unittest.TestCase):
    def _payload(self) -> dict:
        return {
            "data": [
                {
                    "id": "page_1",
                    "name": "Pagina 1",
                    "instagram_business_account": {
                        "id": "ig_1",
                        "username": "conta_errada",
                    },
                },
                {
                    "id": "page_2",
                    "name": "Pagina 2",
                    "instagram_business_account": {
                        "id": "ig_2",
                        "username": "conta_certa",
                    },
                    "whatsapp_business_account": {
                        "id": "waba_2",
                        "phone_numbers": [{"id": "phone_2"}],
                    },
                },
            ]
        }

    def test_selects_preferred_instagram_username(self) -> None:
        (
            instagram_business_account_id,
            instagram_username,
            whatsapp_business_account_id,
            whatsapp_phone_number_id,
            available_instagram_accounts,
        ) = _extract_meta_assets_from_pages_payload(
            self._payload(),
            preferred_instagram_username="@conta_certa",
        )
        self.assertEqual(instagram_business_account_id, "ig_2")
        self.assertEqual(instagram_username, "conta_certa")
        self.assertEqual(whatsapp_business_account_id, "waba_2")
        self.assertEqual(whatsapp_phone_number_id, "phone_2")
        self.assertEqual(len(available_instagram_accounts), 2)

    def test_selects_preferred_instagram_business_account_id(self) -> None:
        (
            instagram_business_account_id,
            instagram_username,
            _,
            _,
            _,
        ) = _extract_meta_assets_from_pages_payload(
            self._payload(),
            preferred_instagram_business_account_id="ig_2",
        )
        self.assertEqual(instagram_business_account_id, "ig_2")
        self.assertEqual(instagram_username, "conta_certa")

    def test_falls_back_to_first_instagram_when_preference_not_found(self) -> None:
        (
            instagram_business_account_id,
            instagram_username,
            _,
            _,
            _,
        ) = _extract_meta_assets_from_pages_payload(
            self._payload(),
            preferred_instagram_username="@nao_existe",
        )
        self.assertEqual(instagram_business_account_id, "ig_1")
        self.assertEqual(instagram_username, "conta_errada")


if __name__ == "__main__":
    unittest.main()
