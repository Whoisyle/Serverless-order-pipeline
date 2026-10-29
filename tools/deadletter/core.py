"""Pure logic for dead-letter inspection: summarising and deciding what to do with a
dead-lettered message. No Azure SDK imports here, so this is unit-testable without a
live Service Bus namespace. cli.py does the actual Service Bus I/O and calls into this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# The three subscriptions that can dead-letter a message, and which topic each
# one reads from. Must match infra/terraform/main.tf's `local.topics` map.
SUBSCRIPTIONS: dict[str, str] = {
    "validation": "orders",
    "payment": "payments",
    "fulfilment": "fulfilment",
}


@dataclass(frozen=True)
class DeadLetterSummary:
    """Human-readable view of one dead-lettered message, independent of the SDK type."""

    subscription: str
    topic: str
    message_id: str
    order_id: str | None
    delivery_count: int
    dead_letter_reason: str | None
    dead_letter_error_description: str | None
    enqueued_time: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subscription": self.subscription,
            "topic": self.topic,
            "messageId": self.message_id,
            "orderId": self.order_id,
            "deliveryCount": self.delivery_count,
            "deadLetterReason": self.dead_letter_reason,
            "deadLetterErrorDescription": self.dead_letter_error_description,
            "enqueuedTime": self.enqueued_time,
        }


def extract_order_id(body: bytes | str | None) -> str | None:
    """Best-effort extraction of orderId from a message body for display purposes.

    Returns None on anything that isn't a JSON object with an orderId — this is for
    showing a human something useful, not for validating the message.
    """
    if body is None:
        return None
    try:
        text = body.decode("utf-8") if isinstance(body, bytes) else body
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(data, dict):
        order_id = data.get("orderId")
        return order_id if isinstance(order_id, str) and order_id else None
    return None


def can_resubmit(summary: DeadLetterSummary) -> bool:
    """A message can only be meaningfully resubmitted if we know which order it was.

    A message with no recoverable orderId should be purged, not resubmitted, since
    there is nothing to reprocess it as.
    """
    return summary.order_id is not None


def format_table(summaries: list[DeadLetterSummary]) -> str:
    """Render a plain-text table for terminal display. Returns a 'none found' line if empty."""
    if not summaries:
        return "No dead-lettered messages found."

    rows = [("SUBSCRIPTION", "ORDER ID", "DELIVERIES", "REASON")]
    for s in summaries:
        rows.append((s.subscription, s.order_id or "(unknown)", str(s.delivery_count), s.dead_letter_reason or "-"))

    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    lines = []
    for i, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row)))
        if i == 0:
            lines.append("  ".join("-" * widths[j] for j in range(4)))
    return "\n".join(lines)
