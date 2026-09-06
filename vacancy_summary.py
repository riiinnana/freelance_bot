"""Что показывать в карточке вакансии: должность и суть задачи.

Заголовком раньше становилась просто первая строка поста. Но посты часто
начинаются с приветствия или эмодзи — «Ну как дела в школе? 😂», «🎯🎯🎯»,
— и в карточке оказывалась именно она. Здесь текст разбирается на строки
и из них выбирается та, где названа роль: «Монтажёр», «Ищем графического
дизайнера», «#дизайнер_презентаций».

Суть задачи ищется по заголовкам разделов, которые почти всегда есть в
таких постах: «Задачи», «Что делать», «Чем предстоит заниматься». Если
разделов нет, берутся первые строки, похожие на описание работы.
"""

import re

from keywords import compile_keywords, has_match


# Названия ролей. Звёздочка — «и любое окончание», как в остальных
# списках проекта: «дизайнера», «дизайнеру» находятся тем же словом.
ROLE_KEYWORDS = (
    "дизайнер*",
    "дизайнеры",
    "графдизайнер*",
    "вебдизайнер*",
    "веб-дизайнер*",
    "designer*",
    "design lead",
    "иллюстратор*",
    "аниматор*",
    "моушн*",
    "motion*",
    "моделлер*",
    "моделер*",
    "modeler*",
    "3d-артист*",
    "3d артист*",
    "cg-артист*",
    "concept artist*",
    "концепт-артист*",
    "художник*",
    "монтажёр*",
    "монтажер*",
    "видеомонтажёр*",
    "видеомонтажер*",
    "видеомейкер*",
    "ретушёр*",
    "ретушер*",
    "визуализатор*",
    "риггер*",
    "верстальщик*",
    "креатор*",
    "арт-директор*",
    "артдиректор*",
    "art director*",
    "editor*",
    "animator*",
    "illustrator*",
)

ROLE_PATTERNS = compile_keywords(ROLE_KEYWORDS)

# Заголовки разделов, после которых идёт описание работы.
TASK_HEADERS = (
    "задача",
    "задачи",
    "задачки",
    "что делать",
    "что нужно",
    "что нужно делать",
    "что нужно сделать",
    "что требуется",
    "что предстоит",
    "чем предстоит заниматься",
    "чем предстоит",
    "обязанности",
    "описание",
    "описание задачи",
    "суть",
    "суть задачи",
    "суть проекта",
    "о задаче",
    "о проекте",
    "функционал",
    "примеры задач",
    "объём работ",
    "объем работ",
)

# Заголовки, на которых описание работы заканчивается.
STOP_HEADERS = (
    "требовани",
    "требуется от",
    "ждём",
    "ждем",
    "ожидаем",
    "что мы ожидаем",
    "что мы ждём",
    "что мы ждем",
    "что важно",
    "нам важно",
    "наши ожидания",
    "кого ищем",
    "кого мы ищем",
    "от тебя",
    "от вас",
    "пожелания",
    "условия",
    "условие",
    "оплата",
    "бюджет",
    "гонорар",
    "стоимость",
    "зарплата",
    "зп",
    "формат",
    "график",
    "сроки",
    "срок",
    "о нас",
    "о компании",
    "контакт",
    "отклик",
    "как откликнуться",
    "для отклика",
    "что мы предлагаем",
    "мы предлагаем",
    "предлагаем",
    "плюсом",
    "будет плюсом",
    "портфолио",
    "навыки",
    "стек",
    "инструменты",
    "локация",
    "занятость",
    "тип занятости",
)

# Строки-описания без заголовка обычно начинаются с такого глагола.
TASK_CUES = (
    "нужно",
    "нужен",
    "нужна",
    "нужны",
    "требуется",
    "требуются",
    "ищем",
    "ищет",
    "ищут",
    "ищу",
    "разработать",
    "сделать",
    "создать",
    "отрисовать",
    "смонтировать",
    "собрать",
    "оформить",
    "нарисовать",
    "анимировать",
    "снять",
    "предстоит",
    "работа",
    "проект",
)

TASK_CUE_PATTERNS = compile_keywords(tuple(cue + "*" for cue in TASK_CUES))

MAX_TITLE_LENGTH = 90
MAX_TASK_LENGTH = 350

# Сколько строк с начала поста имеет смысл рассматривать как заголовок.
TITLE_SEARCH_LINES = 12

_HEADER_SPLIT = re.compile(r"[:—–-]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_LINK = re.compile(r"https?://|t\.me/|@[A-Za-z0-9_]{4,}|\+?\d[\d\s()-]{8,}")
_MONEY_ONLY = re.compile(
    r"^[^\w]*(?:бюджет|оплата|стоимость|цена|гонорар|зп|зарплата|ставка)\b"
    r"[^а-яё]*$",
    re.IGNORECASE,
)

# Эмодзи и знаки в начале строки. Цифры не трогаем: «3D-визуализатор»
# начинается с цифры, и без неё остался бы «d визуализатор».
_LEADING_MARKS = re.compile(r"^[^\w]+", re.UNICODE)
# Нумерация пункта в подборке: «1.», «2)».
_LIST_NUMBER = re.compile(r"^\d+\s*[.)]\s*")
# Слова-ярлыки перед самой должностью.
_LABEL = re.compile(
    r"^(?:объявление|вакансия|вакансии|срочно)\b[\s:—–-]*", re.IGNORECASE
)
# Строка целиком из хештегов — в подборках так начинается новый пункт.
_HASHTAGS_ONLY = re.compile(r"^[\W]*(?:#[\w]+[\s/,|]*)+$", re.UNICODE)
# Тег в скобках перед должностью: «(#Удаленка) Требуется SMM-специалист».
_LEADING_TAG = re.compile(r"^[^\w(]*\([^)]{0,40}\)\s*")


def _strip_marks(text):
    """Снимает ведущие эмодзи, нумерацию и слова-ярлыки."""

    text = _LEADING_TAG.sub("", text.strip())
    text = _LEADING_MARKS.sub("", text)
    text = _LIST_NUMBER.sub("", text)
    text = _LEADING_MARKS.sub("", text)
    return _LABEL.sub("", text)


def _clean_line(line):
    """Убирает нумерацию, эмодзи и решётки, оставляя сам текст."""

    line = _strip_marks(line.replace("​", ""))
    line = line.replace("#", "").replace("_", " ")
    return re.sub(r"\s+", " ", line).strip(" -—–•·|:;,")


def _capitalize(text):
    """Первая буква заглавная — заголовки из хештегов идут строчными."""

    if text[:1].islower():
        return text[0].upper() + text[1:]
    return text


def _is_meaningful(line):
    """Есть ли в строке слова, а не только эмодзи и знаки."""

    return len(_LETTER.findall(line)) >= 3


def _trim(text, limit):
    """Обрезает по границе слова, чтобы не рвать слово посередине."""

    if len(text) <= limit:
        return text

    cut = text[:limit].rstrip()
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(" ,.;:-—–") + "…"


def _role_sentence(line):
    """Из длинной строки берёт предложение, где названа роль."""

    if len(line) <= MAX_TITLE_LENGTH:
        return line

    for sentence in _SENTENCE_SPLIT.split(line):
        if has_match(sentence, ROLE_PATTERNS):
            return _strip_marks(sentence).rstrip(" -—–:;,")
    return line


def extract_role(text):
    """Возвращает должность из поста или None, если её не видно."""

    seen = 0
    for raw in text.splitlines():
        line = _clean_line(raw)
        if not _is_meaningful(line):
            continue
        if has_match(line, ROLE_PATTERNS):
            return _capitalize(_trim(_role_sentence(line), MAX_TITLE_LENGTH))
        seen += 1
        if seen >= TITLE_SEARCH_LINES:
            break

    return None


def build_title(text, fallback=""):
    """Заголовок карточки: должность, иначе первая осмысленная строка."""

    role = extract_role(text)
    if role:
        return role

    for raw in text.splitlines():
        line = _clean_line(raw)
        if _is_meaningful(line):
            return _capitalize(_trim(line, MAX_TITLE_LENGTH))

    return _capitalize(_trim(_clean_line(fallback), MAX_TITLE_LENGTH))


def _starts_with(line, prefixes):
    lowered = _clean_line(line).lower()
    head = _HEADER_SPLIT.split(lowered, 1)[0].strip()
    return any(head == prefix or head.startswith(prefix) for prefix in prefixes)


def _is_noise(raw):
    """Контакты, ссылки и строки про деньги в суть задачи не идут.

    Проверяется исходная строка, а не очищенная: очистка снимает ведущие
    знаки, и «➡️ @muzykalarisa» превращается в безобидное «muzykalarisa».
    """

    return bool(_LINK.search(raw)) or bool(_MONEY_ONLY.match(raw.strip()))


def _is_next_item(raw):
    """Начало следующей вакансии в подборке из нескольких штук."""

    stripped = raw.replace("​", "").strip()
    if _HASHTAGS_ONLY.match(stripped):
        return True
    # «1. #Монтажер» — нумерация вместе с хештегом. Просто нумерация не
    # считается: списком задач тоже часто нумеруют.
    return bool(_LIST_NUMBER.match(stripped)) and "#" in stripped


def _collect(lines, start, skip_first_line_noise):
    """Собирает строки описания подряд, пока они относятся к делу."""

    collected = []
    length = 0

    for offset, raw in enumerate(lines[start:]):
        if offset and (_starts_with(raw, STOP_HEADERS) or _is_next_item(raw)):
            break

        line = _clean_line(raw)
        if not _is_meaningful(line):
            continue

        if _is_noise(raw):
            # Контакт заказчика закрывает описание. Пока описания нет,
            # это просто шапка поста — её пропускаем.
            if collected:
                break
            if skip_first_line_noise:
                continue
            break

        collected.append(line)
        length += len(line)
        if length >= MAX_TASK_LENGTH:
            break

    return collected


def _format_task(collected):
    if not collected:
        return None

    if len(collected) == 1:
        return _trim(collected[0], MAX_TASK_LENGTH)

    text = ""
    for line in collected:
        addition = ("\n• " if text else "• ") + line
        if len(text) + len(addition) > MAX_TASK_LENGTH:
            text += ("\n• " if text else "• ") + _trim(
                line, MAX_TASK_LENGTH - len(text) - 3
            )
            break
        text += addition

    return text


def extract_task(text, title=""):
    """Возвращает суть задачи или None, если описания в посте нет."""

    lines = text.splitlines()

    for index, raw in enumerate(lines):
        if not _starts_with(raw, TASK_HEADERS):
            continue

        # После двоеточия описание часто начинается прямо в строке
        # заголовка: «Задача — создавать статичные и видео-креативы».
        collected = []
        separator = _HEADER_SPLIT.search(lines[index])
        tail = (
            _clean_line(lines[index][separator.end():]) if separator else ""
        )
        if _is_meaningful(tail) and not _is_noise(tail):
            collected.append(tail)

        collected += _collect(lines, index + 1, skip_first_line_noise=False)
        formatted = _format_task(collected)
        if formatted:
            return formatted

    # Раздела нет — берём строки, похожие на описание работы.
    for index, raw in enumerate(lines):
        line = _clean_line(raw)
        if not _is_meaningful(line) or _is_noise(raw):
            continue
        if title and line[:40] == title[:40]:
            continue
        if _starts_with(raw, STOP_HEADERS):
            continue
        if not has_match(line, TASK_CUE_PATTERNS):
            continue
        return _format_task(_collect(lines, index, skip_first_line_noise=True))

    return None
