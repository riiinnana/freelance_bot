"""Разбивка постов-подборок на отдельные вакансии.

Часть каналов публикует одним постом десяток вакансий подряд:

    ✍️ Требуются творческие специалисты:

    1. #Дизайнер_соцсетей
    Создание визуального контента по ТЗ и брендбуку компании.
    📝 @muzykalarisa

    2. #Графдизайнер
    Учебный центр ищет дизайнера на постоянку.
    📝 @kamola_phoenix

До разбивки такой пост считался одной вакансией: показывался только первый
пункт, а бюджет и контакт брались из всего текста разом — то есть от
случайного пункта. Здесь пост режется по строкам-заголовкам, и дальше
каждый пункт живёт своей жизнью: со своим разбором, своей суммой и своим
контактом заказчика.

Режем на сборе, а не при показе: разбор вакансии считается один раз и
складывается в базу, и делить его потом было бы уже поздно.
"""

from dataclasses import replace

from vacancy_summary import build_title, is_contact_line, is_item_start


# Один заголовок — это обычный пост, а не подборка.
MIN_ITEMS = 2

# Отделяет номер пункта от идентификатора исходной публикации.
ITEM_SEPARATOR = "#"

# Пункт короче этого — обрывок вроде «Найден!», а не вакансия.
MIN_ITEM_LENGTH = 40


def _item_bounds(lines):
    """Номера строк, с которых начинаются пункты подборки."""

    return [index for index, line in enumerate(lines) if is_item_start(line)]


def _cut_item(lines):
    """Обрезает пункт по контакту заказчика.

    Контакт стоит последней строкой пункта, поэтому всё после него — уже
    не про эту вакансию. Для последнего пункта так отсекается и подпись
    канала: «Коллеги, плз, поставьте ваш царский лайк».
    """

    for index, line in enumerate(lines):
        if index and is_contact_line(line):
            return lines[: index + 1]
    return lines


def split_text(text):
    """Режет текст подборки на куски. Не подборка — пустой список."""

    lines = text.splitlines()
    bounds = _item_bounds(lines)

    if len(bounds) < MIN_ITEMS:
        return []

    items = []
    for position, start in enumerate(bounds):
        end = bounds[position + 1] if position + 1 < len(bounds) else len(lines)
        item = "\n".join(_cut_item(lines[start:end])).strip()
        if len(item) >= MIN_ITEM_LENGTH:
            items.append(item)

    return items if len(items) >= MIN_ITEMS else []


def split_post(post):
    """Разбивает публикацию на вакансии. Обычный пост возвращается как есть.

    Ссылка у всех пунктов общая — она ведёт на исходную публикацию,
    отдельных ссылок на пункты в Telegram не существует.
    """

    items = split_text(post.description)
    if not items:
        return [post]

    return [
        replace(
            post,
            source_id=f"{post.source_id}{ITEM_SEPARATOR}{number}",
            title=build_title(item, post.title),
            description=item,
        )
        for number, item in enumerate(items, start=1)
    ]


def split_all(posts):
    """Разворачивает список публикаций, разбивая подборки."""

    expanded = []
    for post in posts:
        expanded.extend(split_post(post))
    return expanded
