import unittest

from budget_format import THOUSANDS_SEPARATOR, format_amount, format_budget


def money(text):
    """Заменяет неразрывный пробел обычным — так тесты читаются."""

    return text.replace(THOUSANDS_SEPARATOR, " ")


class AmountTests(unittest.TestCase):
    def test_thousands_are_separated(self):
        self.assertEqual(money(format_amount(20000)), "20 000")

    def test_millions_are_separated_too(self):
        self.assertEqual(money(format_amount(1500000)), "1 500 000")

    def test_small_amounts_are_left_alone(self):
        self.assertEqual(format_amount(500), "500")

    def test_separator_does_not_break_the_line(self):
        # Обычный пробел позволил бы Telegram перенести «000» на строку ниже.
        self.assertNotIn(" ", format_amount(20000))


class BudgetTests(unittest.TestCase):
    def test_fixed_amount(self):
        budget = {"payment_type": "fixed", "estimated_project_total": 20000}

        self.assertEqual(money(format_budget(budget)), "20 000 ₽ за проект")

    def test_range(self):
        budget = {"payment_type": "range", "min_amount": 20000, "max_amount": 30000}

        self.assertEqual(money(format_budget(budget)), "20 000–30 000 ₽ за проект")

    def test_open_minimum(self):
        budget = {"payment_type": "from", "min_amount": 5000}

        self.assertEqual(money(format_budget(budget)), "от 5 000 ₽ за проект")

    def test_hourly_rate_with_hours(self):
        budget = {
            "payment_type": "hourly",
            "hourly_rate": 1500,
            "hours": 40,
            "estimated_project_total": 60000,
        }

        self.assertEqual(
            money(format_budget(budget)), "1 500 ₽/час; 40 ч. = 60 000 ₽ за проект"
        )

    def test_hourly_rate_without_hours(self):
        budget = {
            "payment_type": "hourly",
            "hourly_rate": 1500,
            "hours": None,
            "estimated_project_total": None,
        }

        self.assertIn("количество часов не указано", format_budget(budget))

    def test_unknown_budget(self):
        self.assertEqual(format_budget({"payment_type": None}), "не указана")


if __name__ == "__main__":
    unittest.main()
