"""Сбор публикаций из открытой веб-ленты Telegram-канала."""

import asyncio
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote

import aiohttp


REQUEST_TIMEOUT_SECONDS = 20

# Ошибки, которые означают «канал сейчас недоступен», а не поломку бота.
EXPECTED_FETCH_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, ValueError)


@dataclass(frozen=True)
class ChannelPost:
    """Публикация канала в едином формате вакансии."""

    source_id: str
    source: str
    title: str
    description: str
    url: str
    published_at: str | None


class _TelegramPreviewParser(HTMLParser):
    """Извлекает текст и метаданные постов из страницы t.me/s/<канал>."""

    def __init__(self, channel_username):
        super().__init__(convert_charrefs=True)
        self.channel_username = channel_username
        self.posts = []
        self._post = None
        self._post_depth = 0
        self._text_container_depth = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = attributes.get("class", "")

        if tag == "div" and "tgme_widget_message" in classes.split():
            source_id = attributes.get("data-post")
            if source_id:
                self._post = {
                    "source_id": source_id,
                    "text_parts": [],
                    "published_at": None,
                }
                self._post_depth = 1
            return

        if self._post is None:
            return

        if tag == "div":
            self._post_depth += 1
            if "tgme_widget_message_text" in classes.split():
                self._text_container_depth = self._post_depth

        if tag == "br" and self._text_container_depth is not None:
            self._post["text_parts"].append("\n")

        if tag == "time" and attributes.get("datetime"):
            self._post["published_at"] = attributes["datetime"]

    def handle_endtag(self, tag):
        if tag == "div" and self._post is not None:
            if self._text_container_depth == self._post_depth:
                self._text_container_depth = None
            self._post_depth -= 1
            if self._post_depth:
                return

            source_id = self._post["source_id"]
            description = "".join(self._post["text_parts"]).strip()
            if description:
                self.posts.append(
                    ChannelPost(
                        source_id=source_id,
                        source=f"@{self.channel_username}",
                        title=description.splitlines()[0][:120],
                        description=description,
                        url=f"https://t.me/{source_id}",
                        published_at=self._post["published_at"],
                    )
                )
            self._post = None
            self._post_depth = 0

    def handle_data(self, data):
        if self._post is not None and self._text_container_depth is not None:
            self._post["text_parts"].append(data)


def parse_channel_posts(html, channel_username):
    """Разбирает HTML открытой ленты в список публикаций."""

    parser = _TelegramPreviewParser(channel_username)
    parser.feed(html)
    return parser.posts


def _new_session():
    """Создаёт сессию с общими для всех запросов настройками."""

    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
        headers={"User-Agent": "freelance-bot/0.1"},
    )


async def _fetch_with_session(session, channel_username, limit, proxy):
    username = channel_username.lstrip("@")
    if not username.replace("_", "").isalnum():
        raise ValueError("Имя Telegram-канала содержит недопустимые символы")

    url = f"https://t.me/s/{quote(username)}"
    async with session.get(url, proxy=proxy) as response:
        response.raise_for_status()
        html = await response.text()

    return parse_channel_posts(html, username)[:limit]


async def fetch_channel_posts(channel_username, limit=20, proxy=None):
    """Получает последние публичные публикации Telegram-канала.

    Это не официальный Telegram API: доступен только контент, опубликованный
    в открытой веб-ленте канала.
    """

    async with _new_session() as session:
        return await _fetch_with_session(session, channel_username, limit, proxy)


async def fetch_all_channel_posts(channels, limit=20, proxy=None):
    """Собирает публикации из нескольких каналов одновременно.

    Каналы опрашиваются параллельно: раньше они шли по очереди, и один
    неотвечающий источник задерживал всю выдачу на свой таймаут.
    Недоступность канала по-прежнему не прерывает сбор из остальных.
    """

    async with _new_session() as session:
        results = await asyncio.gather(
            *(
                _fetch_with_session(session, channel["username"], limit, proxy)
                for channel in channels
            ),
            return_exceptions=True,
        )

    collected_posts = []
    unavailable_channels = []

    # Порядок результатов повторяет порядок каналов, поэтому выдача
    # остаётся предсказуемой.
    for channel, result in zip(channels, results):
        if isinstance(result, EXPECTED_FETCH_ERRORS):
            unavailable_channels.append(channel["username"])
        elif isinstance(result, BaseException):
            # Не сетевая беда, а ошибка в коде — прятать её нельзя.
            raise result
        else:
            collected_posts.extend(result)

    return collected_posts, unavailable_channels
