"""Справочник направлений дизайна.

Ключ направления (`key`) попадает в базу данных и в `callback_data` кнопок,
поэтому менять его у уже существующего направления нельзя. Название и список
ключевых слов можно свободно редактировать.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Direction:
    """Направление работ и слова, по которым оно определяется в тексте."""

    key: str
    name: str
    keywords: tuple[str, ...]


DIRECTIONS = (
    Direction(
        key="presentations",
        name="Презентации",
        keywords=(
            "презентаци", "слайд", "коммерческое предложение",
            "коммерческого предложения", "pitch deck", "pitchdeck",
        ),
    ),
    Direction(
        key="product_cards",
        name="Карточки товаров",
        keywords=(
            "карточк", "wildberries", "wb", "ozon", "маркетплейс",
            "инфографика товара",
        ),
    ),
    Direction(
        key="posters",
        name="Афиши и плакаты",
        keywords=("афиш", "плакат", "постер"),
    ),
    Direction(
        key="covers",
        name="Обложки",
        keywords=("обложк", "cover"),
    ),
    Direction(
        key="publications",
        name="Дизайн публикаций",
        keywords=(
            "публикаци", "дизайн пост", "оформление пост", "визуал пост",
        ),
    ),
    Direction(
        key="banners",
        name="Баннеры",
        keywords=("баннер",),
    ),
    Direction(
        key="ad_creatives",
        name="Рекламные креативы",
        keywords=(
            "креатив", "рекламный макет", "рекламные макеты",
            "рекламный дизайн",
        ),
    ),
    Direction(
        key="social_media",
        name="Оформление соцсетей",
        keywords=(
            "оформление соцсетей", "визуал соцсетей", "дизайн соцсетей",
        ),
    ),
    Direction(
        key="infographics",
        name="Инфографика",
        keywords=("инфографик",),
    ),
    Direction(
        key="three_d",
        name="3D-визуализация",
        keywords=(
            "3d", "3д", "3d-дизайн", "3d визуализатор", "3d-визуализатор",
            "визуализация интерьера", "рендер", "blender", "maya",
            "unreal engine", "cinema 4d",
        ),
    ),
    Direction(
        key="motion",
        name="Анимация и моушн",
        keywords=(
            "анимаци", "аниматор", "motion", "моушн", "моушен",
            "2d animator", "after effects",
        ),
    ),
    Direction(
        key="video_editing",
        name="Видеомонтаж",
        keywords=(
            "видеомонтаж", "монтаж видео", "видеоредактор", "premiere pro",
            "davinci",
        ),
    ),
)


DIRECTION_BY_KEY = {direction.key: direction for direction in DIRECTIONS}


def direction_name(key):
    """Возвращает название направления по ключу."""

    direction = DIRECTION_BY_KEY.get(key)
    return direction.name if direction else key


def direction_names(keys):
    """Возвращает названия направлений в порядке переданных ключей."""

    return [direction_name(key) for key in keys]
