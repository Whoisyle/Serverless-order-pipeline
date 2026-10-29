<div align="center">

# Serverless Order Pipeline

Event-driven order processing on Azure · Python, TypeScript &amp; C# · Terraform

An order pipeline built on Azure Functions and Service Bus, with the same business rules implemented three times so the architecture, not the language, is what's being demonstrated.

<p>
  <img src="https://img.shields.io/badge/Azure-0078D4?style=for-the-badge&logo=microsoftazure&logoColor=white" alt="Azure">
  <img src="https://img.shields.io/badge/Terraform-7B42BC?style=for-the-badge&logo=terraform&logoColor=white" alt="Terraform">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/C%23-239120?style=for-the-badge&logo=csharp&logoColor=white" alt="C#">
</p>

Architecture · Layout · Running the Tests · Test Results · Deploying · Status · Limits

</div>

────────

## Overview

Orders arrive over HTTP, move through validation, payment and fulfilment as Service Bus messages, and land in Cosmos DB at every stage. Failed payments retry automatically and dead-letter once the retry budget is spent, so a failure is recorded rather than lost.

The same rules — validation, totals, status transitions, payment policy — are implemented independently in Python, TypeScript and C#, against one shared JSON schema and one set of test fixtures in `contracts/`. Every implementation's tests run against those same fixtures, so "the same pipeline in three languages" is something the tests check, not just a claim in this file.

![Message flow sequence diagram](docs/diagrams/message-flow.png)

See **[docs/architecture.md](docs/architecture.md)** for the full flow, the order state machine, and how failures are handled — including the [dead-letter inspection tool](tools/deadletter/README.md).

────────

## Repository layout

```
contracts/           Shared order schema and test fixtures (single source of truth)
python/               Core rules, Functions app (v2 model), tests
typescript/           Core rules, Functions app (v4 model), tests
csharp/                Core library and test runner; Functions host (isolated worker)
infra/terraform/      Service Bus, Cosmos DB, Function App, managed-identity RBAC
tools/deadletter/     CLI to list and reprocess dead-lettered messages
docs/                 Architecture notes, diagrams, captured test output
.github/workflows/    CI: tests for all three implementations, Terraform fmt/validate
```

────────

## Running the tests

```bash
# Python
cd python && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest -q

# TypeScript
cd typescript && npm ci && npm test

# C# core (no NuGet packages required)
dotnet run --project csharp/OrderPipeline.Tests

# Dead-letter tool (logic only — no Azure needed)
cd tools/deadletter && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest -v
```

────────

## Test results

Real, captured output from the commands above — not hand-written — is in **[docs/TEST_RESULTS.md](docs/TEST_RESULTS.md)**, with the raw files in [`docs/test-results/`](docs/test-results/).

────────

## Deploying

1. Copy `infra/terraform/terraform.tfvars.example` to `terraform.tfvars` and set `name_suffix` to something globally unique.
2. From `infra/terraform`: `terraform init && terraform plan && terraform apply`.
3. For local testing first, copy the chosen implementation's `local.settings.json.example` to `local.settings.json` and fill in the Service Bus namespace and Cosmos endpoint from the Terraform outputs.
4. Deploy the chosen implementation to the Function App named in the Terraform outputs — `func azure functionapp publish` for Python or TypeScript, or a zip deploy for C#.
5. Test with `POST https://<intake_hostname>/api/orders`, body matching `contracts/fixtures/valid-order.json`, and the function key.

No Azure subscription has been attached to this project yet, so nothing above has been deployed or run against real Azure resources.

────────

## Status

| Part | State |
|---|---|
| Shared rules and fixtures | Done — used by all three test suites |
| Python implementation | 17 tests pass; Functions app imports cleanly |
| TypeScript implementation | 17 tests pass; compiles with `tsc` |
| C# core | 15 tests pass |
| C# Functions host | Written, **not compiled** — NuGet was unreachable in the build environment |
| Dead-letter tool | 12 tests pass (pure logic); Service Bus I/O **not run against a live namespace** |
| Architecture diagrams | Generated from Mermaid source in `docs/diagrams/`, not screenshots of a running system — nothing is deployed yet |
| Terraform | Formatted; **not validated** against the Azure provider — the registry was unreachable in the build environment |
| CI | Written; not yet run on GitHub |

────────

## Known limits

- Payment is simulated behind a fixed threshold — there is no real payment provider integration.
- There's a CLI to inspect and resubmit dead-lettered messages (`tools/deadletter/`), but no automatic alerting yet.
- Single region only. Multi-region failover is a separate, planned project.
- Nothing has been deployed to Azure. The C# Functions host, the dead-letter tool's Service Bus calls, and the Terraform configuration all need to be built/validated on a machine with real network access before first deploy — see [Status](#status) for exactly what has and hasn't been checked.

────────

## Engineering principles

- **Contract first** — one schema and one set of fixtures that every implementation must satisfy.
- **Fail visibly** — invalid orders are rejected and recorded; payment failures retry, then dead-letter; nothing fails silently.
- **No standing secrets** — managed identity and RBAC throughout; no connection strings or access keys.
- **State the gaps** — anything unverified in this build is listed above, not glossed over.

<div align="center">

Part of an ongoing series of cloud and security projects · [github.com/Whoisyle](https://github.com/Whoisyle)

</div>
