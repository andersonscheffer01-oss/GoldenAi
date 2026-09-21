from .inventory import reserve
from .pricing import total_with_tax


def run_order(order):
    if not reserve(order.sku, order.quantity):
        return {"status": "rejected", "total": 0}
    return {"status": "ok", "total": total_with_tax(order)}
