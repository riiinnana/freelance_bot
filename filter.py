"""Разбор вакансии и примерка её под профиль пользователя.

Проверка разделена на два шага:

* `classify_vacancy` читает текст вакансии и не зависит от пользователя.
  Результат одинаков для всех, поэтому его достаточно посчитать один раз.
* `evaluate_for_user` берёт готовый разбор и быстро сверяет его с профилем.
  Текст вакансии на этом шаге уже не читается.
"""

import re

from directions import DIRECTIONS, direction_names
from filter_settings import UNIVERSAL_STOP_WORDS


NUMBER = r"(\d{1,3}(?:[  ]\d{3})+|\d+)"
CURRENCY = r"(?:₽|руб(?:лей|ля|ль)?|р\.)"

# Направление не входит в выбранные, поэтому вакансия ниже в выдаче.
OFF_PROFILE_PRIORITY = 10 ** 6


def _compile_keyword(keyword):
    """Собирает шаблон поиска ключевого слова.

    Звёздочка означает «и любое окончание», поэтому `"презентаци*"` найдёт
    и презентацию, и презентаций. Поиск всегда начинается с начала слова, а
    слово без звёздочки должно совпасть целиком — так «моушн» перестаёт
    находиться в середине постороннего слова.
    """

    parts = [re.escape(part) for part in keyword.split("*")]
    pattern = r"\b" + r"\w*".join(parts)
    if not keyword.endswith("*"):
        pattern += r"\b"
    return re.compile(pattern, re.IGNORECASE)


def _compile_keywords(keywords):
    """Возвращает пары «слово для показа — шаблон поиска»."""

    return tuple(
        (keyword.replace("*", ""), _compile_keyword(keyword))
        for keyword in keywords
    )


# Шаблоны собираются один раз при загрузке модуля, а не на каждую вакансию.
_DIRECTION_PATTERNS = tuple(
    (direction, _compile_keywords(direction.keywords))
    for direction in DIRECTIONS
)

_STOP_WORD_PATTERNS = _compile_keywords(UNIVERSAL_STOP_WORDS)


def _parse_number(value):
    return int(value.replace(" ", "").replace(" ", ""))


def _find_hours(text):
    match = re.search(
        rf"(?:на|около|примерно|до)?\s*{NUMBER}\s*(?:час(?:а|ов)?|ч\b)",
        text.lower(),
    )
    return _parse_number(match.group(1)) if match else None


def extract_budget(text):
    """Возвращает сведения о бюджете и расчёт суммы за проект.

    Поддерживаются фиксированная сумма, диапазон и почасовая ставка. Для
    почасовой ставки итог считается только при указанном количестве часов.
    """

    text_lower = text.lower()

    hourly_match = re.search(
        rf"{NUMBER}\s*{CURRENCY}\s*(?:/|в\s+|за\s+)(?:час|ч\b)",
        text_lower,
    )
    if hourly_match:
        hourly_rate = _parse_number(hourly_match.group(1))
        hours = _find_hours(text_lower)
        total = hourly_rate * hours if hours is not None else None
        return {
            "payment_type": "hourly",
            "amount": total,
            "min_amount": total,
            "max_amount": total,
            "hourly_rate": hourly_rate,
            "hours": hours,
            "estimated_project_total": total,
        }

    range_match = re.search(
        rf"(?:от\s*)?{NUMBER}\s*(?:-|–|—|до)\s*{NUMBER}\s*{CURRENCY}",
        text_lower,
    )
    if range_match:
        minimum = _parse_number(range_match.group(1))
        maximum = _parse_number(range_match.group(2))
        return {
            "payment_type": "range",
            "amount": None,
            "min_amount": minimum,
            "max_amount": maximum,
            "hourly_rate": None,
            "hours": None,
            "estimated_project_total": None,
        }

    fixed_match = re.search(
        rf"{NUMBER}\s*{CURRENCY}|(?:бюджет|оплата|стоимость)[^\d]{{0,20}}{NUMBER}",
        text_lower,
    )
    if fixed_match:
        amount = _parse_number(next(value for value in fixed_match.groups() if value))
        return {
            "payment_type": "fixed",
            "amount": amount,
            "min_amount": amount,
            "max_amount": amount,
            "hourly_rate": None,
            "hours": None,
            "estimated_project_total": amount,
        }

    return {
        "payment_type": None,
        "amount": None,
        "min_amount": None,
        "max_amount": None,
        "hourly_rate": None,
        "hours": None,
        "estimated_project_total": None,
    }


def find_directions(text):
    """Возвращает ключи найденных направлений и совпавшие ключевые слова."""

    direction_keys = []
    matched_keywords = []

    for direction, patterns in _DIRECTION_PATTERNS:
        matches = [
            keyword for keyword, pattern in patterns if pattern.search(text)
        ]
        if matches:
            direction_keys.append(direction.key)
            matched_keywords.extend(matches)

    return direction_keys, matched_keywords


def find_stop_words(text):
    """Возвращает универсальные стоп-слова, найденные в тексте вакансии."""

    return [
        keyword for keyword, pattern in _STOP_WORD_PATTERNS
        if pattern.search(text)
    ]


def classify_vacancy(text):
    """Разбирает вакансию независимо от пользователя.

    Результат можно посчитать один раз при сборе и сохранить: он не зависит
    от того, кто именно будет смотреть вакансию.
    """

    direction_keys, matched_keywords = find_directions(text)

    return {
        "budget": extract_budget(text),
        "direction_keys": direction_keys,
        "matched_keywords": matched_keywords,
        "matched_stop_words": find_stop_words(text),
    }


def _matched_profile_directions(classification, profile):
    """Возвращает подходящие направления в порядке приоритета пользователя."""

    found = set(classification["direction_keys"])
    return [key for key in profile.direction_keys if key in found]


def _result(classification, status, reason_code, reason, profile_keys, priority):
    return {
        "status": status,
        "suitable": status != "red",
        "reason_code": reason_code,
        "reason": reason,
        "budget": classification["budget"],
        "direction_keys": classification["direction_keys"],
        "work_types": direction_names(classification["direction_keys"]),
        "profile_direction_keys": profile_keys,
        "matched_keywords": classification["matched_keywords"],
        "matched_stop_words": classification["matched_stop_words"],
        "off_profile": not profile_keys,
        "priority": priority,
    }


def evaluate_for_user(classification, profile):
    """Сверяет готовый разбор вакансии с профилем пользователя."""

    stop_words = classification["matched_stop_words"]
    if stop_words:
        return _result(
            classification, "red", "stop_words",
            "Неподходящий тип работы: " + ", ".join(stop_words),
            [], OFF_PROFILE_PRIORITY,
        )

    if not classification["direction_keys"]:
        return _result(
            classification, "red", "no_direction",
            "Не найдено подходящее направление дизайна",
            [], OFF_PROFILE_PRIORITY,
        )

    profile_keys = _matched_profile_directions(classification, profile)
    priority = (
        profile.direction_keys.index(profile_keys[0])
        if profile_keys
        else OFF_PROFILE_PRIORITY
    )

    if not profile_keys and profile.strict_mode:
        return _result(
            classification, "red", "off_profile_strict",
            "Направление не входит в твои настройки: "
            + ", ".join(direction_names(classification["direction_keys"])),
            profile_keys, priority,
        )

    budget = classification["budget"]
    maximum = budget["max_amount"]
    minimum = budget["min_amount"]

    if maximum is not None and maximum < profile.min_budget:
        return _result(
            classification, "red", "budget_too_low",
            f"Сумма за проект ниже {profile.min_budget} ₽",
            profile_keys, priority,
        )

    if minimum is not None and minimum < profile.min_budget:
        return _result(
            classification, "yellow", "budget_may_be_low",
            f"Сумма за проект может быть ниже {profile.min_budget} ₽",
            profile_keys, priority,
        )

    if budget["payment_type"] == "hourly" and budget["hours"] is None:
        return _result(
            classification, "yellow", "hours_unknown",
            "Указана почасовая ставка, но не указано количество часов",
            profile_keys, priority,
        )

    if maximum is None:
        return _result(
            classification, "yellow", "budget_unknown",
            "Подходящее направление, но сумма за проект не указана",
            profile_keys, priority,
        )

    if not profile_keys:
        return _result(
            classification, "yellow", "off_profile",
            "Подходит по сумме, но это не твоё основное направление: "
            + ", ".join(direction_names(classification["direction_keys"])),
            profile_keys, priority,
        )

    return _result(
        classification, "green", "match",
        "Подходит по сумме за проект; подходит по направлению: "
        + ", ".join(direction_names(profile_keys)),
        profile_keys, priority,
    )


def analyze_vacancy(text, profile):
    """Разбирает вакансию и сразу примеряет её под профиль пользователя."""

    return evaluate_for_user(classify_vacancy(text), profile)
