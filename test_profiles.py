import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from filter_settings import DEFAULT_MIN_BUDGET
from profiles import ProfileRepository


class ProfileRepositoryTests(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.repository = ProfileRepository(
            Path(self._directory.name) / "profiles.db"
        )

    def test_new_user_gets_defaults_and_no_directions(self):
        profile = self.repository.get(100)

        self.assertEqual(profile.direction_keys, ())
        self.assertEqual(profile.min_budget, DEFAULT_MIN_BUDGET)
        self.assertTrue(profile.strict_mode)
        self.assertFalse(profile.is_configured)

    def test_directions_are_kept_in_order_of_choice(self):
        for key in ("banners", "presentations", "product_cards"):
            self.repository.toggle_direction(100, key)

        profile = self.repository.get(100)

        self.assertEqual(
            profile.direction_keys, ("banners", "presentations", "product_cards")
        )
        self.assertTrue(profile.is_configured)

    def test_toggle_switches_direction_off(self):
        self.assertTrue(self.repository.toggle_direction(100, "banners"))
        self.assertFalse(self.repository.toggle_direction(100, "banners"))

        self.assertEqual(self.repository.get(100).direction_keys, ())

    def test_profiles_of_different_users_do_not_mix(self):
        self.repository.toggle_direction(100, "presentations")
        self.repository.toggle_direction(101, "three_d")
        self.repository.set_min_budget(101, 30000)

        self.assertEqual(self.repository.get(100).direction_keys, ("presentations",))
        self.assertEqual(self.repository.get(100).min_budget, DEFAULT_MIN_BUDGET)
        self.assertEqual(self.repository.get(101).direction_keys, ("three_d",))
        self.assertEqual(self.repository.get(101).min_budget, 30000)

    def test_strict_mode_can_be_switched_off(self):
        self.repository.set_strict_mode(100, False)

        self.assertFalse(self.repository.get(100).strict_mode)

    def test_unknown_direction_is_rejected(self):
        with self.assertRaises(ValueError):
            self.repository.toggle_direction(100, "нет-такого-направления")

    def test_budget_outside_allowed_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self.repository.set_min_budget(100, -1)

    def test_portfolio_url_is_saved_and_returned(self):
        self.repository.set_portfolio_url(100, "https://behance.net/me")

        profile = self.repository.get(100)

        self.assertEqual(profile.portfolio_url, "https://behance.net/me")
        self.assertTrue(profile.has_portfolio)

    def test_new_profile_has_no_portfolio(self):
        self.assertFalse(self.repository.get(100).has_portfolio)

    def test_text_that_is_not_a_link_is_rejected(self):
        for value in ("мой сайт", "behance.net/me", "https://два слова"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.repository.set_portfolio_url(100, value)


class ProfileMigrationTests(unittest.TestCase):
    """База, созданная прошлой версией бота, не должна терять настройки."""

    def test_old_database_gains_the_portfolio_column(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "old.db"

            # Схема до появления портфолио. `with` у sqlite3 закрывает
            # только транзакцию, поэтому соединение закрываем явно —
            # иначе на Windows файл останется заблокированным.
            with closing(
                sqlite3.connect(database_path, isolation_level=None)
            ) as old:
                old.execute(
                    """
                    CREATE TABLE user_profiles (
                        user_id     INTEGER PRIMARY KEY,
                        min_budget  INTEGER NOT NULL,
                        strict_mode INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )
                old.execute(
                    """
                    CREATE TABLE user_directions (
                        user_id       INTEGER NOT NULL,
                        direction_key TEXT NOT NULL,
                        priority      INTEGER NOT NULL,
                        PRIMARY KEY (user_id, direction_key)
                    )
                    """
                )
                old.execute(
                    "INSERT INTO user_profiles VALUES (100, 7000, 0)"
                )
                old.execute(
                    "INSERT INTO user_directions VALUES (100, 'banners', 0)"
                )

            repository = ProfileRepository(database_path)
            profile = repository.get(100)

            # Прежние настройки на месте, портфолио просто пустое.
            self.assertEqual(profile.min_budget, 7000)
            self.assertFalse(profile.strict_mode)
            self.assertEqual(profile.direction_keys, ("banners",))
            self.assertEqual(profile.portfolio_url, "")


if __name__ == "__main__":
    unittest.main()
