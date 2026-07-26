"""Domain models."""

from dataclasses import dataclass, field


@dataclass
class LineItem:
    product_id: str
    quantity: int
    price: float


@dataclass
class Order:
    customer_id: str
    total: float
    items: list = field(default_factory=list)
    charge_id: str = ""
    id: str = ""
    refunded: float = 0.0


@dataclass
class Discount:
    code: str
    percentage: float
    active: bool = True
    id: str = ""
