import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from vacancy_actions import (
    HIDDEN_ACTIONS,
    REJECTED,
    RESPONDED,
    SKIPPED,
    VacancyActionRepository,
)


class VacancyActionRepositoryTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = VacancyActionRepository(
            Path(self._directory.name) / "actions.db"
        )

    def test_action_is_saved_per_user(self):
        self.repository.record(100, "designer_work/123", REJECTED)

        self.assertEqual(
            self.repository.action_for(100, "designer_work/123"), REJECTED
        )
        self.assertIsNone(self.repository.action_for(101, "designer_work/123"))

    def test_untouched_vacancy_has_no_action(self):
        self.assertIsNone(self.repository.action_for(100, "designer_work/123"))

    def test_response_and_rejection_hide_the_vacancy_but_skip_does_not(self):
        self.assertIn(RESPONDED, HIDDEN_ACTIONS)
        self.assertIn(REJECTED, HIDDEN_ACTIONS)
        self.assertNotIn(SKIPPED, HIDDEN_ACTIONS)

    def test_later_action_replaces_the_earlier_one(self):
        self.repository.record(100, "designer_work/123", SKIPPED)
        self.repository.record(100, "designer_work/123", RESPONDED)

        self.assertEqual(
            self.repository.action_for(100, "designer_work/123"), RESPONDED
        )

    def test_all_actions_are_returned_in_one_call(self):
        self.repository.record(100, "a/1", RESPONDED)
        self.repository.record(100, "a/2", SKIPPED)
        self.repository.record(101, "a/3", REJECTED)

        self.assertEqual(
            self.repository.actions_for_user(100),
            {"a/1": RESPONDED, "a/2": SKIPPED},
        )

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            self.repository.record(100, "a/1", "непонятное действие")


class OldRejectionImportTests(unittest.TestCase):
    """Отказы, накопленные прошлой версией бота, не должны пропасть."""

    def test_old_rejections_become_rejected_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "old.db"

            with closing(
                sqlite3.connect(database_path, isolation_level=None)
            ) as old:
                old.execute(
                    """
                    CREATE TABLE rejected_vacancies (
                        user_id INTEGER NOT NULL,
                        source_id TEXT NOT NULL,
                        rejected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, source_id)
                    )
                    """
                )
                old.execute(
                    "INSERT INTO rejected_vacancies (user_id, source_id, rejected_at) "
                    "VALUES (100, 'designer_work/123', '2026-09-01 10:00:00')"
                )

            repository = VacancyActionRepository(database_path)

            self.assertEqual(
                repository.action_for(100, "designer_work/123"), REJECTED
            )

    def test_import_does_not_overwrite_a_newer_action(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "old.db"

            with closing(
                sqlite3.connect(database_path, isolation_level=None)
            ) as old:
                old.execute(
                    """
                    CREATE TABLE rejected_vacancies (
                        user_id INTEGER NOT NULL,
                        source_id TEXT NOT NULL,
                        rejected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, source_id)
                    )
                    """
                )
                old.execute(
                    "INSERT INTO rejected_vacancies (user_id, source_id) "
                    "VALUES (100, 'designer_work/123')"
                )

            repository = VacancyActionRepository(database_path)
            repository.record(100, "designer_work/123", RESPONDED)

            # Повторное открытие снова запускает перенос.
            reopened = VacancyActionRepository(database_path)

            self.assertEqual(
                reopened.action_for(100, "designer_work/123"), RESPONDED
            )


if __name__ == "__main__":
    unittest.main()
