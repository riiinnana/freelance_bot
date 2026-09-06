"""Хранилище собранных вакансий.

Раньше каждый показ заново обходил каналы, разбирал посты и выбрасывал
результат. Теперь публикации складываются в базу вместе с разбором:
`classify_vacancy` не зависит от пользователя, поэтому её достаточно
посчитать один раз при сборе.

Здесь же устраняются повторы. Одно объявление часто перепечатывают в
нескольких каналах, и `source_id` у копий разные — сравнивать нужно тексты.
Точного совпадения при этом мало: каждый канал дописывает свою подпись
(«Подписывайтесь», «Больше вакансий»), и текст перестаёт совпадать буквально.
Поэтому повтор ищется по доле общих слов.
"""

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from filter import CLASSIFICATION_KEYS, classify_vacancy


# Ссылки и упоминания в сравнении не участвуют: у копий они всегда разные.
LINK_PATTERN = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"(?<!\w)@[A-Za-z][A-Za-z0-9_]{4,31}")
NON_TEXT_PATTERN = re.compile(r"[^\w\s]", re.UNICODE)
SPACES_PATTERN = re.compile(r"\s+")

# Короткие слова («и», «для», «на») есть в любом тексте и только смазывают
# сравнение.
MIN_TOKEN_LENGTH = 3

# Служебная лексика вакансий. Эти слова встречаются почти в каждом
# объявлении и в подписи каждого канала, поэтому по ним нельзя отличить
# перепечатку от другой вакансии.
COMMON_WORDS = frozenset(
    """
    бюджет оплата стоимость руб рублей рубля цена гонорар
    нужен нужна нужно нужны требуется ищем ищу разыскивается
    вакансия вакансии работа заказ проект задача задачи
    дизайнер дизайнера дизайн дизайнеров
    писать пишите пиши напишите вопросам вопросы контакт связь
    отклик откликаться резюме портфолио примеры
    подписывайтесь подписаться канал канале канала чат чате
    больше каждый день свежие новые ещё еще
    удалённо удаленно удалёнка удаленка фриланс
    срочно опыт сроки срок готов готова обсудим детали
    """.split()
)


def _is_meaningful(word):
    return len(word) >= MIN_TOKEN_LENGTH and word not in COMMON_WORDS


# Доля слов короткого текста, найденных в длинном. Именно доля от короткого,
# а не от объединения: канал может дописать футер длиннее самой вакансии, и
# тогда сравнение по объединению разваливается.
DUPLICATE_SIMILARITY = 0.75

# Слишком короткие объявления по словам не сравниваются: у них мало
# содержательных слов, и случайное совпадение слишком вероятно.
MIN_TOKENS_FOR_SIMILARITY = 5


def normalize(text):
    """Приводит текст к виду, в котором его можно сравнивать."""

    normalized = text.lower()
    normalized = LINK_PATTERN.sub(" ", normalized)
    normalized = MENTION_PATTERN.sub(" ", normalized)
    normalized = NON_TEXT_PATTERN.sub(" ", normalized)
    return SPACES_PATTERN.sub(" ", normalized).strip()


def fingerprint(text):
    """Отпечаток текста для быстрого поиска буквальных совпадений."""

    return hashlib.blake2b(
        normalize(text).encode("utf-8"), digest_size=16
    ).hexdigest()


def content_tokens(text):
    """Набор содержательных слов текста, без служебной лексики вакансий."""

    return frozenset(
        word for word in normalize(text).split() if _is_meaningful(word)
    )


def similarity(first_tokens, second_tokens):
    """Какая доля слов более короткого текста нашлась в другом.

    От 0 (ничего общего) до 1 (короткий текст целиком содержится в длинном).
    """

    if not first_tokens or not second_tokens:
        return 0.0

    shortest = min(len(first_tokens), len(second_tokens))
    return len(first_tokens & second_tokens) / shortest


def is_reprint(tokens, known_token_sets):
    """Похожа ли публикация на одну из уже известных."""

    if len(tokens) < MIN_TOKENS_FOR_SIMILARITY:
        return False

    return any(
        len(known) >= MIN_TOKENS_FOR_SIMILARITY
        and similarity(tokens, known) >= DUPLICATE_SIMILARITY
        for known in known_token_sets
    )


@dataclass(frozen=True)
class StoredVacancy:
    """Вакансия из базы вместе с готовым разбором."""

    source_id: str
    source: str
    title: str
    description: str
    url: str
    published_at: str | None
    classification: dict


class VacancyRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vacancies (
                    source_id      TEXT PRIMARY KEY,
                    source         TEXT NOT NULL,
                    title          TEXT NOT NULL,
                    description    TEXT NOT NULL,
                    url            TEXT NOT NULL,
                    published_at   TEXT,
                    fingerprint    TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    collected_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_vacancies_fingerprint "
                "ON vacancies (fingerprint)"
            )

    def _connect(self):
        return sqlite3.connect(self.database_path, isolation_level=None)

    def save_posts(self, posts):
        """Сохраняет новые публикации, пропуская уже известные.

        Возвращает пару «сколько добавлено, сколько отсеяно как повтор».
        Повтором считается и та же публикация, и перепечатка того же текста
        в другом канале.
        """

        added = 0
        duplicates = 0

        with closing(self._connect()) as connection:
            known = connection.execute(
                "SELECT fingerprint, description FROM vacancies"
            ).fetchall()

            known_fingerprints = {row[0] for row in known}
            known_token_sets = [content_tokens(row[1]) for row in known]

            for post in posts:
                text_fingerprint = fingerprint(post.description)
                tokens = content_tokens(post.description)

                if text_fingerprint in known_fingerprints or is_reprint(
                    tokens, known_token_sets
                ):
                    duplicates += 1
                    continue

                connection.execute(
                    """
                    INSERT OR IGNORE INTO vacancies (
                        source_id, source, title, description, url,
                        published_at, fingerprint, classification
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        post.source_id,
                        post.source,
                        post.title,
                        post.description,
                        post.url,
                        post.published_at,
                        text_fingerprint,
                        json.dumps(
                            classify_vacancy(post.description),
                            ensure_ascii=False,
                        ),
                    ),
                )
                known_fingerprints.add(text_fingerprint)
                known_token_sets.append(tokens)
                added += 1

        return added, duplicates

    def all(self):
        """Возвращает все сохранённые вакансии, свежие первыми."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT source_id, source, title, description, url,
                       published_at, classification
                FROM vacancies
                ORDER BY collected_at DESC, source_id DESC
                """
            ).fetchall()

        return [
            StoredVacancy(
                source_id=row[0],
                source=row[1],
                title=row[2],
                description=row[3],
                url=row[4],
                published_at=row[5],
                classification=json.loads(row[6]),
            )
            for row in rows
        ]

    def count(self):
        with closing(self._connect()) as connection:
            return connection.execute(
                "SELECT COUNT(*) FROM vacancies"
            ).fetchone()[0]

    def reclassify_outdated(self):
        """Пересчитывает разбор там, где он собран прошлой версией.

        Разбор лежит в базе готовым, поэтому новое поле (например, формат
        работы) к старым записям само не появится.
        """

        outdated = []
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT source_id, description, classification FROM vacancies"
            ).fetchall()

            for source_id, description, classification in rows:
                if CLASSIFICATION_KEYS <= set(json.loads(classification)):
                    continue
                outdated.append((source_id, description))

            for source_id, description in outdated:
                connection.execute(
                    "UPDATE vacancies SET classification = ? WHERE source_id = ?",
                    (
                        json.dumps(
                            classify_vacancy(description), ensure_ascii=False
                        ),
                        source_id,
                    ),
                )

        return len(outdated)

    def reclassify_all(self):
        """Пересчитывает разбор по сохранённым текстам.

        Нужно после правки `directions.py` или `filter_settings.py`: разбор
        лежит в базе готовым, и без пересчёта новые ключевые слова к старым
        вакансиям не применятся.
        """

        updated = 0
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT source_id, description FROM vacancies"
            ).fetchall()

            for source_id, description in rows:
                connection.execute(
                    "UPDATE vacancies SET classification = ? WHERE source_id = ?",
                    (
                        json.dumps(
                            classify_vacancy(description), ensure_ascii=False
                        ),
                        source_id,
                    ),
                )
                updated += 1

        return updated
