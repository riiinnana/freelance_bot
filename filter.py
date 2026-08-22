import re

from filter_settings import EXCLUDED_KEYWORDS, MIN_PROJECT_BUDGET, WORK_TYPES


NUMBER = r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+)"
CURRENCY = r"(?:₽|руб(?:лей|ля|ль)?|р\.)"


def _parse_number(value):
    return int(value.replace(" ", "").replace("\u00a0", ""))


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


def find_work_types(text):
    """Возвращает подходящие направления и совпавшие ключевые слова."""

    text_lower = text.lower()
    work_types = []
    matched_keywords = []

    for work_type, keywords in WORK_TYPES.items():
        matches = [keyword for keyword in keywords if keyword.lower() in text_lower]
        if matches:
            work_types.append(work_type)
            matched_keywords.extend(matches)

    return work_types, matched_keywords


def find_stop_words(text):
    """Возвращает стоп-слова, найденные в тексте вакансии."""

    text_lower = text.lower()
    return [keyword for keyword in EXCLUDED_KEYWORDS if keyword.lower() in text_lower]


def _result(status, suitable, budget, work_types, matched_keywords, stop_words, reason):
    return {
        "status": status,
        "suitable": suitable,
        "budget": budget,
        "work_types": work_types,
        "matched_keywords": matched_keywords,
        "matched_stop_words": stop_words,
        "reason": reason,
    }


def analyze_vacancy(text):
    """Анализирует вакансию и оценивает общую сумму за проект."""

    budget = extract_budget(text)
    work_types, matched_keywords = find_work_types(text)
    stop_words = find_stop_words(text)

    if stop_words:
        return _result(
            "red", False, budget, work_types, matched_keywords, stop_words,
            "Неподходящий тип работы: " + ", ".join(stop_words),
        )

    if not work_types:
        return _result(
            "red", False, budget, [], matched_keywords, stop_words,
            "Не найдено подходящее направление дизайна",
        )

    maximum = budget["max_amount"]
    minimum = budget["min_amount"]

    if maximum is not None and maximum < MIN_PROJECT_BUDGET:
        return _result(
            "red", False, budget, work_types, matched_keywords, stop_words,
            f"Сумма за проект ниже {MIN_PROJECT_BUDGET} ₽",
        )

    if minimum is not None and minimum < MIN_PROJECT_BUDGET:
        return _result(
            "yellow", True, budget, work_types, matched_keywords, stop_words,
            f"Сумма за проект может быть ниже {MIN_PROJECT_BUDGET} ₽",
        )

    if budget["payment_type"] == "hourly" and budget["hours"] is None:
        return _result(
            "yellow", True, budget, work_types, matched_keywords, stop_words,
            "Указана почасовая ставка, но не указано количество часов",
        )

    if maximum is None:
        return _result(
            "yellow", True, budget, work_types, matched_keywords, stop_words,
            "Подходящее направление, но сумма за проект не указана",
        )

    return _result(
        "green", True, budget, work_types, matched_keywords, stop_words,
        "Подходит по сумме за проект; подходит по направлению: "
        + ", ".join(work_types),
    )
