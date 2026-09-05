import unittest

from filter import analyze_vacancy, classify_vacancy, evaluate_for_user, extract_budget
from profiles import UserProfile


def make_profile(direction_keys, min_budget=1500, strict_mode=True):
    """Профиль пользователя для тестов, без обращения к базе."""

    return UserProfile(
        user_id=1,
        direction_keys=tuple(direction_keys),
        min_budget=min_budget,
        strict_mode=strict_mode,
    )


DESIGNER = make_profile(["presentations", "banners", "covers", "product_cards"])


class BudgetExtractionTests(unittest.TestCase):
    def test_fixed_project_budget(self):
        budget = extract_budget("Нужна презентация. Бюджет: 5 000 ₽.")

        self.assertEqual(budget["payment_type"], "fixed")
        self.assertEqual(budget["estimated_project_total"], 5000)

    def test_budget_range(self):
        budget = extract_budget("Нужен дизайн баннеров, бюджет 3 000–5 000 рублей.")

        self.assertEqual(budget["payment_type"], "range")
        self.assertEqual(budget["min_amount"], 3000)
        self.assertEqual(budget["max_amount"], 5000)

    def test_hourly_rate_with_hours_calculates_project_total(self):
        budget = extract_budget("Презентация: 700 ₽/час, работа на 8 часов.")

        self.assertEqual(budget["payment_type"], "hourly")
        self.assertEqual(budget["hourly_rate"], 700)
        self.assertEqual(budget["hours"], 8)
        self.assertEqual(budget["estimated_project_total"], 5600)

    def test_hourly_rate_without_hours_has_no_project_total(self):
        budget = extract_budget("Нужны слайды, оплата 700 ₽ в час.")

        self.assertEqual(budget["payment_type"], "hourly")
        self.assertIsNone(budget["estimated_project_total"])


class ClassificationTests(unittest.TestCase):
    """Разбор вакансии не должен зависеть от пользователя."""

    def test_finds_all_directions_regardless_of_profile(self):
        classification = classify_vacancy(
            "Нужен 3D-рендер интерьера и презентация проекта. Бюджет 30 000 ₽."
        )

        self.assertIn("three_d", classification["direction_keys"])
        self.assertIn("presentations", classification["direction_keys"])

    def test_universal_stop_words_are_still_global(self):
        classification = classify_vacancy("Ищем копирайтера для презентации.")

        self.assertIn("копирайтер", classification["matched_stop_words"])

    def test_animation_is_a_direction_not_a_stop_word(self):
        classification = classify_vacancy("Нужен аниматор, motion для рекламы.")

        self.assertEqual(classification["matched_stop_words"], [])
        self.assertIn("motion", classification["direction_keys"])


class ProfileMatchingTests(unittest.TestCase):
    def test_same_vacancy_suits_one_user_and_not_another(self):
        text = "Ищем 3D-визуализатора для рендера интерьера. Бюджет 30 000 ₽."
        classification = classify_vacancy(text)

        motion_designer = make_profile(["three_d", "motion"])
        self.assertEqual(
            evaluate_for_user(classification, motion_designer)["status"], "green"
        )
        self.assertEqual(
            evaluate_for_user(classification, DESIGNER)["status"], "red"
        )

    def test_strict_mode_hides_unselected_direction(self):
        result = analyze_vacancy(
            "Нужна анимация для ролика. Бюджет 20 000 ₽.", DESIGNER
        )

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["reason_code"], "off_profile_strict")

    def test_relaxed_mode_shows_unselected_direction_as_yellow(self):
        relaxed = make_profile(DESIGNER.direction_keys, strict_mode=False)
        result = analyze_vacancy(
            "Нужна анимация для ролика. Бюджет 20 000 ₽.", relaxed
        )

        self.assertEqual(result["status"], "yellow")
        self.assertEqual(result["reason_code"], "off_profile")
        self.assertTrue(result["off_profile"])

    def test_priority_follows_order_of_chosen_directions(self):
        result = analyze_vacancy(
            "Нужны баннеры и презентация. Бюджет 20 000 ₽.", DESIGNER
        )

        # «Презентации» выбраны первыми, поэтому приоритет считается по ним.
        self.assertEqual(result["priority"], 0)
        self.assertEqual(result["profile_direction_keys"][0], "presentations")

    def test_personal_budget_threshold_is_used(self):
        text = "Нужна презентация. Бюджет 5 000 ₽."
        classification = classify_vacancy(text)

        cheap = make_profile(["presentations"], min_budget=1500)
        expensive = make_profile(["presentations"], min_budget=20000)

        self.assertEqual(evaluate_for_user(classification, cheap)["status"], "green")
        self.assertEqual(
            evaluate_for_user(classification, expensive)["reason_code"],
            "budget_too_low",
        )

    def test_empty_profile_matches_nothing_in_strict_mode(self):
        result = analyze_vacancy(
            "Нужна презентация. Бюджет 5 000 ₽.", make_profile([])
        )

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["reason_code"], "off_profile_strict")


class VacancyAnalysisTests(unittest.TestCase):
    def test_range_partly_below_minimum_needs_review(self):
        result = analyze_vacancy(
            "Сделать презентацию. Бюджет 1 000–3 000 ₽.", DESIGNER
        )

        self.assertEqual(result["status"], "yellow")

    def test_low_calculated_hourly_project_total_is_rejected(self):
        result = analyze_vacancy("Нужна обложка: 400 ₽/час на 3 часа.", DESIGNER)

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["budget"]["estimated_project_total"], 1200)

    def test_returns_matched_keywords_and_stop_words(self):
        result = analyze_vacancy(
            "Ищем копирайтера для презентации. Бюджет 5 000 ₽.", DESIGNER
        )

        self.assertEqual(result["status"], "red")
        self.assertIn("презентаци", result["matched_keywords"])
        self.assertIn("копирайтер", result["matched_stop_words"])

    def test_rejects_work_that_is_not_design_for_everyone(self):
        result = analyze_vacancy(
            "Нужен frontend разработчик для баннеров. Бюджет 10 000 ₽.",
            make_profile(["banners", "three_d", "motion"]),
        )

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["reason_code"], "stop_words")


if __name__ == "__main__":
    unittest.main()
