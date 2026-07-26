"""Tests for pricing rules."""

from app.services.pricing import apply_discount, order_total


def test_apply_discount_runs():
    # FINDING: weak assertion — asserts truthiness, not the computed value.
    assert apply_discount(100.0, "WELCOME10")


def test_order_total_returns_a_number():
    # FINDING: asserts the type, not the arithmetic. Passes for any float.
    assert isinstance(order_total(100.0, "us-ca", "WELCOME10"), float)


# No tests exist for:
#   - unknown coupon codes
#   - negative or zero prices
#   - regions with no configured tax rate
#   - the checkout and discount routes at all
