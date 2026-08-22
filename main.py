import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

from config import PORTFOLIO_URL
from filter import analyze_vacancy
from filter_settings import MIN_PROJECT_BUDGET, WORK_TYPES

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")

if not bot_token:
    raise ValueError("BOT_TOKEN не найден в .env")


session = AiohttpSession(proxy="http://127.0.0.1:12334")

bot = Bot(
    token=bot_token,
    session=session
)

dp = Dispatcher()


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
        await message.answer(
            "🔎 Пришли текст вакансии, и я проверю её."
        )

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


async def main():
    print("Бот запускается...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
