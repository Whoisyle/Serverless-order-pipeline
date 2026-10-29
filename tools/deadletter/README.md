# Dead-letter tool

Lists and reprocesses dead-lettered order-pipeline messages. Dead-lettering is a Service Bus feature, not language-specific, so this one CLI works no matter which implementation (Python, TypeScript, or C#) is deployed.

## Status

`core.py` (the pure logic — parsing, summarising, deciding whether a message can be resubmitted) has **12 tests, all passing**, with no Azure dependency. `cli.py` (the actual Service Bus I/O) imports cleanly and its argument parsing is verified, but **it has not been run against a real Service Bus namespace** — there's no Azure subscription attached to this project yet. Review it before pointing it at anything real.

## Install

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

## Use

Requires `SERVICEBUS_NAMESPACE` (from the Terraform output `servicebus_namespace`) and a credential `DefaultAzureCredential` can resolve — `az login` locally, or a managed identity in CI/production.

```bash
export SERVICEBUS_NAMESPACE=sb-orderpipe-dev-a1b2.servicebus.windows.net

# See everything dead-lettered across all three subscriptions
python cli.py list

# One subscription, as JSON
python cli.py list --subscription payment --json

# Put a message back on its source topic, so it re-enters the pipeline
python cli.py resubmit --subscription payment --message-id <id>

# Permanently discard a message (e.g. one with no recoverable orderId)
python cli.py purge --subscription validation --message-id <id>
```

`list` reports how many messages have a recoverable `orderId` and can be resubmitted — a message whose body didn't parse to valid JSON with an `orderId` field should be purged instead, since there's nothing to reprocess it as.

## Run the tests

```bash
pytest -v      # 12 tests, core.py only, no Azure needed
ruff check .
```

## Design

```
cli.py    Service Bus I/O: peek/receive/complete/send. NOT unit tested (needs a live namespace).
core.py   Pure functions: extract_order_id, can_resubmit, format_table. Fully unit tested.
```

Same split used by the pipeline's own `core.py`/Functions-host pairing in `python/`, `typescript/`, and `csharp/` — business logic stays testable without cloud credentials, I/O stays thin.
