"""Подготовка контакта и ссылки с черновиком отклика."""

import re
from urllib.parse import quote

from application_settings import APPLICATION_TEMPLATE
from config import PORTFOLIO_URL


CONTACT_PATTERN = re.compile(
    r"(?:https?://t\.me/|(?<!\w)@)([A-Za-z][A-Za-z0-9_]{4,31})(?:[/?#]|\b)",
    re.IGNORECASE,
)


def extract_contact_username(text):
    """Возвращает последний публичный Telegram-контакт из текста вакансии."""

    usernames = CONTACT_PATTERN.findall(text)
    return usernames[-1] if usernames else None


def build_application_text(title):
    """Создаёт редактируемый черновик отклика."""

    return APPLICATION_TEMPLATE.format(
        title=title,
        portfolio_url=PORTFOLIO_URL,
    )


def build_chat_link(username, text):
    """Создаёт ссылку на личный чат с предзаполненным текстом."""

    return f"https://t.me/{username}?text={quote(text)}"
