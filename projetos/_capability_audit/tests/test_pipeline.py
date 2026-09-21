import unittest

from audit_app.models import Order
from audit_app.pipeline import run_order
from audit_app.pricing import validate_discount


class PipelineTests(unittest.TestCase):
    def test_total_uses_quantity_price_discount_and_tax(self):
        result = run_order(Order("XAU", 2, 100.0, discount=0.10))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total"], 198.0)

    def test_can_reserve_exact_stock(self):
        result = run_order(Order("EUR", 3, 10.0))
        self.assertEqual(result["status"], "ok")

    def test_discount_above_max_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_discount(0.50)


if __name__ == "__main__":
    unittest.main()
