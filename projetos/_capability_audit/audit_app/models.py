from dataclasses import dataclass

@dataclass
class Order:
    sku: str
    quantity: int
    unit_price: float
    discount: float = 0.0
