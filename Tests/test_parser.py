import unittest
from App.parser import equation_splitter, evaluate_expression   

class TestParser(unittest.TestCase):
    def test_equation_splitter(self):
        self.assertEqual(equation_splitter("2x = 4"), ("2x", "4"))
        self.assertEqual(equation_splitter(" 3y + 5 = 10 "), ("3y+5", "10"))
        self.assertIsNone(equation_splitter("2x + 4"))

    def test_evaluate_expression(self):
        self.assertEqual(evaluate_expression("2x + 6", 4), 14)
        self.assertEqual(evaluate_expression("x + 3", 2), 5)


if __name__ == "__main__":
    unittest.main()