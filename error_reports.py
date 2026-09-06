"""Дублирование ошибок бота в Telegram.

Логи пишутся в консоль на машине, где запущен бот. Если у пользователя
что-то упадёт, владелец узнает об этом только из его сообщения — если тот
напишет. Этот обработчик подключается к логированию и присылает ошибки
владельцу.

Вешается на логгер `freelance_bot`, поэтому ловит и падения в обработчиках
сообщений, и падения фонового сбора: его логгер `freelance_bot.collection`
дочерний и передаёт записи родителю.

Оговорка, о которой стоит помнить: если бот отвалился именно от Telegram —
сеть легла, proxy упал, токен протух — сообщение не дойдёт по той же
причине. Консольные логи остаются последней линией.
"""

import asyncio
import logging
import time
import traceback


LOGGER_NAME = "freelance_bot"

# Telegram обрезает сообщения длиннее 4096 символов.
MAX_REPORT_LENGTH = 3500

# Одна и та же ошибка в фоновом цикле повторяется каждые несколько минут.
# Без окна подавления телефон звенел бы до самого исправления.
DEFAULT_REPEAT_WINDOW_SECONDS = 3600


def _shorten(text, limit):
    if len(text) <= limit:
        return text
    # Хвост трассировки полезнее начала: там место падения.
    return "…" + text[-(limit - 1):]


def build_report(record):
    """Собирает текст сообщения об ошибке."""

    lines = [
        "⚠️ Ошибка в боте",
        "",
        "Где: %s" % record.name,
        "Что: %s" % record.getMessage(),
    ]

    if record.exc_info:
        exception = record.exc_info[1]
        lines.append("Тип: %s: %s" % (type(exception).__name__, exception))
        lines.append("")
        lines.append(
            _shorten(
                "".join(traceback.format_exception(*record.exc_info)).strip(),
                MAX_REPORT_LENGTH - sum(len(line) for line in lines),
            )
        )

    return _shorten("\n".join(lines), MAX_REPORT_LENGTH)


def report_signature(record):
    """Чем одна ошибка отличается от другой при подавлении повторов."""

    exception_type = (
        type(record.exc_info[1]).__name__ if record.exc_info else ""
    )
    return (record.name, record.getMessage(), exception_type)


class TelegramErrorHandler(logging.Handler):
    """Отправляет записи уровня ERROR и выше через переданную корутину.

    `send` — асинхронная функция одного аргумента (текста). Бот сюда не
    передаётся намеренно: так обработчик можно проверить, не поднимая его.
    """

    def __init__(
        self,
        send,
        loop=None,
        repeat_window_seconds=DEFAULT_REPEAT_WINDOW_SECONDS,
        level=logging.ERROR,
        time_source=time.monotonic,
    ):
        super().__init__(level=level)
        self._send = send
        self._loop = loop
        self._repeat_window_seconds = repeat_window_seconds
        self._time_source = time_source
        self._last_sent = {}
        # Ошибка внутри отправки не должна порождать новую отправку.
        self._sending = False

    def should_send(self, record):
        """Не слишком ли часто повторяется эта же ошибка."""

        now = self._time_source()
        signature = report_signature(record)
        last = self._last_sent.get(signature)

        if last is not None and now - last < self._repeat_window_seconds:
            return False

        self._last_sent[signature] = now
        self._forget_old(now)
        return True

    def _forget_old(self, now):
        expired = [
            signature
            for signature, sent_at in self._last_sent.items()
            if now - sent_at >= self._repeat_window_seconds
        ]
        for signature in expired:
            del self._last_sent[signature]

    async def deliver(self, record):
        """Отправляет отчёт, молча переживая неудачу."""

        try:
            await self._send(build_report(record))
        except Exception:
            # Жаловаться в тот же лог нельзя: получится бесконечный круг.
            self.handleError(record)
        finally:
            self._sending = False

    def emit(self, record):
        if self._sending or not self.should_send(record):
            return

        loop = self._loop or asyncio.get_event_loop_policy().get_event_loop()

        self._sending = True
        try:
            asyncio.run_coroutine_threadsafe(self.deliver(record), loop)
        except Exception:
            self._sending = False
            self.handleError(record)


def install(send, loop=None, logger_name=LOGGER_NAME, **options):
    """Подключает отправку ошибок и возвращает обработчик."""

    handler = TelegramErrorHandler(send, loop=loop, **options)
    logging.getLogger(logger_name).addHandler(handler)
    return handler
