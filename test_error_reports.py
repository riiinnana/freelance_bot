import asyncio
import logging
import unittest

from error_reports import TelegramErrorHandler, build_report, report_signature


def make_record(message="Что-то сломалось", exception=None, name="freelance_bot"):
    exc_info = None
    if exception is not None:
        try:
            raise exception
        except type(exception):
            import sys

            exc_info = sys.exc_info()

    return logging.LogRecord(
        name=name,
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=exc_info,
    )


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ReportTextTests(unittest.TestCase):
    def test_report_names_the_source_and_the_message(self):
        report = build_report(make_record(name="freelance_bot.collection"))

        self.assertIn("freelance_bot.collection", report)
        self.assertIn("Что-то сломалось", report)

    def test_report_includes_the_exception(self):
        report = build_report(
            make_record(exception=ConnectionError("сеть недоступна"))
        )

        self.assertIn("ConnectionError", report)
        self.assertIn("сеть недоступна", report)

    def test_report_fits_into_a_telegram_message(self):
        report = build_report(
            make_record(message="ы" * 9000, exception=ValueError("ы" * 9000))
        )

        self.assertLessEqual(len(report), 4096)

    def test_same_failure_has_the_same_signature(self):
        first = make_record(exception=ConnectionError("сеть"))
        second = make_record(exception=ConnectionError("сеть"))

        self.assertEqual(report_signature(first), report_signature(second))

    def test_different_failures_differ(self):
        first = make_record(exception=ConnectionError("сеть"))
        second = make_record(exception=ValueError("что-то другое"))

        self.assertNotEqual(report_signature(first), report_signature(second))


class ThrottleTests(unittest.TestCase):
    """Ошибка в фоновом цикле повторяется постоянно — слать её каждый раз нельзя."""

    def setUp(self):
        self.clock = FakeClock()
        self.handler = TelegramErrorHandler(
            send=None, repeat_window_seconds=3600, time_source=self.clock
        )

    def test_first_occurrence_is_sent(self):
        self.assertTrue(self.handler.should_send(make_record()))

    def test_repeat_inside_the_window_is_suppressed(self):
        self.handler.should_send(make_record())
        self.clock.advance(60)

        self.assertFalse(self.handler.should_send(make_record()))

    def test_repeat_after_the_window_is_sent_again(self):
        self.handler.should_send(make_record())
        self.clock.advance(3601)

        self.assertTrue(self.handler.should_send(make_record()))

    def test_a_different_failure_is_not_suppressed(self):
        self.handler.should_send(make_record(message="первая"))

        self.assertTrue(self.handler.should_send(make_record(message="вторая")))


class DeliveryTests(unittest.TestCase):
    def test_error_reaches_the_owner(self):
        sent = []

        async def send(text):
            sent.append(text)

        async def scenario():
            handler = TelegramErrorHandler(send, loop=asyncio.get_running_loop())
            logger = logging.getLogger("test_error_reports.delivery")
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)

            logger.error("Фоновый сбор не удался")
            await asyncio.sleep(0.05)

        asyncio.run(scenario())

        self.assertEqual(len(sent), 1)
        self.assertIn("Фоновый сбор не удался", sent[0])

    def test_info_messages_are_not_sent(self):
        sent = []

        async def send(text):
            sent.append(text)

        async def scenario():
            handler = TelegramErrorHandler(send, loop=asyncio.get_running_loop())
            logger = logging.getLogger("test_error_reports.levels")
            logger.setLevel(logging.INFO)
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)

            logger.info("Сбор: публикаций 20")
            await asyncio.sleep(0.05)

        asyncio.run(scenario())

        self.assertEqual(sent, [])

    def test_a_failing_send_does_not_raise(self):
        async def send(text):
            raise ConnectionError("Telegram недоступен")

        async def scenario():
            handler = TelegramErrorHandler(send, loop=asyncio.get_running_loop())
            handler.handleError = lambda record: None
            logger = logging.getLogger("test_error_reports.failure")
            logger.addHandler(handler)
            self.addCleanup(logger.removeHandler, handler)

            # Если бот отвалился от Telegram, отчёт туда же не уйдёт —
            # это не должно ломать сам бот.
            logger.error("Что-то сломалось")
            await asyncio.sleep(0.05)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
