"""Профиль пользователя: направления, порог бюджета и строгий режим."""

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from storage import connect
from commitment import ANY, COMMITMENTS
from directions import DIRECTION_BY_KEY
from config import DEFAULT_PORTFOLIO_URL
from filter_settings import DEFAULT_MIN_BUDGET


# Новый пользователь начинает со строгого режима: показываем только то,
# что он выбрал сам.
DEFAULT_STRICT_MODE = True

MIN_ALLOWED_BUDGET = 0
MAX_ALLOWED_BUDGET = 10_000_000

# Ноль означает «потолок не задан»: верхней границы нет.
NO_MAX_BUDGET = 0

# По умолчанию формат работы неважен.
DEFAULT_COMMITMENT = ANY


def is_valid_portfolio_url(url):
    """Проверяет, что ссылка похожа на адрес, а не на случайный текст."""

    url = url.strip()
    return (
        url.startswith(("http://", "https://"))
        and " " not in url
        and len(url) > len("https://")
    )


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
    portfolio_url: str
    max_budget: int = NO_MAX_BUDGET
    commitment: str = DEFAULT_COMMITMENT

    @property
    def is_configured(self):
        """Профиль готов к поиску, если выбрано хотя бы одно направление."""

        return bool(self.direction_keys)

    @property
    def has_portfolio(self):
        return bool(self.portfolio_url)

    @property
    def has_max_budget(self):
        return self.max_budget > NO_MAX_BUDGET


class ProfileRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id       INTEGER PRIMARY KEY,
                    min_budget    INTEGER NOT NULL,
                    strict_mode   INTEGER NOT NULL DEFAULT 1,
                    portfolio_url TEXT NOT NULL DEFAULT '',
                    max_budget    INTEGER NOT NULL DEFAULT 0,
                    commitment    TEXT NOT NULL DEFAULT 'any'
                )
                """
            )
            self._add_missing_columns(connection)
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
        return connect(self.database_path)

    @staticmethod
    def _add_missing_columns(connection):
        """Дописывает колонки, появившиеся позже создания базы.

        Без этого база, созданная прошлой версией бота, теряла бы профили
        при обновлении.
        """

        existing = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(user_profiles)"
            ).fetchall()
        }

        if "portfolio_url" not in existing:
            connection.execute(
                "ALTER TABLE user_profiles "
                "ADD COLUMN portfolio_url TEXT NOT NULL DEFAULT ''"
            )

        if "max_budget" not in existing:
            connection.execute(
                "ALTER TABLE user_profiles "
                "ADD COLUMN max_budget INTEGER NOT NULL DEFAULT 0"
            )

        if "commitment" not in existing:
            connection.execute(
                "ALTER TABLE user_profiles "
                "ADD COLUMN commitment TEXT NOT NULL DEFAULT 'any'"
            )

    def _ensure_profile(self, connection, user_id):
        connection.execute(
            """
            INSERT OR IGNORE INTO user_profiles
                (user_id, min_budget, strict_mode, portfolio_url)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                DEFAULT_MIN_BUDGET,
                int(DEFAULT_STRICT_MODE),
                DEFAULT_PORTFOLIO_URL,
            ),
        )

    def get(self, user_id):
        """Возвращает профиль пользователя, создавая его при первом обращении."""

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)

            (
                min_budget,
                strict_mode,
                portfolio_url,
                max_budget,
                commitment,
            ) = connection.execute(
                "SELECT min_budget, strict_mode, portfolio_url, "
                "max_budget, commitment "
                "FROM user_profiles WHERE user_id = ?",
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
            portfolio_url=portfolio_url or "",
            max_budget=max_budget,
            commitment=commitment,
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

    def set_portfolio_url(self, user_id, url):
        """Сохраняет ссылку на портфолио пользователя."""

        url = url.strip()
        if not is_valid_portfolio_url(url):
            raise ValueError("Ссылка должна начинаться с http:// или https://")

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)
            connection.execute(
                "UPDATE user_profiles SET portfolio_url = ? WHERE user_id = ?",
                (url, user_id),
            )

    def set_max_budget(self, user_id, amount):
        """Сохраняет потолок суммы. Ноль снимает ограничение."""

        if not MIN_ALLOWED_BUDGET <= amount <= MAX_ALLOWED_BUDGET:
            raise ValueError("Сумма вне допустимого диапазона")

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)
            connection.execute(
                "UPDATE user_profiles SET max_budget = ? WHERE user_id = ?",
                (amount, user_id),
            )

    def set_commitment(self, user_id, commitment):
        """Сохраняет предпочтение по формату работы."""

        if commitment != ANY and commitment not in COMMITMENTS:
            raise ValueError(f"Неизвестный формат работы: {commitment}")

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)
            connection.execute(
                "UPDATE user_profiles SET commitment = ? WHERE user_id = ?",
                (commitment, user_id),
            )

    def set_strict_mode(self, user_id, enabled):
        """Включает или выключает строгий режим."""

        with closing(self._connect()) as connection:
            self._ensure_profile(connection, user_id)
            connection.execute(
                "UPDATE user_profiles SET strict_mode = ? WHERE user_id = ?",
                (int(enabled), user_id),
            )
