import unittest

from app.services.whatsapp_jid_utils import isGroupJid


class WhatsAppJidUtilsTests(unittest.TestCase):
    def test_is_group_jid_true_for_group_suffix(self) -> None:
        self.assertTrue(isGroupJid("120363111111111111@g.us"))

    def test_is_group_jid_false_for_regular_user(self) -> None:
        self.assertFalse(isGroupJid("5511999999999@s.whatsapp.net"))
        self.assertFalse(isGroupJid("5511999999999"))


if __name__ == "__main__":
    unittest.main()
