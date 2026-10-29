import json
from pathlib import Path

import pytest

from order_pipeline.core import (
    InvalidTransition,
    Status,
    authorize_payment,
    compute_total,
    should_retry_payment,
    transition,
    validate_order,
)

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_fixture_has_no_errors():
    assert validate_order(load("valid-order.json")) == []


def test_total_mismatch_is_reported():
    errors = validate_order(load("invalid-total.json"))
    assert any("does not match" in e for e in errors)


def test_empty_items_is_reported():
    assert "items must be a non-empty list" in validate_order(load("invalid-empty-items.json"))


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda o: o.update(orderId=""), "orderId is required"),
        (lambda o: o.update(customerId="  "), "customerId is required"),
        (lambda o: o.update(currency="zar"), "currency must be a 3-letter uppercase code"),
        (lambda o: o.update(total="10"), "total must be a number >= 0"),
        (lambda o: o["items"][0].update(quantity=0), "items[0].quantity must be an integer >= 1"),
        (lambda o: o["items"][0].update(quantity=True), "items[0].quantity must be an integer >= 1"),
        (lambda o: o["items"][0].update(unitPrice=-1), "items[0].unitPrice must be a number >= 0"),
        (lambda o: o["items"][0].pop("sku"), "items[0].sku is required"),
    ],
)
def test_field_errors(mutate, expected):
    order = load("valid-order.json")
    mutate(order)
    assert expected in validate_order(order)


def test_non_object_order_rejected():
    assert validate_order(["not", "an", "order"]) == ["order must be an object"]


def test_compute_total_rounds_to_cents():
    items = [{"sku": "a", "quantity": 3, "unitPrice": 0.1}]
    assert compute_total(items) == 0.3


def test_valid_transitions():
    assert transition(Status.RECEIVED, Status.VALIDATED) == Status.VALIDATED
    assert transition(Status.PAYMENT_FAILED, Status.PAID) == Status.PAID
    assert transition(Status.PAID, Status.FULFILLED) == Status.FULFILLED


def test_invalid_transition_raises():
    with pytest.raises(InvalidTransition):
        transition(Status.FULFILLED, Status.PAID)


def test_payment_policy():
    assert authorize_payment({"total": 100.0})
    assert not authorize_payment({"total": 20_000.0})


def test_retry_budget():
    assert should_retry_payment(1)
    assert should_retry_payment(2)
    assert not should_retry_payment(3)
