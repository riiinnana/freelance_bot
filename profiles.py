"""Профиль пользователя: направления, порог бюджета и строгий режим."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from directions import DIRECTION_BY_KEY
from filter_settings import DEFAULT_MIN_BUDGET


# Новый пользователь начинает со строгого режима: показываем только то,
# что он выбрал сам.
DEFAULT_STRICT_MODE = True

MIN_ALLOWED_BUDGET = 0
MAX_ALLOWED_BUDGET = 10_000_000


@dataclass(frozen=True)
class UserProfile:
    """Настройки поиска одного пользователя.

    `direction_keys` хранится в порядке приоритета: чем раньше направление
    в списке, тем выше вакансия в выдаче.
    """

    user_id: int
    direction_keys: tuple
    min_budget: int
    strict_mode: bool

    @property
    def is_configured(self):
        """Профиль готов к поиску, если выбрано хотя бы одно направление."""

        return bool(self.direction_keys)


class ProfileRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id     INTEGER PRIMARY KEY,
                    min_budget  INTEGER NOT NULL,
                    strict_mode INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_directions (
                    user_id       INTEGER NOT NULL,
                    direction_key TEXT NOT NULL,
                    priority      INTEGER NOT NULL,
                    PRIMARY KEY (user_id, direction_key)
                )
                """
            )

    def _connect(self):
        return sqlite3.connect(self.database_path, isolation_level=None)

    def _ensure_profile(self, connection, user_id):
        connection.execute(
            """
            INSERT OR IGNORE INTO user_profiles (user_id, min_budget, strict_mode)
            VALUES (?, ?, ?)
            """,
            (user_id, DEFAULT_MIN_BUDGET, int(DEFAULT_STRICT_MODE)),
        )

    def get(self, user_id):
        """Возвращает профиль пользователя, создавая его при первом обращении."""

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)

            min_budget, strict_mode = connection.execute(
                "SELECT min_budget, strict_mode FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            rows = connection.execute(
                """
                SELECT direction_key FROM user_directions
                WHERE user_id = ?
                ORDER BY priority
                """,
                (user_id,),
            ).fetchall()

        # Направление могло исчезнуть из справочника после правки
        # `directions.py` — такие ключи молча пропускаем.
        keys = tuple(
            key for (key,) in rows if key in DIRECTION_BY_KEY
        )

        return UserProfile(
            user_id=user_id,
            direction_keys=keys,
            min_budget=min_budget,
            strict_mode=bool(strict_mode),
        )

    def toggle_direction(self, user_id, direction_key):
        """Включает или выключает направление. Возвращает новое состояние."""

        if direction_key not in DIRECTION_BY_KEY:
            raise ValueError(f"Неизвестное направление: {direction_key}")

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)

            is_selected = connection.execute(
                """
                SELECT 1 FROM user_directions
                WHERE user_id = ? AND direction_key = ?
                """,
                (user_id, direction_key),
            ).fetchone()

            if is_selected:
                connection.execute(
                    """
                    DELETE FROM user_directions
                    WHERE user_id = ? AND direction_key = ?
                    """,
                    (user_id, direction_key),
                )
                return False

            (next_priority,) = connection.execute(
                """
                SELECT COALESCE(MAX(priority), -1) + 1 FROM user_directions
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            connection.execute(
                """
                INSERT INTO user_directions (user_id, direction_key, priority)
                VALUES (?, ?, ?)
                """,
                (user_id, direction_key, next_priority),
            )
            return True

    def set_min_budget(self, user_id, amount):
        """Сохраняет персональную минимальную сумму за проект."""

        if not MIN_ALLOWED_BUDGET <= amount <= MAX_ALLOWED_BUDGET:
            raise ValueError("Сумма вне допустимого диапазона")

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)
            connection.execute(
                "UPDATE user_profiles SET min_budget = ? WHERE user_id = ?",
                (amount, user_id),
            )

    def set_strict_mode(self, user_id, enabled):
        """Включает или выключает строгий режим."""

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)
            connection.execute(
                "UPDATE user_profiles SET strict_mode = ? WHERE user_id = ?",
                (int(enabled), user_id),
            )
