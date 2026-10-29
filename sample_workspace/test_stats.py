import unittest
from stats import mean, maximum


class StatsTest(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([2, 4, 6]), 4)

    def test_empty_mean(self):
        self.assertEqual(mean([]), 0)

    def test_maximum(self):
        self.assertEqual(maximum([2, 9, 3]), 9)


if __name__ == "__main__":
    unittest.main()
