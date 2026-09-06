import unittest

from commitment import ANY, ONE_OFF, ONGOING, commitment_label, detect_commitment
from filter import classify_vacancy, evaluate_for_user
from profiles import UserProfile


def make_profile(commitment=ANY, max_budget=0, min_budget=1000):
    return UserProfile(
        user_id=1,
        direction_keys=("presentations",),
        min_budget=min_budget,
        strict_mode=True,
        portfolio_url="https://example.com/p",
        max_budget=max_budget,
        commitment=commitment,
    )


class CommitmentDetectionTests(unittest.TestCase):
    def test_permanent_work_is_recognised(self):
        for text in (
            "Нужен дизайнер на постоянной основе.",
            "Ищем дизайнера в штат, оклад 60 000 руб.",
            "Загрузка 20 часов в неделю, долгосрочное сотрудничество.",
            "Оплата ежемесячно, постоянный поток задач.",
        ):
            with self.subTest(text=text):
                self.assertEqual(detect_commitment(text), ONGOING)

    def test_one_off_work_is_recognised(self):
        for text in (
            "Разовая задача: сделать афишу.",
            "Нужен один макет, к завтра.",
            "Сделать до конца дня, оплата сразу.",
        ):
            with self.subTest(text=text):
                self.assertEqual(detect_commitment(text), ONE_OFF)

    def test_named_amount_of_work_counts_as_one_off(self):
        self.assertEqual(
            detect_commitment("Нужно 20 слайдов для инвесторов."), ONE_OFF
        )

    def test_permanent_wins_when_both_signals_are_present(self):
        # Объём назван, но работа постоянная — это долгосрок.
        text = "Нужно 10 карточек в неделю на постоянной основе."

        self.assertEqual(detect_commitment(text), ONGOING)

    def test_silence_about_duration_leaves_it_unknown(self):
        text = "Требуется дизайнер презентаций. Бюджет 25 000 руб."

        self.assertIsNone(detect_commitment(text))
        self.assertIsNone(commitment_label(None))

    def test_commitment_lands_in_the_classification(self):
        classification = classify_vacancy(
            "Нужен дизайнер на постоянной основе. Бюджет 50 000 руб."
        )

        self.assertEqual(classification["commitment"], ONGOING)


class CommitmentFilterTests(unittest.TestCase):
    ONGOING_VACANCY = (
        "Нужен дизайнер презентаций на постоянной основе. Оклад 60 000 руб."
    )
    ONE_OFF_VACANCY = "Разовая задача: одна презентация к завтра. 20 000 руб."
    UNCLEAR_VACANCY = "Требуется дизайнер презентаций. Бюджет 25 000 руб."

    def _status(self, text, profile):
        return evaluate_for_user(classify_vacancy(text), profile)

    def test_any_format_lets_everything_through(self):
        profile = make_profile(ANY)

        for text in (
            self.ONGOING_VACANCY,
            self.ONE_OFF_VACANCY,
            self.UNCLEAR_VACANCY,
        ):
            with self.subTest(text=text):
                self.assertEqual(self._status(text, profile)["status"], "green")

    def test_one_off_preference_hides_permanent_work(self):
        result = self._status(self.ONGOING_VACANCY, make_profile(ONE_OFF))

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["reason_code"], "wrong_commitment")

    def test_ongoing_preference_hides_one_off_work(self):
        result = self._status(self.ONE_OFF_VACANCY, make_profile(ONGOING))

        self.assertEqual(result["reason_code"], "wrong_commitment")

    def test_unclear_duration_is_never_hidden(self):
        # Про длительность пишут редко, поэтому неопределённые вакансии
        # проходят при любой настройке — иначе выдача схлопнется.
        for preference in (ONE_OFF, ONGOING):
            with self.subTest(preference=preference):
                result = self._status(
                    self.UNCLEAR_VACANCY, make_profile(preference)
                )
                self.assertEqual(result["status"], "green")

    def test_result_carries_the_detected_commitment(self):
        result = self._status(self.ONGOING_VACANCY, make_profile(ANY))

        self.assertEqual(result["commitment"], ONGOING)

    def test_classification_without_commitment_still_works(self):
        # Вакансии, разобранные прошлой версией, ключа не содержат.
        classification = classify_vacancy(self.UNCLEAR_VACANCY)
        del classification["commitment"]

        result = evaluate_for_user(classification, make_profile(ONE_OFF))

        self.assertEqual(result["status"], "green")
        self.assertIsNone(result["commitment"])


class MaxBudgetTests(unittest.TestCase):
    EXPENSIVE = "Презентация под ключ, полный ребрендинг. Бюджет 300 000 руб."
    MODEST = "Нужна презентация. Бюджет 25 000 руб."

    def _status(self, text, profile):
        return evaluate_for_user(classify_vacancy(text), profile)

    def test_no_ceiling_by_default(self):
        self.assertEqual(
            self._status(self.EXPENSIVE, make_profile())["status"], "green"
        )

    def test_vacancy_above_the_ceiling_is_hidden(self):
        result = self._status(self.EXPENSIVE, make_profile(max_budget=100000))

        self.assertEqual(result["status"], "red")
        self.assertEqual(result["reason_code"], "budget_too_high")

    def test_vacancy_under_the_ceiling_passes(self):
        result = self._status(self.MODEST, make_profile(max_budget=100000))

        self.assertEqual(result["status"], "green")

    def test_range_starting_below_the_ceiling_still_passes(self):
        # Верхняя граница выше потолка, но нижняя в пределах — торг уместен.
        text = "Нужна презентация, бюджет 50 000–200 000 руб."

        result = self._status(text, make_profile(max_budget=100000))

        self.assertNotEqual(result["reason_code"], "budget_too_high")


if __name__ == "__main__":
    unittest.main()
