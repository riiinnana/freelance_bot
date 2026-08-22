"""Хранение отклонённых вакансий для каждого пользователя бота."""

import sqlite3
from contextlib import closing
from pathlib import Path


class RejectionRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rejected_vacancies (
                    user_id INTEGER NOT NULL,
                    source_id TEXT NOT NULL,
                    rejected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, source_id)
                )
                """
            )

    def _connect(self):
        return sqlite3.connect(self.database_path, isolation_level=None)

    def reject(self, user_id, source_id):
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO rejected_vacancies (user_id, source_id)
                VALUES (?, ?)
                """,
                (user_id, source_id),
            )

    def is_rejected(self, user_id, source_id):
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM rejected_vacancies
                WHERE user_id = ? AND source_id = ?
                """,
                (user_id, source_id),
            ).fetchone()
        return row is not None
