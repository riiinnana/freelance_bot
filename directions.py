"""Справочник направлений дизайна, сгруппированный по блокам.

Ключ направления (`key`) попадает в базу данных и в `callback_data` кнопок,
поэтому менять его у уже существующего направления нельзя. Название и список
ключевых слов можно свободно редактировать.

Ключевое слово со звёздочкой на конце означает «и любое окончание»:
`"презентаци*"` найдёт презентацию, презентации и презентаций. Без звёздочки
слово ищется целиком: `"3d"` найдёт «3d» и «3d-дизайн», но не «3days».
Поиск в любом случае начинается с начала слова, поэтому «моушн» больше не
находится в середине постороннего слова.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Group:
    """Блок направлений: крупная сфера, из которой пользователь выбирает."""

    key: str
    name: str


@dataclass(frozen=True)
class Direction:
    """Направление работ и слова, по которым оно определяется в тексте."""

    key: str
    name: str
    group: str
    keywords: tuple[str, ...]


GROUPS = (
    Group(key="graphics_2d", name="2D-графика"),
    Group(key="three_d_block", name="3D"),
    Group(key="motion_block", name="Анимация и видео"),
)


DIRECTIONS = (
    # --- 2D-графика ---
    Direction(
        key="presentations",
        name="Презентации",
        group="graphics_2d",
        keywords=(
            "презентаци*", "слайд*", "коммерческое предложение",
            "коммерческого предложения", "pitch deck", "pitchdeck",
        ),
    ),
    Direction(
        key="product_cards",
        name="Карточки товаров",
        group="graphics_2d",
        keywords=(
            "карточк*", "wildberries", "wb", "ozon", "маркетплейс*",
            "инфографика товара",
        ),
    ),
    Direction(
        key="posters",
        name="Афиши и плакаты",
        group="graphics_2d",
        keywords=("афиш*", "плакат*", "постер*"),
    ),
    Direction(
        key="covers",
        name="Обложки",
        group="graphics_2d",
        keywords=("обложк*", "cover"),
    ),
    Direction(
        key="publications",
        name="Дизайн публикаций",
        group="graphics_2d",
        keywords=(
            "публикаци*", "дизайн пост*", "оформление пост*", "визуал пост*",
        ),
    ),
    Direction(
        key="banners",
        name="Баннеры",
        group="graphics_2d",
        keywords=("баннер*",),
    ),
    Direction(
        key="ad_creatives",
        name="Рекламные креативы",
        group="graphics_2d",
        keywords=(
            "креатив*", "рекламный макет*", "рекламные макет*",
            "рекламный дизайн",
        ),
    ),
    Direction(
        key="social_media",
        name="Оформление соцсетей",
        group="graphics_2d",
        keywords=(
            "оформление соцсетей", "визуал соцсетей", "дизайн соцсетей",
            "оформление социальных сетей",
        ),
    ),
    Direction(
        key="illustration",
        name="Иллюстрация",
        group="graphics_2d",
        keywords=(
            "иллюстрац*", "иллюстратор*", "отрисовк*", "отрисовать",
            "нарисовать", "скетч*", "рисунок", "рисунк*", "лайнарт",
            "растровая графика", "векторн* иллюстрац*",
        ),
    ),
    Direction(
        key="infographics",
        name="Инфографика",
        group="graphics_2d",
        keywords=("инфографик*",),
    ),

    # --- 3D ---
    # Сферы взяты с фриланс-рынка, а не придуманы: предметная и
    # архитектурная визуализация, персонажи, hard surface, игровая
    # графика и модели под 3D-печать.
    Direction(
        key="three_d",
        name="3D-графика (общее)",
        group="three_d_block",
        keywords=(
            "3d", "3д", "3d-дизайн*", "3d-график*", "3d-модел*",
            "3d-моделлер*", "3d-визуализ*", "3д-визуализ*", "визуализатор*",
            "рендер*", "blender", "maya", "cinema 4d", "3ds max", "zbrush",
        ),
    ),
    Direction(
        key="three_d_product",
        name="Предметная визуализация",
        group="three_d_block",
        keywords=(
            "предметн* визуализаци*", "предметн* рендер*",
            "визуализаци* товар*", "визуализаци* мебел*", "3d товар*",
            "3d для маркетплейс*", "3d-карточк*", "3d карточк*",
        ),
    ),
    Direction(
        key="three_d_archviz",
        name="Архитектура и интерьеры",
        group="three_d_block",
        keywords=(
            "интерьер*", "экстерьер*", "архитектурн* визуализаци*",
            "архвиз", "archviz", "планировк*", "ландшафт*",
        ),
    ),
    Direction(
        key="three_d_character",
        name="Персонажи",
        group="three_d_block",
        # Голое "персонаж*" ловило вакансии иллюстраторов, поэтому слово
        # берётся только в связке с 3D-контекстом.
        keywords=(
            "3d персонаж*", "3d-персонаж*", "моделирование персонаж*",
            "модел* персонаж*", "художник* по персонаж*",
            "персонаж* для игр*", "character design", "скульптинг",
        ),
    ),
    Direction(
        key="three_d_hard_surface",
        name="Техника и механизмы",
        group="three_d_block",
        keywords=(
            "hard surface", "хард сюрфейс", "моделирование техники",
            "3d транспорт*", "промышленн* модел*",
        ),
    ),
    Direction(
        key="three_d_game",
        name="Игровая графика",
        group="three_d_block",
        keywords=(
            "геймдев", "gamedev", "игров* график*", "environment art",
            "пропс*", "low poly", "lowpoly", "лоуполи", "гейм-арт",
            "unreal engine", "unity",
        ),
    ),
    Direction(
        key="three_d_print",
        name="Модели для 3D-печати",
        group="three_d_block",
        keywords=(
            "3d-печат*", "3d печат*", "печать на 3d", "модел* под печать",
        ),
    ),

    # --- Анимация и видео ---
    Direction(
        key="motion",
        name="Анимация и моушн",
        group="motion_block",
        keywords=(
            "анимаци*", "аниматор*", "анимированн*", "motion", "моушн*",
            "моушен*", "after effects",
        ),
    ),
    Direction(
        key="logo_animation",
        name="Анимация логотипа",
        group="motion_block",
        keywords=(
            "анимация логотипа", "анимировать логотип", "лого анимаци*",
        ),
    ),
    Direction(
        key="three_d_animation",
        name="3D-анимация",
        group="motion_block",
        keywords=(
            "3d анимаци*", "3d-анимаци*", "анимация 3d", "трёхмерн* анимаци*",
            "трехмерн* анимаци*", "анимация модел*",
        ),
    ),
    Direction(
        key="character_animation",
        name="Анимация персонажей",
        group="motion_block",
        keywords=(
            "анимация персонаж*", "анимаци* персонаж*", "оживить персонаж*",
            "анимировать персонаж*", "аниматор* персонаж*",
            "character animation",
        ),
    ),
    Direction(
        key="rigging",
        name="Риггинг",
        group="motion_block",
        keywords=(
            "риггинг", "rigging", "риг персонаж*", "настройка скелета",
            "скелет персонаж*", "скиннинг", "skinning",
        ),
    ),
    Direction(
        key="video_editing",
        name="Видеомонтаж",
        group="motion_block",
        keywords=(
            "видеомонтаж*", "монтаж видео", "видеоредактор*", "монтажёр*",
            "монтажер*", "premiere pro", "davinci",
        ),
    ),
    Direction(
        key="reels",
        name="Рилсы и вертикальные видео",
        group="motion_block",
        keywords=(
            "рилс*", "reels", "вертикальн* видео", "shorts", "тикток",
            "tiktok",
        ),
    ),
)


DIRECTION_BY_KEY = {direction.key: direction for direction in DIRECTIONS}
GROUP_BY_KEY = {group.key: group for group in GROUPS}


def directions_in_group(group_key):
    """Возвращает направления одного блока в порядке справочника."""

    return [
        direction for direction in DIRECTIONS if direction.group == group_key
    ]


def direction_name(key):
    """Возвращает название направления по ключу."""

    direction = DIRECTION_BY_KEY.get(key)
    return direction.name if direction else key


def direction_names(keys):
    """Возвращает названия направлений в порядке переданных ключей."""

    return [direction_name(key) for key in keys]


def group_name(key):
    """Возвращает название блока по ключу."""

    group = GROUP_BY_KEY.get(key)
    return group.name if group else key
