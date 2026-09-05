import asyncio
from html import escape
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
from directions import DIRECTIONS, direction_names
from filter import analyze_vacancy
from profiles import MAX_ALLOWED_BUDGET, MIN_ALLOWED_BUDGET, ProfileRepository
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
profile_repository = ProfileRepository("data/rejections.db")

# Вакансии, которые попадают в выдачу: точное совпадение с профилем и —
# при выключенном строгом режиме — смежные направления.
SHOWN_REASON_CODES = {"match", "off_profile"}

# Каналы-источники: их упоминания в конце поста — это подпись канала,
# а не контакт заказчика.
CHANNEL_USERNAMES = [channel["username"] for channel in TELEGRAM_CHANNELS]


class SettingsStates(StatesGroup):
    waiting_for_budget = State()


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


def build_settings_text(profile):
    """Собирает описание текущих настроек поиска."""

    if profile.direction_keys:
        chosen = "\n".join(
            f"{position}. {escape(name)}"
            for position, name in enumerate(
                direction_names(profile.direction_keys), start=1
            )
        )
        directions_block = (
            f"<b>Твои направления</b> (в порядке важности):\n{chosen}"
        )
    else:
        directions_block = (
            "<b>Твои направления:</b> пока не выбраны.\n"
            "Отметь хотя бы одно — без этого поиск не заработает."
        )

    strict_block = (
        "Показываю только выбранные направления."
        if profile.strict_mode
        else "Показываю и смежные направления, но в конце списка."
    )

    return (
        "⚙️ <b>Настройки поиска</b>\n\n"
        f"{directions_block}\n\n"
        f"<b>Минимальная сумма за проект:</b> {profile.min_budget} ₽\n"
        f"<b>Строгий режим:</b> {strict_block}\n\n"
        f"<b>Портфолио:</b>\n{escape(PORTFOLIO_URL)}"
    )


def build_settings_keyboard(profile):
    """Собирает клавиатуру настроек с галочками направлений."""

    rows = []
    for direction in DIRECTIONS:
        mark = "✅" if direction.key in profile.direction_keys else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {direction.name}",
                    callback_data=f"dir:{direction.key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=f"💰 Минимальная сумма: {profile.min_budget} ₽",
                callback_data="settings:budget",
            )
        ]
    )

    strict_label = "включён" if profile.strict_mode else "выключен"
    rows.append(
        [
            InlineKeyboardButton(
                text=f"🎯 Строгий режим: {strict_label}",
                callback_data="settings:strict",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_settings(message, profile):
    await message.answer(
        build_settings_text(profile),
        parse_mode="HTML",
        reply_markup=build_settings_keyboard(profile),
    )


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
        f"<a href=\"{escape(post.url, quote=True)}\">Открыть публикацию в канале</a>"
    )


def candidate_score(post, result, contact_username):
    """Оценивает релевантность вакансии для выдачи первой."""

    return (
        not result["off_profile"],
        contact_username is not None,
        -result["priority"],
        len(result["matched_keywords"]),
        result["budget"]["max_amount"] or 0,
        post.published_at or "",
    )


async def show_best_vacancy(message, user_id):
    """Находит и отправляет одну лучшую ещё не отклонённую вакансию."""

    profile = profile_repository.get(user_id)

    if not profile.is_configured:
        await message.answer(
            "Сначала выбери направления, которые тебе интересны — "
            "иначе я не знаю, что искать."
        )
        await send_settings(message, profile)
        return

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

        result = analyze_vacancy(post.description, profile)
        if result["reason_code"] not in SHOWN_REASON_CODES:
            continue

        contact_username = extract_contact_username(
            post.description,
            source_username=post.source,
            excluded_usernames=CHANNEL_USERNAMES,
        )
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
async def start_command(message: Message, state: FSMContext):
    await state.clear()
    profile = profile_repository.get(message.from_user.id)

    if not profile.is_configured:
        await message.answer(
            "Привет! Я помогаю искать фриланс-вакансии по дизайну.\n\n"
            "Чтобы я показывал только нужное, отметь свои направления. "
            "Порядок важен: что отметишь первым, то и будет выше в выдаче.",
            reply_markup=main_menu,
        )
        await send_settings(message, profile)
        return

    await message.answer(
        "Привет! Я твой помощник по поиску фриланс-вакансий.\n\n"
        "Выбери нужное действие:",
        reply_markup=main_menu
    )


@dp.message(SettingsStates.waiting_for_budget)
async def set_budget(message: Message, state: FSMContext):
    raw_amount = (message.text or "").replace(" ", "").replace(" ", "")

    if not raw_amount.isdigit():
        await message.answer(
            "Нужно число без букв и знаков, например: 5000.\n"
            "Отправь сумму ещё раз или нажми /start, чтобы выйти."
        )
        return

    amount = int(raw_amount)
    if not MIN_ALLOWED_BUDGET <= amount <= MAX_ALLOWED_BUDGET:
        await message.answer(
            f"Сумма должна быть от {MIN_ALLOWED_BUDGET} "
            f"до {MAX_ALLOWED_BUDGET} ₽. Отправь другое число."
        )
        return

    profile_repository.set_min_budget(message.from_user.id, amount)
    await state.clear()

    profile = profile_repository.get(message.from_user.id)
    await message.answer(f"Готово, минимальная сумма теперь {amount} ₽.")
    await send_settings(message, profile)


@dp.message()
async def handle_buttons(message: Message):
    profile = profile_repository.get(message.from_user.id)

    if message.text == "🔎 Найти вакансии":
        await message.answer("🔎 Ищу лучшую подходящую вакансию...")
        await show_best_vacancy(message, message.from_user.id)

    elif message.text == "⭐ Подходящие вакансии":
        await message.answer(
            "⭐ Здесь будут появляться подходящие тебе вакансии."
        )

    elif message.text == "⚙️ Настройки":
        await send_settings(message, profile)

    else:
        result = analyze_vacancy(message.text, profile)

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


@dp.callback_query(F.data.startswith("dir:"))
async def toggle_direction(callback: CallbackQuery):
    direction_key = callback.data.removeprefix("dir:")

    try:
        is_selected = profile_repository.toggle_direction(
            callback.from_user.id, direction_key
        )
    except ValueError:
        await callback.answer("Это направление больше недоступно")
        return

    await callback.answer("Направление добавлено" if is_selected else "Направление убрано")

    profile = profile_repository.get(callback.from_user.id)
    await callback.message.edit_text(
        build_settings_text(profile),
        parse_mode="HTML",
        reply_markup=build_settings_keyboard(profile),
    )


@dp.callback_query(F.data == "settings:strict")
async def toggle_strict_mode(callback: CallbackQuery):
    profile = profile_repository.get(callback.from_user.id)
    profile_repository.set_strict_mode(
        callback.from_user.id, not profile.strict_mode
    )

    await callback.answer(
        "Строгий режим выключен" if profile.strict_mode else "Строгий режим включён"
    )

    profile = profile_repository.get(callback.from_user.id)
    await callback.message.edit_text(
        build_settings_text(profile),
        parse_mode="HTML",
        reply_markup=build_settings_keyboard(profile),
    )


@dp.callback_query(F.data == "settings:budget")
async def ask_budget(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_budget)
    await callback.answer()
    await callback.message.answer(
        "Отправь минимальную сумму за проект в рублях, например: 5000."
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
