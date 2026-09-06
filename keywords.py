"""Поиск ключевых слов по тексту вакансии.

Один и тот же формат списков используется и для направлений
(`directions.py`), и для формата работы (`commitment.py`), и для
универсальных стоп-слов (`filter_settings.py`), поэтому разбор вынесен
сюда.

Звёздочка означает «и любое окончание»: `"презентаци*"` найдёт презентацию,
презентации и презентаций. Слово без звёздочки должно совпасть целиком.
Поиск всегда начинается с начала слова, поэтому «моушн» не находится
в середине постороннего слова, а `"3d"` — внутри `3days`.
"""

import re


def compile_keyword(keyword):
    """Собирает шаблон поиска одного ключевого слова."""

    parts = [re.escape(part) for part in keyword.split("*")]
    pattern = r"\b" + r"\w*".join(parts)
    if not keyword.endswith("*"):
        pattern += r"\b"
    return re.compile(pattern, re.IGNORECASE)


def compile_keywords(keywords):
    """Возвращает пары «слово для показа — шаблон поиска».

    Шаблоны стоит собирать один раз при загрузке модуля, а не на каждую
    вакансию.
    """

    return tuple(
        (keyword.replace("*", ""), compile_keyword(keyword))
        for keyword in keywords
    )


def find_matches(text, patterns):
    """Возвращает слова из набора, найденные в тексте."""

    return [keyword for keyword, pattern in patterns if pattern.search(text)]


def has_match(text, patterns):
    """Есть ли в тексте хотя бы одно слово из набора."""

    return any(pattern.search(text) for _, pattern in patterns)
