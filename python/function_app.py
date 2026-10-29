"""Azure Functions (Python v2 model) for the order pipeline.

Flow: HTTP intake -> topic "orders" -> validation -> topic "payments" -> payment
-> topic "fulfilment" -> fulfilment. Order state lives in Cosmos DB.
Failed payments are retried by Service Bus and dead-lettered after the retry budget.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import azure.functions as func
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from order_pipeline.core import (
    Status,
    authorize_payment,
    should_retry_payment,
    transition,
    validate_order,
)

app = func.FunctionApp()
log = logging.getLogger("order_pipeline")

_sb: ServiceBusClient | None = None
_orders = None


def _servicebus() -> ServiceBusClient:
    global _sb
    if _sb is None:
        _sb = ServiceBusClient(
            fully_qualified_namespace=os.environ["ServiceBusConnection__fullyQualifiedNamespace"],
            credential=DefaultAzureCredential(),
        )
    return _sb


def _orders_container():
    global _orders
    if _orders is None:
        client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=DefaultAzureCredential())
        _orders = client.get_database_client(os.environ.get("COSMOS_DATABASE", "orders")).get_container_client("orders")
    return _orders


def _send(topic: str, payload: dict[str, Any]) -> None:
    with _servicebus().get_topic_sender(topic_name=topic) as sender:
        sender.send_messages(ServiceBusMessage(json.dumps(payload)))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _save(order: dict[str, Any], status: str, reason: str | None = None) -> None:
    doc = {
        "id": order["orderId"],
        "orderId": order["orderId"],
        "customerId": order.get("customerId"),
        "status": status,
        "reason": reason,
        "updatedAt": _now(),
    }
    _orders_container().upsert_item(doc)


def _move(order: dict[str, Any], target: str, reason: str | None = None) -> None:
    """Advance an order to a new status, refusing illegal transitions."""
    container = _orders_container()
    try:
        current = container.read_item(item=order["orderId"], partition_key=order["orderId"])["status"]
    except CosmosResourceNotFoundError:  # first write for this order
        current = Status.RECEIVED
    if current != target:
        transition(current, target)
    _save(order, target, reason)


@app.route(route="orders", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def intake(req: func.HttpRequest) -> func.HttpResponse:
    try:
        order = req.get_json()
    except ValueError:
        return func.HttpResponse("Body must be JSON", status_code=400)
    if not isinstance(order, dict) or not order.get("orderId"):
        return func.HttpResponse("orderId is required", status_code=400)

    _save(order, Status.RECEIVED)
    _send("orders", order)
    return func.HttpResponse(json.dumps({"orderId": order["orderId"], "status": Status.RECEIVED}), status_code=202, mimetype="application/json")


@app.service_bus_topic_trigger(arg_name="msg", topic_name="orders", subscription_name="validation", connection="ServiceBusConnection")
def validate(msg: func.ServiceBusMessage) -> None:
    order = json.loads(msg.get_body().decode("utf-8"))
    errors = validate_order(order)
    if errors:
        log.info("order %s rejected: %s", order.get("orderId"), errors)
        _move(order, Status.REJECTED, reason="; ".join(errors))
        return
    _move(order, Status.VALIDATED)
    _send("payments", order)


@app.service_bus_topic_trigger(arg_name="msg", topic_name="payments", subscription_name="payment", connection="ServiceBusConnection")
def pay(msg: func.ServiceBusMessage) -> None:
    order = json.loads(msg.get_body().decode("utf-8"))
    if authorize_payment(order):
        _move(order, Status.PAID)
        _send("fulfilment", order)
        return

    if should_retry_payment(msg.delivery_count or 1):
        _move(order, Status.PAYMENT_FAILED, reason="declined")
        # Raising makes Service Bus redeliver the message for another attempt.
        raise RuntimeError(f"payment declined for {order['orderId']}; retrying")

    _move(order, Status.DEAD_LETTERED, reason="payment declined after retries")
    log.warning("order %s dead-lettered after payment retries", order["orderId"])


@app.service_bus_topic_trigger(arg_name="msg", topic_name="fulfilment", subscription_name="fulfilment", connection="ServiceBusConnection")
def fulfil(msg: func.ServiceBusMessage) -> None:
    order = json.loads(msg.get_body().decode("utf-8"))
    _move(order, Status.FULFILLED)
