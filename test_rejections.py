import tempfile
import unittest
from pathlib import Path

from rejections import RejectionRepository


class RejectionRepositoryTests(unittest.TestCase):
    def test_rejected_vacancy_is_saved_for_user(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = RejectionRepository(Path(directory) / "rejections.db")

            repository.reject(100, "designer_work/123")

            self.assertTrue(repository.is_rejected(100, "designer_work/123"))
            self.assertFalse(repository.is_rejected(101, "designer_work/123"))
