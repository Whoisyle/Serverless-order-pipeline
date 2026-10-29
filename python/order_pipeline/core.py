"""Pure order rules: validation, totals, status transitions, and payment policy.

This module imports no cloud SDKs, so it can be unit-tested without Azure.
"""

from __future__ import annotations

import re
from typing import Any

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
TOTAL_TOLERANCE = 0.01
MAX_PAYMENT_ATTEMPTS = 3
# Simulated payment policy: totals above this are declined so failure paths can be exercised.
PAYMENT_LIMIT = 10_000.0


class Status:
    RECEIVED = "received"
    VALIDATED = "validated"
    REJECTED = "rejected"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    FULFILLED = "fulfilled"
    DEAD_LETTERED = "dead_lettered"


TRANSITIONS: dict[str, set[str]] = {
    Status.RECEIVED: {Status.VALIDATED, Status.REJECTED},
    Status.VALIDATED: {Status.PAID, Status.PAYMENT_FAILED},
    Status.PAYMENT_FAILED: {Status.PAID, Status.DEAD_LETTERED},
    Status.PAID: {Status.FULFILLED},
}


class InvalidTransition(Exception):
    """Raised when an order is asked to move to a status it cannot reach."""


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def transition(current: str, target: str) -> str:
    if not can_transition(current, target):
        raise InvalidTransition(f"Cannot move order from {current!r} to {target!r}")
    return target


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def compute_total(items: list[dict[str, Any]]) -> float:
    """Sum of quantity * unitPrice, rounded to cents. Assumes items are already valid."""
    return round(sum(item["quantity"] * item["unitPrice"] for item in items), 2)


def validate_order(order: Any) -> list[str]:
    """Return a list of human-readable errors. An empty list means the order is valid."""
    if not isinstance(order, dict):
        return ["order must be an object"]

    errors: list[str] = []
    if not _nonempty_str(order.get("orderId")):
        errors.append("orderId is required")
    if not _nonempty_str(order.get("customerId")):
        errors.append("customerId is required")

    items = order.get("items")
    items_ok = isinstance(items, list) and len(items) > 0
    if not items_ok:
        errors.append("items must be a non-empty list")
    else:
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"items[{i}] must be an object")
                items_ok = False
                continue
            if not _nonempty_str(item.get("sku")):
                errors.append(f"items[{i}].sku is required")
                items_ok = False
            quantity = item.get("quantity")
            if not _is_int(quantity) or quantity < 1:
                errors.append(f"items[{i}].quantity must be an integer >= 1")
                items_ok = False
            unit_price = item.get("unitPrice")
            if not _is_number(unit_price) or unit_price < 0:
                errors.append(f"items[{i}].unitPrice must be a number >= 0")
                items_ok = False

    currency = order.get("currency")
    if not isinstance(currency, str) or not CURRENCY_RE.match(currency):
        errors.append("currency must be a 3-letter uppercase code")

    total = order.get("total")
    if not _is_number(total) or total < 0:
        errors.append("total must be a number >= 0")
    elif items_ok and abs(total - compute_total(items)) > TOTAL_TOLERANCE:
        errors.append(f"total {total} does not match items sum {compute_total(items)}")

    return errors


def authorize_payment(order: dict[str, Any]) -> bool:
    """Simulated payment decision. Real integrations replace this, not the callers."""
    return float(order["total"]) <= PAYMENT_LIMIT


def should_retry_payment(delivery_count: int) -> bool:
    """delivery_count is 1 on the first attempt."""
    return delivery_count < MAX_PAYMENT_ATTEMPTS
