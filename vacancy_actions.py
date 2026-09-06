"""Что пользователь сделал с показанной вакансией.

Раньше состояние было одно — «отклонена», и кнопка отказа заодно служила
кнопкой «листать дальше». Из-за этого отклики попадали в базу как отказы,
и отличить одно от другого было нельзя.

Теперь состояний три:

* `RESPONDED` — написала заказчику. Вакансия больше не показывается.
* `REJECTED` — не подходит. Тоже больше не показывается.
* `SKIPPED` — пропущена. Уходит в конец очереди и вернётся, когда
  свежие вакансии закончатся.
"""

from contextlib import closing
from pathlib import Path

from storage import connect


RESPONDED = "responded"
SKIPPED = "skipped"
REJECTED = "rejected"

ACTIONS = (RESPONDED, SKIPPED, REJECTED)

# Состояния, после которых вакансия не показывается никогда.
HIDDEN_ACTIONS = frozenset({RESPONDED, REJECTED})


class VacancyActionRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vacancy_actions (
                    user_id    INTEGER NOT NULL,
                    source_id  TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, source_id)
                )
                """
            )
            self._import_old_rejections(connection)

    def _connect(self):
        return connect(self.database_path)

    @staticmethod
    def _import_old_rejections(connection):
        """Переносит отказы из таблицы прошлой версии бота.

        Старая таблица не удаляется: если что-то пойдёт не так, данные
        останутся на месте.
        """

        exists = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'rejected_vacancies'"
        ).fetchone()

        if not exists:
            return

        connection.execute(
            """
            INSERT OR IGNORE INTO vacancy_actions
                (user_id, source_id, action, created_at)
            SELECT user_id, source_id, ?, rejected_at FROM rejected_vacancies
            """,
            (REJECTED,),
        )

    def record(self, user_id, source_id, action):
        """Запоминает действие. Более позднее действие заменяет прежнее."""

        if action not in ACTIONS:
            raise ValueError(f"Неизвестное действие: {action}")

        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO vacancy_actions (user_id, source_id, action)
                VALUES (?, ?, ?)
                ON CONFLICT (user_id, source_id) DO UPDATE
                SET action = excluded.action,
                    created_at = CURRENT_TIMESTAMP
                """,
                (user_id, source_id, action),
            )

    def action_for(self, user_id, source_id):
        """Возвращает действие по вакансии или None, если его не было."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT action FROM vacancy_actions
                WHERE user_id = ? AND source_id = ?
                """,
                (user_id, source_id),
            ).fetchone()

        return row[0] if row else None

    def actions_for_user(self, user_id):
        """Возвращает все действия пользователя одним запросом.

        Выдача перебирает сотни публикаций, и ходить в базу за каждой —
        лишние запросы.
        """

        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT source_id, action FROM vacancy_actions WHERE user_id = ?",
                (user_id,),
            ).fetchall()

        return {source_id: action for source_id, action in rows}
