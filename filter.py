"""Разбор вакансии и примерка её под профиль пользователя.

Проверка разделена на два шага:

* `classify_vacancy` читает текст вакансии и не зависит от пользователя.
  Результат одинаков для всех, поэтому его достаточно посчитать один раз.
* `evaluate_for_user` берёт готовый разбор и быстро сверяет его с профилем.
  Текст вакансии на этом шаге уже не читается.
"""

import re

from commitment import ANY, commitment_name, detect_commitment
from directions import DIRECTIONS, direction_names
from filter_settings import UNIVERSAL_STOP_WORDS
from keywords import compile_keywords, find_matches
from roles import hires_someone_else
from vacancy_summary import build_title


NUMBER = r"(\d{1,3}(?:[  ]\d{3})+|\d+)"
CURRENCY = r"(?:₽|руб(?:лей|ля|ль)?|р\.)"

# «5к», «15 тыс.», «20 тысяч» — так пишут постоянно, а без разбора «5к»
# читалось как пять рублей, и вакансия отсеивалась как слишком дешёвая.
THOUSANDS = r"(?:к|k|тыс\.?|тысяч(?:а|и)?)"

# Ниже этой суммы число в диапазоне без валюты — почти наверняка не деньги,
# а количество правок, недель или чего-то ещё.
MIN_MEANINGFUL_AMOUNT = 500

# Сначала диапазон с общим сокращением: в «5-10к» тысячи относятся к обоим
# числам, хотя написаны один раз.
THOUSANDS_RANGE_PATTERN = re.compile(
    rf"(?<![\d.,])(\d{{1,4}})\s*[-–—]\s*(\d{{1,4}})\s*{THOUSANDS}(?![а-яa-z])",
    re.IGNORECASE,
)

THOUSANDS_PATTERN = re.compile(
    rf"(?<![\d.,])(\d{{1,4}})\s*{THOUSANDS}(?![а-яa-z])",
    re.IGNORECASE,
)


def expand_thousands(text):
    """Разворачивает сокращения тысяч в обычные числа."""

    text = THOUSANDS_RANGE_PATTERN.sub(
        lambda match: "%d-%d"
        % (int(match.group(1)) * 1000, int(match.group(2)) * 1000),
        text,
    )
    return THOUSANDS_PATTERN.sub(
        lambda match: str(int(match.group(1)) * 1000), text
    )

# Направление не входит в выбранные, поэтому вакансия ниже в выдаче.
OFF_PROFILE_PRIORITY = 10 ** 6


# Шаблоны собираются один раз при загрузке модуля, а не на каждую вакансию.
_DIRECTION_PATTERNS = tuple(
    (direction, compile_keywords(direction.keywords))
    for direction in DIRECTIONS
)

_STOP_WORD_PATTERNS = compile_keywords(UNIVERSAL_STOP_WORDS)


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

    text_lower = expand_thousands(text.lower())

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

    if range_match is None:
        # «бюджет 5-10к»: валюту часто не пишут, раз она понятна из слова
        # «бюджет». Мелкие числа при этом игнорируем, иначе «оплата 2-3 раза
        # в месяц» превратилась бы в диапазон two-three рублей.
        budget_range_match = re.search(
            rf"(?:бюджет|оплата|стоимость)[^\d]{{0,20}}"
            rf"{NUMBER}\s*(?:-|–|—|до)\s*{NUMBER}",
            text_lower,
        )
        if budget_range_match and min(
            _parse_number(budget_range_match.group(1)),
            _parse_number(budget_range_match.group(2)),
        ) >= MIN_MEANINGFUL_AMOUNT:
            range_match = budget_range_match

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

    # «от 5000 ₽» — это нижняя граница, а не точная сумма. Проверяется после
    # диапазона, иначе «от 20 000 до 40 000» потеряло бы верхнюю границу.
    open_ended_match = re.search(rf"от\s*{NUMBER}\s*{CURRENCY}", text_lower)
    if open_ended_match:
        minimum = _parse_number(open_ended_match.group(1))
        return {
            "payment_type": "from",
            "amount": None,
            "min_amount": minimum,
            "max_amount": None,
            "hourly_rate": None,
            "hours": None,
            "estimated_project_total": None,
        }

    # Валюта — сильный признак, поэтому сумма с ней ищется первой. Раньше обе
    # возможности стояли в одном шаблоне, и в «оплата 2-3 раза в месяц,
    # 50 000 руб.» побеждала двойка просто потому, что была левее.
    fixed_match = re.search(rf"{NUMBER}\s*{CURRENCY}", text_lower)

    if fixed_match is None:
        near_budget_word = re.search(
            rf"(?:бюджет|оплата|стоимость)[^\d]{{0,20}}{NUMBER}", text_lower
        )
        if (
            near_budget_word
            and _parse_number(near_budget_word.group(1)) >= MIN_MEANINGFUL_AMOUNT
        ):
            fixed_match = near_budget_word

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
        matches = find_matches(text, patterns)
        if matches:
            direction_keys.append(direction.key)
            matched_keywords.extend(matches)

    return direction_keys, matched_keywords


def find_stop_words(text):
    """Возвращает универсальные стоп-слова, найденные в тексте вакансии."""

    return find_matches(text, _STOP_WORD_PATTERNS)


def classify_vacancy(text):
    """Разбирает вакансию независимо от пользователя.

    Результат можно посчитать один раз при сборе и сохранить: он не зависит
    от того, кто именно будет смотреть вакансию.
    """

    direction_keys, matched_keywords = find_directions(text)

    return {
        "budget": extract_budget(text),
        "commitment": detect_commitment(text),
        "direction_keys": direction_keys,
        "matched_keywords": matched_keywords,
        "matched_stop_words": find_stop_words(text),
        # Решается по заголовку: в теле «дизайн» и «smm» идут вперемешку,
        # а в заголовке стоит именно та роль, которую зовут.
        "hires_someone_else": hires_someone_else(build_title(text)),
    }


# Ключи, которые должен содержать свежий разбор. По ним видно, что
# сохранённая вакансия разбиралась старой версией и требует пересчёта.
CLASSIFICATION_KEYS = frozenset(
    {
        "budget",
        "commitment",
        "direction_keys",
        "matched_keywords",
        "matched_stop_words",
        "hires_someone_else",
    }
)


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
        # У вакансий, разобранных прошлой версией, ключа может не быть.
        "commitment": classification.get("commitment"),
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

    # Стоп-слова смотрят на весь текст, а это — на то, кого зовут.
    # У эсэмэмщика в вакансии честно есть и «креативы», и «reels», и
    # «обложки» — по словам она проходит, по работе нет.
    if classification.get("hires_someone_else"):
        return _result(
            classification, "red", "another_role",
            "Ищут не дизайнера, а другого специалиста",
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

    # Формат работы проверяется до денег: это предпочтение о том, во что
    # вообще ввязываться. Неопределённый формат проходит дальше — прямо о
    # длительности пишут редко, и прятать такие вакансии нельзя.
    commitment = classification.get("commitment")
    if (
        profile.commitment != ANY
        and commitment is not None
        and commitment != profile.commitment
    ):
        return _result(
            classification, "red", "wrong_commitment",
            "Не тот формат работы: " + commitment_name(commitment),
            profile_keys, priority,
        )

    budget = classification["budget"]
    maximum = budget["max_amount"]
    minimum = budget["min_amount"]

    if (
        profile.max_budget
        and minimum is not None
        and minimum > profile.max_budget
    ):
        return _result(
            classification, "red", "budget_too_high",
            f"Сумма за проект выше {profile.max_budget} ₽",
            profile_keys, priority,
        )

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

    if budget["payment_type"] == "from" and minimum is not None:
        return _result(
            classification, "green", "match",
            f"Сумма от {minimum} ₽ — не ниже твоего минимума; "
            "подходит по направлению: " + ", ".join(direction_names(profile_keys)),
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
