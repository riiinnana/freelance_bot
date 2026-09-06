import unittest

from vacancy_summary import build_title, extract_role, extract_task


# Настоящий пост из ленты: он и заставил переделать карточку — заголовком
# становилась шутка про школу, а сама вакансия оставалась не видна.
DIGEST = """Ну как дела в школе? 😂

1. #Монтажер_reels
Нужно собрать с нуля Reels с анимационным монтажом. При отклике сразу присылайте примеры аналогичных работ и стоимость за ролик
📝 @ritaprod

2. #Монтажер
Нужно совместно с режиссёром собрать уже отснятый ролик продолжительностью около двух минут.
📝 @Multodel_media"""


SECTIONED = """Graphic Designer (part-time)
Мы делаем AI-продукты: телеграм-бот с нейросетями и AI-генератор презентаций.

Задачи
Карточки, обложки, визуалы и карусели для соцсетей
Обложки для YouTube-канала

Требования
Уверенная Figma
Портфолио с графикой под соцсети"""


class TitleTests(unittest.TestCase):
    def test_greeting_is_not_a_title(self):
        title = build_title(DIGEST)

        self.assertNotIn("школе", title)
        self.assertIn("онтажер", title)

    def test_hashtag_becomes_a_readable_title(self):
        title = build_title("​#дизайнер_соцсетей\nИщут дизайнера для соцсетей.")

        self.assertEqual(title, "Дизайнер соцсетей")

    def test_digit_at_the_start_survives(self):
        # «#3d_визуализатор» когда-то превращался в «d визуализатор».
        title = build_title("#3d_визуализатор\nИщут визуализатора интерьеров.")

        self.assertEqual(title, "3d визуализатор")

    def test_emoji_and_label_are_stripped(self):
        title = build_title("🌕 ОБЪЯВЛЕНИЕ Требуется дизайнер по инфографике")

        self.assertEqual(title, "Требуется дизайнер по инфографике")

    def test_tag_in_brackets_is_stripped(self):
        title = build_title("(#Удаленка) Требуется #SMM-дизайнер")

        self.assertEqual(title, "Требуется SMM-дизайнер")

    def test_a_good_first_line_is_kept_as_is(self):
        title = build_title(SECTIONED)

        self.assertEqual(title, "Graphic Designer (part-time)")

    def test_long_line_is_cut_to_the_sentence_with_the_role(self):
        text = (
            "Мы делаем AI-продукты: телеграм-бот с нейросетями, генератор "
            "презентаций и ещё несколько сервисов для маркетинга. "
            "Ищем графического дизайнера на part-time."
        )

        self.assertEqual(build_title(text), "Ищем графического дизайнера на part-time.")

    def test_title_stays_short(self):
        text = "Ищем дизайнера " + "очень " * 60 + "срочно"

        self.assertLessEqual(len(build_title(text)), 91)

    def test_without_a_role_the_first_meaningful_line_is_used(self):
        title = build_title("🎯🎯🎯\nРАЗМЕЩЕНИЕ ОБЪЯВЛЕНИЙ\nПодробности ниже.")

        self.assertEqual(title, "РАЗМЕЩЕНИЕ ОБЪЯВЛЕНИЙ")

    def test_role_is_absent_when_nobody_is_hired(self):
        self.assertIsNone(extract_role("Уважаемые подписчики нашего канала!"))

    def test_fallback_is_used_for_an_empty_post(self):
        self.assertEqual(build_title("😂😂", fallback="Монтажёр"), "Монтажёр")


class TaskTests(unittest.TestCase):
    def test_section_header_gives_the_task(self):
        task = extract_task(SECTIONED)

        self.assertIn("Карточки, обложки", task)
        self.assertIn("YouTube", task)

    def test_the_header_word_itself_is_not_shown(self):
        self.assertNotIn("Задачи", extract_task(SECTIONED))

    def test_requirements_are_not_part_of_the_task(self):
        task = extract_task(SECTIONED)

        self.assertNotIn("Figma", task)
        self.assertNotIn("Портфолио", task)

    def test_text_after_a_colon_is_kept(self):
        task = extract_task("Дизайнер\nЗадача: сделать 5 карточек для WB.")

        self.assertIn("сделать 5 карточек", task)

    def test_task_is_found_without_any_header(self):
        task = extract_task(DIGEST)

        self.assertIn("Reels с анимационным монтажом", task)

    def test_the_next_vacancy_does_not_leak_in(self):
        task = extract_task(DIGEST)

        self.assertNotIn("режиссёром", task)

    def test_contacts_do_not_leak_in(self):
        task = extract_task(DIGEST)

        self.assertNotIn("ritaprod", task)

    def test_task_stays_short(self):
        task = extract_task("Задачи\n" + "Рисовать баннеры. " * 60)

        self.assertLessEqual(len(task), 351)

    def test_expectations_section_ends_the_task(self):
        task = extract_task(
            "Дизайнер инфографики\n"
            "Что предстоит делать:\n"
            "— создавать инфографику для карточек;\n"
            "Что мы ожидаем:\n"
            "— чувство композиции и типографики;"
        )

        self.assertIn("инфографику для карточек", task)
        self.assertNotIn("композиции", task)


    def test_a_contact_glued_to_the_task_does_not_eat_the_line(self):
        # В подборках контакт часто дописан прямо в конец описания.
        task = extract_task(
            "#Дизайнер_упаковки\n"
            "Нужно разработать дизайн стаканчика для кофе. "
            "Бюджет 5 000 сом @michaelscottch"
        )

        self.assertIn("стаканчика для кофе", task)

    def test_a_line_without_a_cue_word_still_becomes_the_task(self):
        # Пункт подборки часто продолжает заголовок: «#Копирайтер / для
        # долгосрочного сотрудничества».
        task = extract_task("#Копирайтер\nдля Tg-канала. Писать посты\n📝 @someone")

        self.assertIn("Tg-канала", task)

    def test_a_pure_contact_line_is_still_dropped(self):
        task = extract_task("#Дизайнер\nНужно сделать баннер\n📝 @someone")

        self.assertNotIn("someone", task)


class TrailingPunctuationTests(unittest.TestCase):
    def test_title_does_not_end_with_a_colon(self):
        text = (
            "Ищем монтажёра-моушн-дизайнера, который берёт готовый материал "
            "и собирает из него:\n"
            "— обзоры квартир;"
        )

        self.assertFalse(build_title(text).endswith(":"))

    def test_bullet_dashes_are_removed(self):
        task = extract_task("Задачи:\n— рисовать баннеры;\n— верстать письма;")

        self.assertNotIn("—", task)


class EmptyInputTests(unittest.TestCase):
    def test_no_task_when_there_is_no_description(self):
        self.assertIsNone(extract_task("Уважаемые подписчики нашего канала!"))


if __name__ == "__main__":
    unittest.main()
