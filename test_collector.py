import asyncio
import time
import unittest
from unittest import mock

import collectors.telegram_channel as telegram_channel
from collectors.telegram_channel import fetch_all_channel_posts, parse_channel_posts


PREVIEW_HTML = """
<div class="tgme_widget_message" data-post="designer_work/123">
  <div class="tgme_widget_message_text js-message_text">
    Нужен дизайнер презентаций.<br>Бюджет: 5 000 ₽.
  </div>
  <a class="tgme_widget_message_date"><time datetime="2026-08-22T10:00:00+00:00"></time></a>
</div>
<div class="tgme_widget_message" data-post="designer_work/124">
  <div class="tgme_widget_message_text js-message_text">Пост без вакансии.</div>
</div>
"""


class TelegramChannelParserTests(unittest.TestCase):
    def test_parses_posts_into_normalized_format(self):
        posts = parse_channel_posts(PREVIEW_HTML, "designer_work")

        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0].source, "@designer_work")
        self.assertEqual(posts[0].source_id, "designer_work/123")
        self.assertEqual(posts[0].url, "https://t.me/designer_work/123")
        self.assertEqual(posts[0].title, "Нужен дизайнер презентаций.")
        self.assertIn("Бюджет: 5 000 ₽.", posts[0].description)
        self.assertEqual(posts[0].published_at, "2026-08-22T10:00:00+00:00")


class FakeSession:
    """Заглушка сессии: настоящих запросов в тестах не делаем."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class ParallelFetchTests(unittest.TestCase):
    """Каналы должны опрашиваться одновременно, а не по очереди."""

    CHANNELS = [{"username": "ch%d" % number} for number in range(6)]
    DELAY = 0.05

    def _run(self, fetch):
        with mock.patch.object(telegram_channel, "_fetch_with_session", fetch),              mock.patch.object(telegram_channel, "_new_session", FakeSession):
            return asyncio.run(fetch_all_channel_posts(self.CHANNELS))

    def test_channels_are_polled_at_the_same_time(self):
        async def slow(session, username, limit, proxy):
            await asyncio.sleep(self.DELAY)
            return ["пост из " + username]

        started = time.perf_counter()
        posts, unavailable = self._run(slow)
        elapsed = time.perf_counter() - started

        self.assertEqual(len(posts), len(self.CHANNELS))
        self.assertEqual(unavailable, [])
        # Последовательный обход занял бы шесть задержек.
        self.assertLess(elapsed, self.DELAY * len(self.CHANNELS) / 2)

    def test_one_unavailable_channel_does_not_stop_the_rest(self):
        async def one_times_out(session, username, limit, proxy):
            if username == "ch3":
                raise asyncio.TimeoutError
            return ["пост из " + username]

        posts, unavailable = self._run(one_times_out)

        self.assertEqual(unavailable, ["ch3"])
        self.assertEqual(len(posts), len(self.CHANNELS) - 1)

    def test_results_keep_the_order_of_the_channel_list(self):
        async def by_name(session, username, limit, proxy):
            return ["пост из " + username]

        posts, _ = self._run(by_name)

        self.assertEqual(
            posts, ["пост из ch%d" % number for number in range(6)]
        )

    def test_a_bug_in_the_collector_is_not_swallowed(self):
        async def broken(session, username, limit, proxy):
            raise KeyError("опечатка в разборе")

        # Ошибку кода нельзя прятать в «канал недоступен».
        with self.assertRaises(KeyError):
            self._run(broken)


if __name__ == "__main__":
    unittest.main()
