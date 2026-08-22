import asyncio
from html import escape
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

from applications import build_application_text, build_chat_link, extract_contact_username
from config import PORTFOLIO_URL
from collectors.telegram_channel import fetch_all_channel_posts
from filter import analyze_vacancy
from filter_settings import MIN_PROJECT_BUDGET, WORK_TYPES
from rejections import RejectionRepository
from source_settings import (
    COLLECTOR_POST_LIMIT,
    TELEGRAM_CHANNELS,
)

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")

if not bot_token:
    raise ValueError("BOT_TOKEN не найден в .env")


PROXY_URL = "http://127.0.0.1:12334"

session = AiohttpSession(proxy=PROXY_URL)

bot = Bot(
    token=bot_token,
    session=session
)

dp = Dispatcher()
rejection_repository = RejectionRepository("data/rejections.db")


# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🔎 Найти вакансии"),
            KeyboardButton(text="⭐ Подходящие вакансии"),
        ],
        [
            KeyboardButton(text="⚙️ Настройки"),
        ],
    ],
    resize_keyboard=True
)


def format_budget(budget):
    """Форматирует бюджет с упором на итоговую сумму за проект."""

    payment_type = budget["payment_type"]

    if payment_type == "fixed":
        return f"{budget['estimated_project_total']} ₽ за проект"

    if payment_type == "range":
        return f"{budget['min_amount']}–{budget['max_amount']} ₽ за проект"

    if payment_type == "hourly":
        rate = f"{budget['hourly_rate']} ₽/час"
        if budget["estimated_project_total"] is None:
            return f"{rate}; количество часов не указано"
        return (
            f"{rate}; {budget['hours']} ч. = "
            f"{budget['estimated_project_total']} ₽ за проект"
        )

    return "не указана"


def format_collected_vacancy(post, result):
    """Создаёт компактное сообщение с результатом анализа публикации."""

    status_icons = {"green": "🟢", "yellow": "🟡"}
    directions = ", ".join(result["work_types"])

    return (
        f"{status_icons[result['status']]} <b>{escape(post.title)}</b>\n\n"
        f"<b>Бюджет:</b> {escape(format_budget(result['budget']))}\n"
        f"<b>Источник:</b> {escape(post.source)}\n"
        f"<b>Направления:</b> {escape(directions)}\n"
        f"<b>Причина:</b> {escape(result['reason'])}\n\n"
        f"<a href=\"{post.url}\">Открыть публикацию в канале</a>"
    )


def candidate_score(post, result, contact_username):
    """Оценивает релевантность вакансии для выдачи первой."""

    return (
        contact_username is not None,
        len(result["matched_keywords"]),
        result["budget"]["max_amount"] or 0,
        post.published_at or "",
    )


async def show_best_vacancy(message, user_id):
    """Находит и отправляет одну лучшую ещё не отклонённую вакансию."""

    try:
        posts, unavailable_channels = await fetch_all_channel_posts(
            TELEGRAM_CHANNELS,
            limit=COLLECTOR_POST_LIMIT,
            proxy=PROXY_URL,
        )
    except Exception:
        await message.answer(
            "Не удалось получить вакансии. Проверь подключение к proxy и повтори попытку позже."
        )
        return

    candidates = []
    for post in posts:
        if rejection_repository.is_rejected(user_id, post.source_id):
            continue

        result = analyze_vacancy(post.description)
        if result["status"] != "green":
            continue

        contact_username = extract_contact_username(post.description)
        candidates.append((post, result, contact_username))

    if not candidates:
        await message.answer(
            "Новых подходящих вакансий не найдено. Попробуй позже или измени настройки фильтра."
        )
        return

    post, result, contact_username = max(
        candidates,
        key=lambda item: candidate_score(*item),
    )

    buttons = []
    if contact_username:
        draft = build_application_text(post.title)
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✉️ Написать заказчику",
                    url=build_chat_link(contact_username, draft),
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔗 Открыть публикацию",
                    url=post.url,
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="✖️ Отклонить",
                callback_data=f"reject:{post.source_id}",
            )
        ]
    )

    await message.answer(
        format_collected_vacancy(post, result),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )

    if unavailable_channels:
        await message.answer(
            "Часть источников недоступна: "
            + ", ".join(f"@{username}" for username in unavailable_channels)
        )


@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer(
        "Привет! Я твой помощник по поиску фриланс-вакансий.\n\n"
        "Выбери нужное действие:",
        reply_markup=main_menu
    )


@dp.message()
async def handle_buttons(message: Message):
    if message.text == "🔎 Найти вакансии":
        await message.answer("🔎 Ищу лучшую подходящую вакансию...")
        await show_best_vacancy(message, message.from_user.id)

    elif message.text == "⭐ Подходящие вакансии":
        await message.answer(
            "⭐ Здесь будут появляться подходящие тебе вакансии."
        )

    elif message.text == "⚙️ Настройки":
        work_types = "\n".join(
            f"• {work_type}" for work_type in WORK_TYPES
        )

        await message.answer(
            f"⚙️ <b>Твои настройки поиска</b>\n\n"
            f"<b>Минимальная сумма за проект:</b> {MIN_PROJECT_BUDGET} ₽\n\n"
            f"<b>Подходящие направления:</b>\n"
            f"{work_types}\n\n"
            f"<b>Портфолио:</b>\n"
            f"{PORTFOLIO_URL}",
            parse_mode="HTML"
        )

    else:
        result = analyze_vacancy(message.text)

        status_icons = {
            "green": "🟢",
            "yellow": "🟡",
            "red": "🔴",
        }

        status_names = {
            "green": "Подходит",
            "yellow": "Нужно проверить",
            "red": "Не подходит",
        }

        icon = status_icons[result["status"]]
        status = status_names[result["status"]]

        directions = ", ".join(result["work_types"])

        budget = format_budget(result["budget"])

        await message.answer(
            f"{icon} <b>{status}</b>\n\n"
            f"<b>Бюджет:</b> {budget}\n"
            f"<b>Направления:</b> {directions or 'не определены'}\n\n"
            f"<b>Причина:</b> {result['reason']}"
            ,
            parse_mode="HTML"
        )


@dp.callback_query(F.data.startswith("reject:"))
async def reject_vacancy(callback: CallbackQuery):
    source_id = callback.data.removeprefix("reject:")
    rejection_repository.reject(callback.from_user.id, source_id)
    await callback.answer("Вакансия отклонена")
    await callback.message.answer("✖️ Вакансия скрыта. Ищу следующую...")
    await show_best_vacancy(callback.message, callback.from_user.id)


async def main():
    print("Бот запускается...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
