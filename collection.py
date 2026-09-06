"""Фоновый сбор вакансий.

Раньше каналы опрашивались в момент нажатия кнопки — то есть отдельно для
каждого пользователя. С несколькими людьми это превращалось в лишние
десятки запросов к t.me на одну волну нажатий. Теперь сбор идёт один раз
за цикл и общий для всех, а выдача читает только базу.

Зависимости передаются аргументами, а не берутся из `main`: так сбор можно
запустить в тесте, не поднимая бота.
"""

import asyncio
import logging

from collectors.telegram_channel import fetch_all_channel_posts


logger = logging.getLogger("freelance_bot.collection")


async def collect_once(
    repository,
    channels,
    limit,
    proxy=None,
    fetch=fetch_all_channel_posts,
):
    """Обходит каналы и складывает новые публикации в базу."""

    posts, unavailable_channels = await fetch(channels, limit=limit, proxy=proxy)
    added, duplicates = repository.save_posts(posts)

    logger.info(
        "Сбор: публикаций %d, новых %d, повторов %d, всего в базе %d",
        len(posts), added, duplicates, repository.count(),
    )

    if unavailable_channels:
        logger.warning(
            "Недоступны каналы: %s", ", ".join(unavailable_channels)
        )

    return added, duplicates


async def run_collection_loop(
    repository,
    channels,
    limit,
    proxy=None,
    interval_seconds=900,
    first_delay_seconds=5,
    fetch=fetch_all_channel_posts,
):
    """Собирает вакансии по кругу, пока задачу не отменят.

    Неудачный цикл не останавливает сбор: сеть могла моргнуть, следующая
    попытка будет через тот же интервал. Отмена пробрасывается наружу,
    чтобы бот мог корректно завершиться.
    """

    await asyncio.sleep(first_delay_seconds)

    while True:
        try:
            await collect_once(repository, channels, limit, proxy, fetch)
        except asyncio.CancelledError:
            logger.info("Фоновый сбор остановлен")
            raise
        except Exception:
            logger.exception("Фоновый сбор не удался, повторю позже")

        await asyncio.sleep(interval_seconds)
