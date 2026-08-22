import unittest

from applications import build_application_text, build_chat_link, extract_contact_username


class ApplicationTests(unittest.TestCase):
    def test_extracts_last_telegram_contact(self):
        text = "Подробности: @company_hr. Для связи также https://t.me/final_contact"

        self.assertEqual(extract_contact_username(text), "final_contact")

    def test_builds_chat_link_with_draft_text(self):
        draft = build_application_text("Дизайн презентации")
        link = build_chat_link("company_hr", draft)

        self.assertTrue(link.startswith("https://t.me/company_hr?text="))
        self.assertIn("Портфолио", draft)
