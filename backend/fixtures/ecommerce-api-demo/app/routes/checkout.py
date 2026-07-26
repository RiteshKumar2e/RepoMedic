"""Checkout endpoints."""

import time

import requests
from fastapi import APIRouter

from app.config import INVOICE_DIRECTORY, STRIPE_SECRET_KEY
from app.db import get_cursor, session
from app.models import LineItem, Order
from app.services.pricing import apply_discount

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/orders")
async def create_order(customer_id: str, cart_id: str, coupon: str = ""):
    """Create an order from a cart.

    No authentication dependency: any caller can create an order for any
    customer_id they choose.
    """
    cursor = get_cursor()

    # FINDING: SQL injection — cart_id is interpolated straight into the query.
    cursor.execute(f"SELECT * FROM carts WHERE id = '{cart_id}'")
    cart = cursor.fetchone()
    if not cart:
        return {"error": "cart not found"}

    total = 0.0
    items = []
    # FINDING: N+1 — one product query per cart line.
    for line in cart["lines"]:
        product = session.query("SELECT * FROM products WHERE id = %s", line["product_id"]).first()
        price = apply_discount(product["price"], coupon)
        total += price * line["quantity"]
        items.append(LineItem(product_id=product["id"], quantity=line["quantity"], price=price))

    # FINDING: blocking synchronous HTTP call inside an async route, and no timeout.
    charge = requests.post(
        "https://api.stripe.com/v1/charges",
        auth=(STRIPE_SECRET_KEY, ""),
        data={"amount": int(total * 100), "currency": "usd"},
    )

    # FINDING: blocking sleep inside an async route.
    time.sleep(0.5)

    order = Order(customer_id=customer_id, total=total, items=items, charge_id=charge.json()["id"])
    session.add(order)
    session.commit()

    return {"order_id": order.id, "total": total, "charge": charge.json()}


@router.get("/orders/{order_id}/invoice")
async def download_invoice(order_id: str, filename: str):
    """Return a stored invoice file."""
    # FINDING: path traversal — filename comes straight from the query string.
    with open(f"{INVOICE_DIRECTORY}/{filename}", "rb") as handle:
        return handle.read()


@router.post("/orders/{order_id}/refund")
async def refund_order(order_id: str, amount: float):
    """Refund an order."""
    cursor = get_cursor()
    try:
        cursor.execute("UPDATE orders SET refunded = %s WHERE id = %s", (amount, order_id))
    except:  # FINDING: bare except swallowing every failure, including the refund failing
        pass
    return {"refunded": amount}
