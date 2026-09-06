import asyncio
import logging
import os
from html import escape

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

from applications import build_application_text, build_chat_link, extract_contact_username
from commitment import ANY, ONE_OFF, ONGOING, commitment_label, commitment_name
from collection import run_collection_loop
from directions import (
    DIRECTION_BY_KEY,
    GROUPS,
    direction_names,
    directions_in_group,
    group_name,
)
from filter import analyze_vacancy, evaluate_for_user
from storage import DATABASE_PATH
from vacancies import VacancyRepository
from profiles import (
    MAX_ALLOWED_BUDGET,
    MIN_ALLOWED_BUDGET,
    NO_MAX_BUDGET,
    ProfileRepository,
)
from vacancy_actions import (
    HIDDEN_ACTIONS,
    REJECTED,
    RESPONDED,
    SKIPPED,
    VacancyActionRepository,
)
from source_settings import (
    COLLECTION_INTERVAL_MINUTES,
    COLLECTOR_POST_LIMIT,
    FIRST_COLLECTION_DELAY_SECONDS,
    TELEGRAM_CHANNELS,
)

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")

if not bot_token:
    raise ValueError("BOT_TOKEN не найден в .env")


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("freelance_bot")

# Пусто или не задано — работаем без proxy. Адрес задаётся в .env, чтобы
# бот запускался в любой среде без правки кода.
PROXY_URL = os.getenv("PROXY_URL") or None

if PROXY_URL:
    logger.info("Запросы идут через proxy %s", PROXY_URL)
else:
    logger.info("PROXY_URL не задан — работаю напрямую")

session = AiohttpSession(proxy=PROXY_URL)

bot = Bot(
    token=bot_token,
    session=session
)

dp = Dispatcher()
action_repository = VacancyActionRepository(DATABASE_PATH)
profile_repository = ProfileRepository(DATABASE_PATH)
vacancy_repository = VacancyRepository(DATABASE_PATH)

# Вакансии, которые попадают в выдачу: точное совпадение с профилем и —
# при выключенном строгом режиме — смежные направления.
SHOWN_REASON_CODES = {"match", "off_profile"}

# Каналы-источники: их упоминания в конце поста — это подпись канала,
# а не контакт заказчика.
CHANNEL_USERNAMES = [channel["username"] for channel in TELEGRAM_CHANNELS]

# Ссылки на чат с заказчиком для показанных вакансий. В callback приходит
# только идентификатор поста, а собирать черновик заново пришлось бы через
# повторный опрос каналов — то самое ожидание, от которого мы уходим.
#
# Хранится отдельно по каждому пользователю: в общем списке активные
# вытесняли бы черновики тех, кто читает медленнее.
pending_chat_links = {}
MAX_LINKS_PER_USER = 20


def remember_chat_link(user_id, source_id, chat_url):
    links = pending_chat_links.setdefault(user_id, {})
    links[source_id] = chat_url
    while len(links) > MAX_LINKS_PER_USER:
        links.pop(next(iter(links)))


def take_chat_link(user_id, source_id):
    """Забирает ссылку на чат: повторно она уже не понадобится."""

    links = pending_chat_links.get(user_id)
    return links.pop(source_id, None) if links else None


class SettingsStates(StatesGroup):
    waiting_for_budget = State()
    waiting_for_max_budget = State()
    waiting_for_portfolio = State()


# Кнопка формата работы перебирает варианты по кругу.
COMMITMENT_CYCLE = {ANY: ONE_OFF, ONE_OFF: ONGOING, ONGOING: ANY}

COMMITMENT_BUTTON_LABELS = {
    ANY: "любой",
    ONE_OFF: "только разовые",
    ONGOING: "только долгосрок",
}


HELP_TEXT = """<b>Что делает бот</b>

Раз в 15 минут я обхожу Telegram-каналы с вакансиями для дизайнеров,
разбираю объявления и оставляю те, что подходят именно тебе.

<b>Кнопки</b>
🔎 <b>Найти вакансии</b> — показываю одну самую подходящую.
⚙️ <b>Настройки</b> — направления, вилка сумм, формат работы, портфолио.

<b>Под каждой вакансией</b>
✉️ <b>Написать заказчику</b> — открываю чат с готовым черновиком отклика.
Отправляешь его ты, я ничего никому не рассылаю.
⏭️ <b>Пропустить</b> — вакансия вернётся позже, когда свежие кончатся.
✖️ <b>Не подходит</b> — больше её не покажу.

<b>Настройки стоит проверить в первую очередь</b>
Направления собраны в три блока — 2D, 3D, анимация и видео. Порядок
выбора задаёт приоритет: что отметишь первым, будет выше в выдаче.
Строгий режим показывает только выбранное; если его выключить, смежные
направления тоже попадут в выдачу, но в конец.

Команды: /start — начать заново, /help — эта справка."""

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🔎 Найти вакансии"),
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

    if payment_type == "from":
        return f"от {budget['min_amount']} ₽ за проект"

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

    budget_block = f"от {profile.min_budget} ₽"
    if profile.has_max_budget:
        budget_block += f" до {profile.max_budget} ₽"

    commitment_block = {
        ANY: "любой",
        ONE_OFF: "только разовые задачи",
        ONGOING: "только постоянное сотрудничество",
    }[profile.commitment]

    portfolio_block = (
        escape(profile.portfolio_url)
        if profile.has_portfolio
        else "не указано — без него отклик уйдёт без ссылки на работы."
    )

    return (
        "⚙️ <b>Настройки поиска</b>\n\n"
        f"{directions_block}\n\n"
        f"<b>Сумма за проект:</b> {budget_block}\n"
        f"<b>Формат работы:</b> {commitment_block}\n"
        f"<b>Строгий режим:</b> {strict_block}\n\n"
        f"<b>Портфолио:</b>\n{portfolio_block}"
    )


def _selected_in_group(group_key, profile):
    """Считает, сколько направлений блока отмечено у пользователя."""

    return sum(
        1
        for direction in directions_in_group(group_key)
        if direction.key in profile.direction_keys
    )


def build_settings_keyboard(profile):
    """Собирает главный экран настроек: блоки, сумма и строгий режим."""

    rows = []
    for group in GROUPS:
        chosen = _selected_in_group(group.key, profile)
        total = len(directions_in_group(group.key))
        mark = "✅" if chosen else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {group.name} — {chosen}/{total}",
                    callback_data=f"grp:{group.key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=f"💰 От: {profile.min_budget} ₽",
                callback_data="settings:budget",
            ),
            InlineKeyboardButton(
                text=(
                    f"💸 До: {profile.max_budget} ₽"
                    if profile.has_max_budget
                    else "💸 До: без потолка"
                ),
                callback_data="settings:maxbudget",
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "⏳ Формат работы: "
                    + COMMITMENT_BUTTON_LABELS[profile.commitment]
                ),
                callback_data="settings:commitment",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "🔗 Портфолио: указано"
                    if profile.has_portfolio
                    else "🔗 Портфолио: добавить"
                ),
                callback_data="settings:portfolio",
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


def build_group_text(group_key, profile):
    """Описывает один блок направлений."""

    chosen = [
        direction.name
        for direction in directions_in_group(group_key)
        if direction.key in profile.direction_keys
    ]

    if chosen:
        chosen_block = "Отмечено: " + escape(", ".join(chosen))
    else:
        chosen_block = "Пока ничего не отмечено."

    return (
        f"<b>{escape(group_name(group_key))}</b>\n\n"
        f"{chosen_block}\n\n"
        "Порядок важен: что отметишь раньше, то будет выше в выдаче."
    )


def build_group_keyboard(group_key, profile):
    """Собирает экран одного блока с галочками направлений."""

    directions = directions_in_group(group_key)
    rows = []

    for direction in directions:
        mark = "✅" if direction.key in profile.direction_keys else "⬜"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {direction.name}",
                    callback_data=f"dir:{direction.key}",
                )
            ]
        )

    all_chosen = all(
        direction.key in profile.direction_keys for direction in directions
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="✖️ Снять весь блок" if all_chosen else "✅ Отметить весь блок",
                callback_data=f"grpall:{group_key}",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ К настройкам",
                callback_data="settings:back",
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

    label = commitment_label(result.get("commitment"))
    commitment_line = f"<b>Формат:</b> {label}' + NL + '" if label else ""

    return (
        f"{status_icons[result['status']]} <b>{escape(post.title)}</b>\n\n"
        f"<b>Бюджет:</b> {escape(format_budget(result['budget']))}\n"
        f"{commitment_line}"
        f"<b>Источник:</b> {escape(post.source)}\n"
        f"<b>Направления:</b> {escape(directions)}\n"
        f"<b>Причина:</b> {escape(result['reason'])}\n\n"
        f"<a href=\"{escape(post.url, quote=True)}\">Открыть публикацию в канале</a>"
    )


def candidate_score(post, result, contact_username, is_skipped):
    """Оценивает релевантность вакансии для выдачи первой.

    Пропущенные уходят в конец: они вернутся, только когда свежих
    вакансий не останется.
    """

    return (
        not is_skipped,
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

    if not profile.has_portfolio:
        await message.answer(
            "Добавь ссылку на портфолио — она подставляется в отклик "
            "заказчику. Это в «⚙️ Настройки»."
        )
        await send_settings(message, profile)
        return

    # В сеть здесь не ходим: каналы обходит фоновый сбор, один раз для
    # всех пользователей. Выдача читает только базу и отвечает сразу.
    if not vacancy_repository.count():
        await message.answer(
            "Ещё собираю вакансии — это первый заход после запуска. "
            "Загляни через пару минут."
        )
        return

    actions = action_repository.actions_for_user(user_id)

    candidates = []
    for post in vacancy_repository.all():
        action = actions.get(post.source_id)
        if action in HIDDEN_ACTIONS:
            continue

        # Разбор уже посчитан при сборе — здесь только примерка под профиль.
        result = evaluate_for_user(post.classification, profile)
        if result["reason_code"] not in SHOWN_REASON_CODES:
            continue

        contact_username = extract_contact_username(
            post.description,
            source_username=post.source,
            excluded_usernames=CHANNEL_USERNAMES,
        )
        candidates.append(
            (post, result, contact_username, action == SKIPPED)
        )

    if not candidates:
        await message.answer(
            "Новых подходящих вакансий не найдено. Попробуй позже или измени настройки фильтра."
        )
        return

    post, result, contact_username, _ = max(
        candidates,
        key=lambda item: candidate_score(*item),
    )

    buttons = []
    if contact_username:
        draft = build_application_text(
            post.title,
            profile.portfolio_url,
            result["profile_direction_keys"] or result["direction_keys"],
            seed=post.source_id,
        )
        # Кнопка-ссылка не сообщила бы боту о нажатии, поэтому она
        # callback: бот успевает отметить отклик и подтянуть следующую
        # вакансию, пока ты пишешь заказчику.
        remember_chat_link(
            user_id, post.source_id, build_chat_link(contact_username, draft)
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✉️ Написать заказчику",
                    callback_data=f"write:{post.source_id}",
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
                text="⏭️ Пропустить",
                callback_data=f"skip:{post.source_id}",
            ),
            InlineKeyboardButton(
                text="✖️ Не подходит",
                callback_data=f"reject:{post.source_id}",
            ),
        ]
    )

    await message.answer(
        format_collected_vacancy(post, result),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")


@dp.error()
async def on_unexpected_error(event: ErrorEvent):
    """Ловит всё, что не поймали обработчики.

    Без этого падение внутри обработчика уходило только в лог, а человек
    видел тишину и не понимал, жив ли бот.
    """

    logger.exception(
        "Необработанная ошибка при обновлении", exc_info=event.exception
    )

    message = event.update.message
    if message is None and event.update.callback_query is not None:
        message = event.update.callback_query.message

    if message is not None:
        try:
            await message.answer(
                "Что-то пошло не так с моей стороны. Попробуй ещё раз, "
                "а если повторится — напиши мне об этом."
            )
        except Exception:
            logger.exception("Не удалось сообщить пользователю об ошибке")

    return True

@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    await state.clear()
    profile = profile_repository.get(message.from_user.id)

    if not profile.is_configured:
        await message.answer(
            "Привет! Я помогаю искать фриланс-вакансии по дизайну.\n\n"
            "Чтобы я показывал только нужное, отметь свои направления — "
            "порядок важен, что отметишь первым, то и будет выше в выдаче.\n"
            "И добавь ссылку на портфолио: она подставляется в отклик.",
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


@dp.message(SettingsStates.waiting_for_portfolio)
async def set_portfolio(message: Message, state: FSMContext):
    try:
        profile_repository.set_portfolio_url(
            message.from_user.id, message.text or ""
        )
    except ValueError:
        await message.answer(
            "Нужна ссылка целиком, вместе с http:// или https://.\n"
            "Отправь её ещё раз или нажми /start, чтобы выйти."
        )
        return

    await state.clear()

    profile = profile_repository.get(message.from_user.id)
    await message.answer("Готово, ссылка на портфолио сохранена.")
    await send_settings(message, profile)


@dp.message(SettingsStates.waiting_for_max_budget)
async def set_max_budget(message: Message, state: FSMContext):
    raw_amount = (message.text or "").replace(" ", "").replace(chr(160), "")

    if raw_amount in ("0", "-", "без потолка"):
        profile_repository.set_max_budget(message.from_user.id, NO_MAX_BUDGET)
        await state.clear()
        await message.answer("Готово, потолок снят.")
        await send_settings(
            message, profile_repository.get(message.from_user.id)
        )
        return

    if not raw_amount.isdigit():
        await message.answer(
            "Нужно число без букв и знаков, например: 80000.\n"
            "Отправь 0, чтобы снять потолок, или /start, чтобы выйти."
        )
        return

    amount = int(raw_amount)
    profile = profile_repository.get(message.from_user.id)

    if amount < profile.min_budget:
        await message.answer(
            f"Потолок не может быть ниже минимальной суммы "
            f"({profile.min_budget} ₽). Отправь число побольше."
        )
        return

    try:
        profile_repository.set_max_budget(message.from_user.id, amount)
    except ValueError:
        await message.answer(
            f"Сумма должна быть не больше {MAX_ALLOWED_BUDGET} ₽."
        )
        return

    await state.clear()
    await message.answer(f"Готово, потолок теперь {amount} ₽.")
    await send_settings(message, profile_repository.get(message.from_user.id))


@dp.message()
async def handle_buttons(message: Message):
    if not message.text:
        # Стикер, картинка или голосовое: разбирать нечего.
        await message.answer(
            "Я разбираю только текст. Пришли текст вакансии или выбери "
            "действие в меню."
        )
        return

    profile = profile_repository.get(message.from_user.id)

    if message.text == "🔎 Найти вакансии":
        await message.answer("🔎 Ищу лучшую подходящую вакансию...")
        await show_best_vacancy(message, message.from_user.id)

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


@dp.callback_query(F.data.startswith("grp:"))
async def open_group(callback: CallbackQuery):
    group_key = callback.data.removeprefix("grp:")
    profile = profile_repository.get(callback.from_user.id)

    await callback.answer()
    await callback.message.edit_text(
        build_group_text(group_key, profile),
        parse_mode="HTML",
        reply_markup=build_group_keyboard(group_key, profile),
    )


@dp.callback_query(F.data.startswith("grpall:"))
async def toggle_whole_group(callback: CallbackQuery):
    group_key = callback.data.removeprefix("grpall:")
    profile = profile_repository.get(callback.from_user.id)
    directions = directions_in_group(group_key)

    turning_off = all(
        direction.key in profile.direction_keys for direction in directions
    )
    for direction in directions:
        is_selected = direction.key in profile.direction_keys
        if is_selected == turning_off:
            profile_repository.toggle_direction(
                callback.from_user.id, direction.key
            )

    await callback.answer("Блок снят" if turning_off else "Блок отмечен")

    profile = profile_repository.get(callback.from_user.id)
    await callback.message.edit_text(
        build_group_text(group_key, profile),
        parse_mode="HTML",
        reply_markup=build_group_keyboard(group_key, profile),
    )


@dp.callback_query(F.data == "settings:back")
async def back_to_settings(callback: CallbackQuery):
    profile = profile_repository.get(callback.from_user.id)

    await callback.answer()
    await callback.message.edit_text(
        build_settings_text(profile),
        parse_mode="HTML",
        reply_markup=build_settings_keyboard(profile),
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

    group_key = DIRECTION_BY_KEY[direction_key].group
    profile = profile_repository.get(callback.from_user.id)
    await callback.message.edit_text(
        build_group_text(group_key, profile),
        parse_mode="HTML",
        reply_markup=build_group_keyboard(group_key, profile),
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


@dp.callback_query(F.data == "settings:portfolio")
async def ask_portfolio(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_portfolio)
    await callback.answer()
    await callback.message.answer(
        "Пришли ссылку на своё портфолио — она подставляется в отклик "
        "заказчику.\n"
        "Например: https://behance.net/username"
    )


@dp.callback_query(F.data == "settings:maxbudget")
async def ask_max_budget(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SettingsStates.waiting_for_max_budget)
    await callback.answer()
    await callback.message.answer(
        "Отправь максимальную сумму за проект в рублях — вакансии дороже показываться не будут.\n"
        "Например: 80000. Отправь 0, чтобы снять потолок."
    )


@dp.callback_query(F.data == "settings:commitment")
async def switch_commitment(callback: CallbackQuery):
    """Перебирает форматы работы по кругу: любой, разовые, долгосрок."""

    profile = profile_repository.get(callback.from_user.id)
    next_commitment = COMMITMENT_CYCLE[profile.commitment]
    profile_repository.set_commitment(callback.from_user.id, next_commitment)

    await callback.answer(
        "Формат работы: " + COMMITMENT_BUTTON_LABELS[next_commitment]
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


@dp.callback_query(F.data.startswith("write:"))
async def write_to_customer(callback: CallbackQuery):
    """Отмечает отклик, отдаёт ссылку на чат и сразу ищет следующую.

    Порядок важен: ссылка уходит первой, поэтому её видно мгновенно, а
    следующая вакансия догружается, пока ты пишешь заказчику.
    """

    source_id = callback.data.removeprefix("write:")
    user_id = callback.from_user.id

    action_repository.record(user_id, source_id, RESPONDED)
    await callback.answer("Отмечено: написала")

    chat_url = take_chat_link(user_id, source_id)
    if chat_url:
        await callback.message.answer(
            "✉️ Черновик готов. Открой чат, поправь под себя и отправь.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➡️ Открыть чат с заказчиком",
                            url=chat_url,
                        )
                    ]
                ]
            ),
        )
    else:
        await callback.message.answer(
            "Черновик не сохранился — похоже, бот перезапускался. "
            "Открой вакансию заново через «🔎 Найти вакансии»."
        )

    await show_best_vacancy(callback.message, user_id)


@dp.callback_query(F.data.startswith("skip:"))
async def skip_vacancy(callback: CallbackQuery):
    source_id = callback.data.removeprefix("skip:")
    action_repository.record(callback.from_user.id, source_id, SKIPPED)

    await callback.answer("Пропущена — вернётся позже")
    await show_best_vacancy(callback.message, callback.from_user.id)


@dp.callback_query(F.data.startswith("reject:"))
async def reject_vacancy(callback: CallbackQuery):
    source_id = callback.data.removeprefix("reject:")
    action_repository.record(callback.from_user.id, source_id, REJECTED)

    await callback.answer("Больше не покажу")
    await show_best_vacancy(callback.message, callback.from_user.id)


async def main():
    logger.info("Бот запускается")

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Начать заново"),
            BotCommand(command="help", description="Что умеет бот"),
        ])
    except Exception:
        # Меню команд — украшение: без него бот работает.
        logger.exception("Не удалось установить меню команд")

    outdated = vacancy_repository.reclassify_outdated()
    if outdated:
        logger.info("Пересчитан разбор у %d сохранённых вакансий", outdated)

    collector = asyncio.create_task(
        run_collection_loop(
            vacancy_repository,
            TELEGRAM_CHANNELS,
            COLLECTOR_POST_LIMIT,
            proxy=PROXY_URL,
            interval_seconds=COLLECTION_INTERVAL_MINUTES * 60,
            first_delay_seconds=FIRST_COLLECTION_DELAY_SECONDS,
        )
    )

    try:
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Бот остановлен")
        raise
    except Exception:
        logger.exception("Опрос Telegram прервался с ошибкой")
        raise
    finally:
        collector.cancel()
        # Даём задаче свернуться, иначе на выходе сыплются предупреждения
        # о незавершённой корутине.
        await asyncio.gather(collector, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
