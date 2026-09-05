import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
