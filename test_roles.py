import unittest

from roles import hires_someone_else, names_a_design_role


class NonDesignRoleTests(unittest.TestCase):
    """Заголовки, из-за которых на живых тестах полезли смм и реклама."""

    def test_smm_manager_is_not_a_designer(self):
        self.assertTrue(hires_someone_else("SMM-менеджер / Контент креатор"))

    def test_marketer_is_not_a_designer(self):
        self.assertTrue(hires_someone_else("Маркетолог в онлайн-школу"))

    def test_targetologist_is_not_a_designer(self):
        self.assertTrue(hires_someone_else("Таргетолог ВКонтакте"))

    def test_copywriter_is_not_a_designer(self):
        self.assertTrue(hires_someone_else("Креативный копирайтер"))

    def test_scriptwriter_is_not_a_designer(self):
        self.assertTrue(hires_someone_else("Методолог / сценарист"))

    def test_content_creator_is_not_a_designer(self):
        for title in ("ИИ креатор", "UCG креатор", "Digital креатор"):
            with self.subTest(title=title):
                self.assertTrue(hires_someone_else(title))

    def test_manager_is_not_a_designer(self):
        self.assertTrue(hires_someone_else("Требуется менеджер площадки"))


class DesignRoleTests(unittest.TestCase):
    """Дизайнера нельзя терять из-за соседнего слова в должности."""

    def test_smm_designer_is_still_a_designer(self):
        # Тема эсэмэмная, работа дизайнерская.
        self.assertFalse(hires_someone_else("SMM-дизайнер"))

    def test_ad_creatives_designer_is_still_a_designer(self):
        self.assertFalse(hires_someone_else("Дизайнер креативов для таргета"))

    def test_plain_designer_passes(self):
        for title in (
            "Требуется Графический дизайнер",
            "Web-designer | 100 000 р.",
            "Middle UI/UX-дизайнер",
            "Моушндизайнер",
            "Монтажер",
            "3D-художник окружений",
        ):
            with self.subTest(title=title):
                self.assertFalse(hires_someone_else(title))

    def test_craft_signal_saves_a_vague_job_title(self):
        # «Специалист» и «креатор» сами по себе ни о чём не говорят,
        # а «3D» и «CGI» говорят.
        self.assertFalse(
            hires_someone_else("3D-специалист по предметной визуализации")
        )
        self.assertFalse(hires_someone_else("CGI креатор"))

    def test_craft_signals_are_recognised(self):
        self.assertTrue(names_a_design_role("VFX artist"))
        self.assertFalse(names_a_design_role("Аналитик"))


if __name__ == "__main__":
    unittest.main()
