"""Суммы в том виде, в каком их видит пользователь.

Разбор бюджета живёт в `filter.py`, а здесь только показ его результата.
"""


# Неразрывный пробел: «20 000» читается легче, чем «20000», и при этом
# не разъезжается по двум строкам на узком экране.
THOUSANDS_SEPARATOR = "\u00a0"


def format_amount(amount):
    """Разбивает сумму на тройки: 20000 → 20 000."""

    return f"{amount:,}".replace(",", THOUSANDS_SEPARATOR)


def format_budget(budget):
    """Форматирует бюджет с упором на итоговую сумму за проект."""

    payment_type = budget["payment_type"]

    if payment_type == "fixed":
        return f"{format_amount(budget['estimated_project_total'])} ₽ за проект"

    if payment_type == "range":
        return (
            f"{format_amount(budget['min_amount'])}–"
            f"{format_amount(budget['max_amount'])} ₽ за проект"
        )

    if payment_type == "from":
        return f"от {format_amount(budget['min_amount'])} ₽ за проект"

    if payment_type == "hourly":
        rate = f"{format_amount(budget['hourly_rate'])} ₽/час"
        if budget["estimated_project_total"] is None:
            return f"{rate}; количество часов не указано"
        return (
            f"{rate}; {budget['hours']} ч. = "
            f"{format_amount(budget['estimated_project_total'])} ₽ за проект"
        )

    return "не указана"
