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

    def test_accepts_parentheses(self):
        result = detect_first_error(["2(x + 3) = 14", "2x + 6 = 14"])
        self.assertTrue(result.passed)

    def test_accepts_other_variable_names(self):
        result = detect_first_error(["3y = 9", "y = 3"])
        self.assertTrue(result.passed)

    def test_accepts_inequalities(self):
        result = detect_first_error(["x < 5", "5 > x"])
        self.assertTrue(result.passed)

    def test_accepts_system_of_equations(self):
        result = detect_first_error([
            "x + y = 5",
            "x - y = 1",
            "y = x - 1",
            "x + (x - 1) = 5",
            "2x = 6",
            "x = 3",
            "y = (3) - 1",
            "y = 2",
        ])
        self.assertTrue(result.passed)

    def test_accepts_volume_substitution(self):
        result = detect_first_error([
            "V = 4/3 π r^3",
            "r = 3",
            "V = 4/3 π (3)^3",
            "V = 36π",
        ])
        self.assertTrue(result.passed)

    def test_accepts_volume_with_units(self):
        result = detect_first_error([
            "V = 4/3 π r^3",
            "r = 3",
            "V = 4/3 π (3)^3",
            "V = 36π cm^3",
        ])
        self.assertTrue(result.passed)

    def test_accepts_area_with_units_and_unicode_power(self):
        result = detect_first_error([
            "A = πr²",
            "r = 4",
            "A = 16π in²",
        ])
        self.assertTrue(result.passed)

    def test_accepts_reversed_formula(self):
        result = detect_first_error([
            "4/3 π r^3 = V",
            "r = 3",
            "36π = V",
        ])
        self.assertTrue(result.passed)

    def test_accepts_answer_only_final_line(self):
        result = detect_first_error([
            "A = 1/2 b h",
            "b = 10",
            "h = 6",
            "30",
        ])
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
