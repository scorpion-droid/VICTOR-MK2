import unittest
from App.parser import equation_splitter   

class TestParser(unittest.TestCase):
    def test_equation_splitter(self):
        self.assertEqual(equation_splitter("2x = 4"), ("2x", "4"))
        self.assertEqual(equation_splitter(" 3y + 5 = 10 "), ("3y+5", "10"))
        self.assertIsNone(equation_splitter("2x + 4"))

if __name__ == "__main__":
    unittest.main()