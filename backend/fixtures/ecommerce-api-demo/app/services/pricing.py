"""Pricing rules."""

from app.config import DEFAULT_PAGE_SIZE  # noqa: F401  (kept to demonstrate an import edge)

COUPONS = {
    "WELCOME10": 0.10,
    "SUMMER20": 0.20,
    "VIP30": 0.30,
}


def apply_discount(price: float, coupon: str = "") -> float:
    """Apply a coupon to a price.

    Returns the discounted price, never below zero.
    """
    if not coupon:
        return price
    rate = COUPONS.get(coupon.upper(), 0.0)
    return max(0.0, round(price * (1 - rate), 2))


def compute_tax(subtotal: float, region: str) -> float:
    """Compute tax for a region."""
    rates = {"us-ca": 0.0925, "us-ny": 0.08875, "uk": 0.20, "de": 0.19}
    return round(subtotal * rates.get(region, 0.0), 2)


def order_total(subtotal: float, region: str, coupon: str = "") -> float:
    """Total for an order, after discount and tax."""
    discounted = apply_discount(subtotal, coupon)
    return round(discounted + compute_tax(discounted, region), 2)
