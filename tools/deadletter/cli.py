#!/usr/bin/env python3
"""CLI to list and reprocess dead-lettered order-pipeline messages.

Dead-lettering is a Service Bus feature, not language-specific, so this one CLI
works regardless of which implementation (Python/TypeScript/C#) is deployed.

Usage:
    python cli.py list [--subscription NAME] [--json]
    python cli.py resubmit --subscription NAME --message-id ID
    python cli.py purge --subscription NAME --message-id ID

Requires DefaultAzureCredential to resolve (az login, a managed identity, etc.)
and the SERVICEBUS_NAMESPACE environment variable (e.g. sb-orderpipe-dev-a1b2.servicebus.windows.net).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

from core import SUBSCRIPTIONS, DeadLetterSummary, can_resubmit, extract_order_id, format_table


def _client() -> ServiceBusClient:
    namespace = os.environ.get("SERVICEBUS_NAMESPACE")
    if not namespace:
        print("Error: set SERVICEBUS_NAMESPACE (e.g. sb-orderpipe-dev-a1b2.servicebus.windows.net)", file=sys.stderr)
        raise SystemExit(2)
    return ServiceBusClient(fully_qualified_namespace=namespace, credential=DefaultAzureCredential())


def _list_one(client: ServiceBusClient, subscription: str, topic: str, max_messages: int) -> list[DeadLetterSummary]:
    summaries: list[DeadLetterSummary] = []
    with client.get_subscription_receiver(
        topic_name=topic, subscription_name=subscription, sub_queue="deadletter", max_wait_time=5
    ) as receiver:
        for msg in receiver.peek_messages(max_message_count=max_messages):
            body = b"".join(msg.body) if hasattr(msg.body, "__iter__") else msg.body
            summaries.append(
                DeadLetterSummary(
                    subscription=subscription,
                    topic=topic,
                    message_id=str(msg.message_id),
                    order_id=extract_order_id(body),
                    delivery_count=msg.delivery_count or 0,
                    dead_letter_reason=msg.dead_letter_reason,
                    dead_letter_error_description=msg.dead_letter_error_description,
                    enqueued_time=str(msg.enqueued_time_utc) if msg.enqueued_time_utc else None,
                )
            )
    return summaries


def cmd_list(args: argparse.Namespace) -> int:
    client = _client()
    subs = {args.subscription: SUBSCRIPTIONS[args.subscription]} if args.subscription else SUBSCRIPTIONS
    all_summaries: list[DeadLetterSummary] = []
    for sub, topic in subs.items():
        all_summaries.extend(_list_one(client, sub, topic, args.max_messages))

    if args.json:
        print(json.dumps([s.to_dict() for s in all_summaries], indent=2))
    else:
        print(format_table(all_summaries))
        resubmittable = sum(1 for s in all_summaries if can_resubmit(s))
        if all_summaries:
            print(f"\n{resubmittable}/{len(all_summaries)} have a recoverable orderId and can be resubmitted.")
    return 0


def cmd_resubmit(args: argparse.Namespace) -> int:
    """Receive-and-complete the dead-lettered message, republishing its body to the
    subscription's source topic so it re-enters the pipeline from that stage."""
    client = _client()
    topic = SUBSCRIPTIONS[args.subscription]
    with client.get_subscription_receiver(
        topic_name=topic, subscription_name=args.subscription, sub_queue="deadletter", max_wait_time=10
    ) as receiver:
        for msg in receiver.receive_messages(max_message_count=20, max_wait_time=5):
            if str(msg.message_id) != args.message_id:
                receiver.abandon_message(msg)
                continue
            body = b"".join(msg.body) if hasattr(msg.body, "__iter__") else msg.body
            with client.get_topic_sender(topic_name=topic) as sender:
                sender.send_messages(ServiceBusMessage(body))
            receiver.complete_message(msg)
            print(f"Resubmitted message {args.message_id} to topic {topic!r}.")
            return 0
    print(f"Message {args.message_id} not found in {args.subscription}'s dead-letter queue.", file=sys.stderr)
    return 1


def cmd_purge(args: argparse.Namespace) -> int:
    client = _client()
    topic = SUBSCRIPTIONS[args.subscription]
    with client.get_subscription_receiver(
        topic_name=topic, subscription_name=args.subscription, sub_queue="deadletter", max_wait_time=10
    ) as receiver:
        for msg in receiver.receive_messages(max_message_count=20, max_wait_time=5):
            if str(msg.message_id) != args.message_id:
                receiver.abandon_message(msg)
                continue
            receiver.complete_message(msg)
            print(f"Purged message {args.message_id} from {args.subscription}'s dead-letter queue.")
            return 0
    print(f"Message {args.message_id} not found in {args.subscription}'s dead-letter queue.", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List dead-lettered messages")
    list_p.add_argument("--subscription", choices=sorted(SUBSCRIPTIONS), help="Limit to one subscription")
    list_p.add_argument("--max-messages", type=int, default=50)
    list_p.add_argument("--json", action="store_true", help="Output JSON instead of a table")

    resub_p = sub.add_parser("resubmit", help="Re-publish a dead-lettered message to its source topic")
    resub_p.add_argument("--subscription", required=True, choices=sorted(SUBSCRIPTIONS))
    resub_p.add_argument("--message-id", required=True)

    purge_p = sub.add_parser("purge", help="Permanently remove a dead-lettered message")
    purge_p.add_argument("--subscription", required=True, choices=sorted(SUBSCRIPTIONS))
    purge_p.add_argument("--message-id", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"list": cmd_list, "resubmit": cmd_resubmit, "purge": cmd_purge}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
