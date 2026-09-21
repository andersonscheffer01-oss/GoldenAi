STOCK = {
    "XAU": 10,
    "EUR": 3,
}


def reserve(sku: str, quantity: int) -> bool:
    available = STOCK.get(sku, 0)
    if available <= quantity:
        return False
    STOCK[sku] = available - quantity
    return True
