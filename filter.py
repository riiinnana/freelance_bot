import re

from config import MIN_BUDGET, WORK_TYPES, EXCLUDED_KEYWORDS

def extract_budget(text):
    """
    Ищет бюджет вакансии в тексте.
    Возвращает число или None, если бюджет не найден.
    """

    patterns = [
        r"(\d[\d\s]*)\s*(?:₽|руб(?:лей|ля)?|р\.)",
        r"(?:бюджет|оплата|стоимость)[^\d]{0,20}(\d[\d\s]*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text.lower())

        if match:
            budget_text = match.group(1)
            budget_text = budget_text.replace(" ", "")
            return int(budget_text)

    return None


def find_work_types(text):
    """
    Ищет подходящие направления дизайна
    по набору ключевых слов.
    """

    text_lower = text.lower()

    found = []

    for work_type, keywords in WORK_TYPES.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                found.append(work_type)
                break

    return found


def analyze_vacancy(text):
    """
    Анализирует вакансию и возвращает статус:
    green  = подходит
    yellow = нужно проверить
    red    = не подходит
    """

    text_lower = text.lower()

    budget = extract_budget(text)
    work_types = find_work_types(text)

    # Проверяем исключения
    excluded = []

    for keyword in EXCLUDED_KEYWORDS:
        if keyword.lower() in text_lower:
            excluded.append(keyword)

    if excluded:
        return {
            "status": "red",
            "suitable": False,
            "budget": budget,
            "work_types": work_types,
            "reason": (
                "Неподходящий тип работы: "
                + ", ".join(excluded)
            ),
        }

    # Проверяем направление
    if not work_types:
        return {
            "status": "red",
            "suitable": False,
            "budget": budget,
            "work_types": [],
            "reason": "Не найдено подходящее направление дизайна",
        }

    # Проверяем бюджет
    if budget is not None and budget < MIN_BUDGET:
        return {
            "status": "red",
            "suitable": False,
            "budget": budget,
            "work_types": work_types,
            "reason": f"Бюджет ниже {MIN_BUDGET} ₽",
        }

    # Бюджет не указан
    if budget is None:
        return {
            "status": "yellow",
            "suitable": True,
            "budget": None,
            "work_types": work_types,
            "reason": (
                "Подходящее направление, "
                "но бюджет не указан"
            ),
        }

    # Всё подходит
    return {
        "status": "green",
        "suitable": True,
        "budget": budget,
        "work_types": work_types,
        "reason": (
            "Подходит по бюджету; "
            "подходит по направлению: "
            + ", ".join(work_types)
        ),
    }