import unittest

from applications import build_application_text, build_chat_link, extract_contact_username


class ContactExtractionTests(unittest.TestCase):
    def test_extracts_last_telegram_contact(self):
        text = "Подробности: @company_hr. Для связи также https://t.me/final_contact"

        self.assertEqual(extract_contact_username(text), "final_contact")

    def test_ignores_signature_of_source_channel(self):
        text = (
            "Нужен дизайнер презентаций. Бюджет 20 000 ₽.\n"
            "По вопросам писать @customer_hr\n\n"
            "Подписывайтесь на @design_vacancy"
        )

        self.assertEqual(
            extract_contact_username(text, source_username="@design_vacancy"),
            "customer_hr",
        )

    def test_ignores_other_connected_channels(self):
        text = (
            "Ищем дизайнера баннеров. Писать @real_customer\n"
            "Ещё вакансии: t.me/designer_work"
        )

        self.assertEqual(
            extract_contact_username(
                text,
                source_username="@design_vacancy",
                excluded_usernames=["designer_work", "design_vacancy"],
            ),
            "real_customer",
        )

    def test_link_to_channel_post_is_not_a_contact(self):
        text = (
            "Подробнее в посте https://t.me/some_channel/3114\n"
            "Контакт: @customer_hr"
        )

        self.assertEqual(extract_contact_username(text), "customer_hr")

    def test_prefers_contact_next_to_cue_word_over_trailing_mention(self):
        text = (
            "Нужна анимация. По вопросам сотрудничества @customer_hr.\n"
            "Наш чат для дизайнеров @designers_chat"
        )

        self.assertEqual(extract_contact_username(text), "customer_hr")

    def test_service_links_are_not_contacts(self):
        text = "Вступай в чат https://t.me/joinchat/AbCdEfGh и жди вакансий"

        self.assertIsNone(extract_contact_username(text))

    def test_returns_none_when_only_source_channel_is_mentioned(self):
        text = "Нужен дизайнер. Все вакансии в @design_vacancy"

        self.assertIsNone(
            extract_contact_username(text, source_username="@design_vacancy")
        )


class ApplicationTests(unittest.TestCase):
    def test_builds_chat_link_with_draft_text(self):
        draft = build_application_text("Дизайн презентации")
        link = build_chat_link("company_hr", draft)

        self.assertTrue(link.startswith("https://t.me/company_hr?text="))
        self.assertIn("Портфолио", draft)


if __name__ == "__main__":
    unittest.main()
