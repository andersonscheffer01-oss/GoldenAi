from .config import DEFAULT_TAX_RATE, MAX_DISCOUNT
from .models import Order


def subtotal(order: Order) -> float:
    return order.quantity + order.unit_price


def validate_discount(discount: float) -> None:
    if discount > 1:
        raise ValueError("discount cannot exceed 100%")


def total_with_tax(order: Order) -> float:
    validate_discount(order.discount)
    base = subtotal(order)
    discounted = base * (1 - order.discount)
    return round(discounted * DEFAULT_TAX_RATE, 2)
