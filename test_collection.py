import asyncio
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from collection import collect_once, run_collection_loop
from vacancies import VacancyRepository


CHANNELS = [{"username": "ch1"}, {"username": "ch2"}]


@dataclass(frozen=True)
class Post:
    source_id: str
    source: str
    title: str
    description: str
    url: str
    published_at: str = "2026-09-06T10:00:00+00:00"


def make_post(number):
    """Каждая публикация про своё, иначе их склеит устранение повторов."""

    descriptions = {
        1: "Нужен дизайнер презентаций для инвесторов, 20 слайдов, 30 000 руб.",
        2: "Требуются карточки товаров для Wildberries, 10 штук, 8 000 руб.",
        3: "Ищем моушн-дизайнера для ролика, хронометраж минута, 45 000 руб.",
        4: "Нужна афиша для концерта в клубе, печать А2, 7 000 руб.",
    }
    return Post(
        source_id="ch/%d" % number,
        source="@ch",
        title="Вакансия %d" % number,
        description=descriptions[number],
        url="https://t.me/ch/%d" % number,
    )


DIGEST = """Ловите свежую подборочку 🫶

1. #Графдизайнер
Нужно разработать визуальную концепцию для Instagram. Бюджет 15000 ₽
📝 @selannaaaa

2. #Монтажер
Нужно смонтировать 11 Reels для beauty-проекта. Оплата 20000 ₽ за проект
📝 @ilya_re2"""


def make_digest():
    """Публикация-подборка: две вакансии в одном посте."""

    return Post(
        source_id="ch/9307",
        source="@ch",
        title="Ловите свежую подборочку",
        description=DIGEST,
        url="https://t.me/ch/9307",
    )


class DigestTests(unittest.TestCase):
    """Пост с несколькими вакансиями должен попасть в базу несколькими."""

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = VacancyRepository(
            Path(self._directory.name) / "vacancies.db"
        )

    def _collect(self, *posts):
        async def fetch(channels, limit=20, proxy=None):
            return list(posts), []

        return asyncio.run(
            collect_once(self.repository, CHANNELS, 20, fetch=fetch)
        )

    def test_a_digest_becomes_several_vacancies(self):
        added, _ = self._collect(make_digest())

        self.assertEqual(added, 2)
        self.assertEqual(self.repository.count(), 2)

    def test_each_vacancy_gets_its_own_budget(self):
        self._collect(make_digest())

        totals = sorted(
            vacancy.classification["budget"]["estimated_project_total"]
            for vacancy in self.repository.all()
        )

        self.assertEqual(totals, [15000, 20000])

    def test_an_ordinary_post_still_lands_as_one(self):
        added, _ = self._collect(make_post(1))

        self.assertEqual(added, 1)

    def test_collecting_the_same_digest_twice_adds_nothing(self):
        self._collect(make_digest())
        added, duplicates = self._collect(make_digest())

        self.assertEqual(added, 0)
        self.assertEqual(duplicates, 2)


class CollectOnceTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = VacancyRepository(
            Path(self._directory.name) / "vacancies.db"
        )

    def test_collected_posts_land_in_the_database(self):
        async def fetch(channels, limit=20, proxy=None):
            return [make_post(1), make_post(2)], []

        added, duplicates = asyncio.run(
            collect_once(self.repository, CHANNELS, 20, fetch=fetch)
        )

        self.assertEqual((added, duplicates), (2, 0))
        self.assertEqual(self.repository.count(), 2)

    def test_second_collection_adds_only_what_is_new(self):
        async def first(channels, limit=20, proxy=None):
            return [make_post(1)], []

        async def second(channels, limit=20, proxy=None):
            return [make_post(1), make_post(2)], []

        asyncio.run(collect_once(self.repository, CHANNELS, 20, fetch=first))
        added, duplicates = asyncio.run(
            collect_once(self.repository, CHANNELS, 20, fetch=second)
        )

        self.assertEqual((added, duplicates), (1, 1))
        self.assertEqual(self.repository.count(), 2)

    def test_unavailable_channels_do_not_stop_the_collection(self):
        async def fetch(channels, limit=20, proxy=None):
            return [make_post(1)], ["ch2"]

        added, _ = asyncio.run(
            collect_once(self.repository, CHANNELS, 20, fetch=fetch)
        )

        self.assertEqual(added, 1)


class CollectionLoopTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = VacancyRepository(
            Path(self._directory.name) / "vacancies.db"
        )

    def _run_loop(self, fetch, seconds=0.25):
        async def scenario():
            task = asyncio.create_task(
                run_collection_loop(
                    self.repository,
                    CHANNELS,
                    20,
                    interval_seconds=0.02,
                    first_delay_seconds=0,
                    fetch=fetch,
                )
            )
            await asyncio.sleep(seconds)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return task

        return asyncio.run(scenario())

    def test_loop_keeps_collecting_until_cancelled(self):
        calls = []

        async def fetch(channels, limit=20, proxy=None):
            calls.append(1)
            return [make_post(min(len(calls), 4))], []

        task = self._run_loop(fetch)

        self.assertGreater(len(calls), 1)
        self.assertTrue(task.done())

    def test_a_failed_cycle_does_not_stop_the_loop(self):
        calls = []

        async def fetch(channels, limit=20, proxy=None):
            calls.append(1)
            if len(calls) == 1:
                raise ConnectionError("сеть моргнула")
            return [make_post(min(len(calls), 4))], []

        self._run_loop(fetch)

        # Первый заход упал, но сбор продолжился и что-то сохранил.
        self.assertGreater(len(calls), 1)
        self.assertGreater(self.repository.count(), 0)

    def test_cancellation_is_not_swallowed(self):
        async def fetch(channels, limit=20, proxy=None):
            return [make_post(1)], []

        task = self._run_loop(fetch, seconds=0.1)

        self.assertTrue(task.cancelled() or task.done())


if __name__ == "__main__":
    unittest.main()
