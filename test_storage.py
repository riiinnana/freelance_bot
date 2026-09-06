import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from profiles import ProfileRepository
from storage import BUSY_TIMEOUT_SECONDS, connect


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.database_path = Path(self._directory.name) / "bot.db"

    def test_database_is_opened_in_wal_mode(self):
        # Без WAL пишущий запрос блокирует читающих, и они получают
        # "database is locked".
        with closing(connect(self.database_path)) as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual(mode.lower(), "wal")

    def test_busy_timeout_is_set(self):
        with closing(connect(self.database_path)) as connection:
            timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertEqual(timeout, BUSY_TIMEOUT_SECONDS * 1000)

    def test_several_writers_do_not_collide(self):
        repository = ProfileRepository(self.database_path)
        failures = []

        def hammer(user_id):
            try:
                for step in range(20):
                    repository.set_min_budget(user_id, 1000 + step)
                    repository.get(user_id)
            except Exception as error:  # noqa: BLE001 - в тесте важен сам факт
                failures.append(repr(error))

        threads = [
            threading.Thread(target=hammer, args=(user_id,))
            for user_id in range(6)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(failures, [])
        self.assertEqual(repository.get(3).min_budget, 1019)


if __name__ == "__main__":
    unittest.main()
