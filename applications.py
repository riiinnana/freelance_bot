"""Подготовка контакта и ссылки с черновиком отклика."""

import re
from urllib.parse import quote

from application_settings import APPLICATION_TEMPLATE
from config import PORTFOLIO_URL


USERNAME = r"[A-Za-z][A-Za-z0-9_]{4,31}"

# Упоминание вида @username.
MENTION_PATTERN = re.compile(rf"(?<!\w)@({USERNAME})\b")

# Ссылка вида t.me/username. Хвост «/123» означает ссылку на конкретный пост
# канала, а не на профиль человека, и контактом не считается.
LINK_PATTERN = re.compile(
    rf"(?:https?://)?t\.me/({USERNAME})(/\d+)?",
    re.IGNORECASE,
)

# Служебные адреса Telegram: это не имена пользователей.
RESERVED_USERNAMES = {
    "joinchat", "addstickers", "addlist", "addemoji", "share", "proxy",
    "socks", "setlanguage", "confirmphone", "login", "iv",
}

# Слова, рядом с которыми обычно стоит контакт заказчика. Помогают отличить
# его от подписи канала в конце поста.
CONTACT_CUE_PATTERN = re.compile(
    r"\b(?:писать|пишите|пиши|напиш\w*|вопрос\w*|контакт\w*|связ\w*|"
    r"отклик\w*|резюме|лс|личк\w*|заказчик\w*|телеграм\w*|telegram|tg)\b",
    re.IGNORECASE,
)

# Сколько символов перед контактом просматривать в поисках такого слова.
CUE_WINDOW = 80


def _find_candidates(text):
    """Возвращает пары «позиция в тексте — имя пользователя»."""

    candidates = [
        (match.start(), match.group(1))
        for match in MENTION_PATTERN.finditer(text)
    ]

    for match in LINK_PATTERN.finditer(text):
        if match.group(2):
            continue
        candidates.append((match.start(), match.group(1)))

    candidates.sort()
    return candidates


def _has_contact_cue(text, position):
    window = text[max(0, position - CUE_WINDOW):position]
    return CONTACT_CUE_PATTERN.search(window) is not None


def extract_contact_username(text, source_username=None, excluded_usernames=()):
    """Возвращает Telegram-контакт заказчика из текста вакансии.

    Подпись канала в конце поста контактом не считается: из кандидатов
    убираются сам источник, другие подключённые каналы и служебные адреса
    Telegram. Из оставшихся предпочтение отдаётся тому, рядом с которым
    стоит слово вроде «писать» или «по вопросам».
    """

    excluded = {name.lower().lstrip("@") for name in excluded_usernames}
    excluded.update(RESERVED_USERNAMES)
    if source_username:
        excluded.add(source_username.lower().lstrip("@"))

    candidates = [
        (position, username)
        for position, username in _find_candidates(text)
        if username.lower() not in excluded
    ]

    if not candidates:
        return None

    for position, username in candidates:
        if _has_contact_cue(text, position):
            return username

    return candidates[-1][1]


def build_application_text(title):
    """Создаёт редактируемый черновик отклика."""

    return APPLICATION_TEMPLATE.format(
        title=title,
        portfolio_url=PORTFOLIO_URL,
    )


def build_chat_link(username, text):
    """Создаёт ссылку на личный чат с предзаполненным текстом."""

    return f"https://t.me/{username}?text={quote(text)}"
