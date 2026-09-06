import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from digests import split_post
from vacancies import (
    DUPLICATE_SIMILARITY,
    VacancyRepository,
    content_tokens,
    fingerprint,
    similarity,
)


@dataclass(frozen=True)
class Post:
    """Публикация в том же виде, в каком её отдаёт сборщик."""

    source_id: str
    source: str
    title: str
    description: str
    url: str
    published_at: str | None = "2026-09-05T10:00:00+00:00"


def make_post(source_id, description, source="@channel"):
    return Post(
        source_id=source_id,
        source=source,
        title=description.splitlines()[0][:120],
        description=description,
        url="https://t.me/" + source_id,
    )


VACANCY = (
    "Нужен дизайнер презентаций для инвесторов.\n"
    "20 слайдов, бюджет 30 000 руб.\n"
    "По вопросам писать @customer_hr"
)


DIGEST = """Ловите свежую подборочку 🫶

1. #Графдизайнер
Нужно разработать визуальную концепцию для Instagram. Бюджет 15000 ₽
📝 @selannaaaa

2. #Монтажер
Нужно смонтировать 11 Reels для beauty-проекта. Оплата 20000 ₽ за проект
📝 @ilya_re2"""


class ResplitDigestsTests(unittest.TestCase):
    """Подборки, собранные до разбивки, надо пересобрать в базе."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = VacancyRepository(
            Path(self._directory.name) / "vacancies.db"
        )

    def test_a_stored_digest_is_replaced_by_its_items(self):
        self.repository.save_posts([make_post("ch/9307", DIGEST)])

        digests, added = self.repository.resplit_digests(split_post)

        self.assertEqual((digests, added), (1, 2))
        self.assertEqual(self.repository.count(), 2)

    def test_the_whole_digest_is_gone_from_the_database(self):
        self.repository.save_posts([make_post("ch/9307", DIGEST)])
        self.repository.resplit_digests(split_post)

        self.assertNotIn(
            "ch/9307", [v.source_id for v in self.repository.all()]
        )

    def test_items_keep_the_link_to_the_publication(self):
        self.repository.save_posts([make_post("ch/9307", DIGEST)])
        self.repository.resplit_digests(split_post)

        self.assertEqual(
            {v.url for v in self.repository.all()}, {"https://t.me/ch/9307"}
        )

    def test_ordinary_vacancies_are_left_alone(self):
        self.repository.save_posts([make_post("ch/1", VACANCY)])

        self.assertEqual(self.repository.resplit_digests(split_post), (0, 0))
        self.assertEqual(self.repository.count(), 1)

    def test_running_it_twice_changes_nothing(self):
        self.repository.save_posts([make_post("ch/9307", DIGEST)])
        self.repository.resplit_digests(split_post)

        self.assertEqual(self.repository.resplit_digests(split_post), (0, 0))
        self.assertEqual(self.repository.count(), 2)


class FingerprintTests(unittest.TestCase):
    def test_same_text_gives_the_same_fingerprint(self):
        self.assertEqual(fingerprint(VACANCY), fingerprint(VACANCY))

    def test_channel_signature_keeps_the_text_similar_enough(self):
        # Точный хеш здесь не сходится: подпись добавляет слова. Именно
        # поэтому повтор ищется по доле общих слов, а не по совпадению.
        reprint = VACANCY + "\n\nПодписывайтесь: @another_channel"

        self.assertNotEqual(fingerprint(VACANCY), fingerprint(reprint))
        self.assertGreaterEqual(
            similarity(content_tokens(VACANCY), content_tokens(reprint)),
            DUPLICATE_SIMILARITY,
        )

    def test_two_different_vacancies_are_not_similar_enough(self):
        other = (
            "Ищем моушн-дизайнера для ролика про сервис доставки.\n"
            "Хронометраж минута, бюджет 45 000 руб."
        )

        self.assertLess(
            similarity(content_tokens(VACANCY), content_tokens(other)),
            DUPLICATE_SIMILARITY,
        )

    def test_two_vacancies_of_one_kind_stay_distinguishable(self):
        similar_topic = (
            "Требуется сделать презентацию для конференции.\n"
            "15 слайдов, оплата 12 000 руб. Писать в личные сообщения."
        )

        self.assertLess(
            similarity(content_tokens(VACANCY), content_tokens(similar_topic)),
            DUPLICATE_SIMILARITY,
        )

    def test_long_channel_footer_does_not_hide_a_reprint(self):
        # Футер канала бывает длиннее самой вакансии. Сравнение по доле
        # общих слов от объединения на этом разваливалось.
        footer = (
            " Подписывайтесь на наш канал, здесь публикуются свежие "
            "вакансии для дизайнеров каждый день. Реклама и "
            "сотрудничество через администратора. Наш чат для общения."
        )

        self.assertGreaterEqual(
            similarity(
                content_tokens(VACANCY), content_tokens(VACANCY + footer)
            ),
            DUPLICATE_SIMILARITY,
        )

    def test_channel_header_in_front_does_not_hide_a_reprint(self):
        reprint = "ВАКАНСИЯ ДНЯ. " + VACANCY

        self.assertGreaterEqual(
            similarity(content_tokens(VACANCY), content_tokens(reprint)),
            DUPLICATE_SIMILARITY,
        )

    def test_another_presentation_vacancy_is_not_merged(self):
        # Самый опасный случай: то же направление, похожая лексика.
        other = (
            "Нужен дизайнер для презентации компании, 25 слайдов, "
            "бюджет 40 000 руб."
        )

        self.assertLess(
            similarity(content_tokens(VACANCY), content_tokens(other)),
            DUPLICATE_SIMILARITY,
        )

    def test_punctuation_and_case_are_ignored(self):
        noisy = VACANCY.upper().replace(",", " ").replace(".", "")

        self.assertEqual(fingerprint(VACANCY), fingerprint(noisy))

    def test_different_vacancies_differ(self):
        other = "Нужны баннеры для рекламы. Бюджет 6 000 руб."

        self.assertNotEqual(fingerprint(VACANCY), fingerprint(other))


class VacancyRepositoryTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = VacancyRepository(
            Path(self._directory.name) / "vacancies.db"
        )

    def test_post_is_stored_with_its_classification(self):
        added, duplicates = self.repository.save_posts(
            [make_post("ch/1", VACANCY)]
        )

        self.assertEqual((added, duplicates), (1, 0))

        stored = self.repository.all()[0]
        self.assertEqual(stored.source_id, "ch/1")
        self.assertIn("presentations", stored.classification["direction_keys"])
        self.assertEqual(stored.classification["budget"]["max_amount"], 30000)

    def test_reprint_in_another_channel_is_not_stored_twice(self):
        self.repository.save_posts([make_post("ch/1", VACANCY, "@first")])

        reprint = VACANCY + "\n\nБольше вакансий: @second_channel"
        added, duplicates = self.repository.save_posts(
            [make_post("other/9", reprint, "@second")]
        )

        self.assertEqual((added, duplicates), (0, 1))
        self.assertEqual(self.repository.count(), 1)

    def test_duplicates_inside_one_batch_are_caught(self):
        added, duplicates = self.repository.save_posts(
            [
                make_post("ch/1", VACANCY, "@first"),
                make_post("other/9", VACANCY, "@second"),
            ]
        )

        self.assertEqual((added, duplicates), (1, 1))

    def test_repeated_collection_adds_nothing_new(self):
        posts = [make_post("ch/1", VACANCY)]
        self.repository.save_posts(posts)

        added, duplicates = self.repository.save_posts(posts)

        self.assertEqual(added, 0)
        self.assertEqual(self.repository.count(), 1)

    def test_different_vacancies_are_both_kept(self):
        added, duplicates = self.repository.save_posts(
            [
                make_post("ch/1", VACANCY),
                make_post("ch/2", "Нужны баннеры. Бюджет 6 000 руб."),
            ]
        )

        self.assertEqual((added, duplicates), (2, 0))

    def test_reclassify_uses_the_stored_text(self):
        self.repository.save_posts([make_post("ch/1", VACANCY)])

        self.assertEqual(self.repository.reclassify_all(), 1)

        stored = self.repository.all()[0]
        self.assertIn("presentations", stored.classification["direction_keys"])


if __name__ == "__main__":
    unittest.main()
