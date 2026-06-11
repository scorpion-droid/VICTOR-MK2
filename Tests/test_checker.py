import unittest
from App.checker import detect_first_error


class TestChecker(unittest.TestCase):
    def test_accepts_simple_matching_steps(self):
        result = detect_first_error(["2x = 4", "x = 2"])
        self.assertTrue(result.passed)

    def test_rejects_wrong_step(self):
        result = detect_first_error(["2x = 4", "x = 3"])
        self.assertFalse(result.passed)
        self.assertEqual(result.first_error_index, 1)


if __name__ == "__main__":
    unittest.main()