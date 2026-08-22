import unittest

from filter import analyze_vacancy, extract_budget


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


class VacancyAnalysisTests(unittest.TestCase):
    def test_range_partly_below_minimum_needs_review(self):
        result = analyze_vacancy("Сделать презентацию. Бюджет 1 000–3 000 ₽.")

        self.assertEqual(result["status"], "yellow")

    def test_low_calculated_hourly_project_total_is_rejected(self):
        result = analyze_vacancy("Нужна обложка: 400 ₽/час на 3 часа.")

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["budget"]["estimated_project_total"], 1200)

    def test_returns_matched_keywords_and_stop_words(self):
        result = analyze_vacancy("Ищем копирайтера для презентации. Бюджет 5 000 ₽.")

        self.assertEqual(result["status"], "red")
        self.assertIn("презентаци", result["matched_keywords"])
        self.assertIn("копирайтер", result["matched_stop_words"])

    def test_rejects_3d_and_motion_specializations(self):
        result = analyze_vacancy(
            "Ищем 3D Motion Designer для рекламных креативов. Бюджет 10 000 ₽."
        )

        self.assertEqual(result["status"], "red")
        self.assertIn("3d", result["matched_stop_words"])
        self.assertIn("motion", result["matched_stop_words"])


if __name__ == "__main__":
    unittest.main()
