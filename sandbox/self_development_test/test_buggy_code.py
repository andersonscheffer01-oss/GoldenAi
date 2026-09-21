"""Tests for the buggy_code module.

These tests will fail until the bug in add() is fixed.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buggy_code import add, multiply, divide


class BuggyCodeTests(unittest.TestCase):
    def test_add_returns_sum(self):
        self.assertEqual(add(2, 3), 5)

    def test_add_with_negatives(self):
        self.assertEqual(add(-1, 1), 0)

    def test_multiply(self):
        self.assertEqual(multiply(3, 4), 12)

    def test_divide(self):
        self.assertEqual(divide(10, 2), 5.0)

    def test_divide_by_zero(self):
        with self.assertRaises(ZeroDivisionError):
            divide(1, 0)


if __name__ == "__main__":
    unittest.main()