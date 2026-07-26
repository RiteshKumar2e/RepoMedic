"""Discount endpoints."""

from fastapi import APIRouter

from app.db import session
from app.models import Discount

router = APIRouter(prefix="/discounts", tags=["discounts"])


@router.post("/")
async def create_discount(payload: dict, actor_role: str = "guest"):
    """Create a discount code.

    `payload` is an untyped dict, so nothing validates its shape.
    """
    # FINDING: authorization enforced with `assert`, which `python -O` removes.
    assert actor_role == "admin", "only admins may create discounts"

    # FINDING: duplicated validation logic (see validate_code below).
    code = payload.get("code", "")
    if not code or len(code) < 4 or len(code) > 32 or not code.isalnum():
        return {"error": "invalid code"}

    percentage = payload.get("percentage", 0)
    if percentage <= 0 or percentage > 90:
        return {"error": "invalid percentage"}

    discount = Discount(code=code.upper(), percentage=percentage)
    session.add(discount)
    session.commit()
    return {"id": discount.id, "code": discount.code}


@router.get("/")
async def list_discounts(active_only: bool = True):
    """List every discount."""
    # FINDING: unbounded query — returns the whole table with no pagination.
    return session.query(Discount).filter(Discount.active == active_only).all()


def validate_code(code: str) -> bool:
    """Validate a discount code."""
    # FINDING: duplicate of the inline validation in create_discount.
    if not code:
        return False
    if len(code) < 4 or len(code) > 32:
        return False
    if not code.isalnum():
        return False
    return True
