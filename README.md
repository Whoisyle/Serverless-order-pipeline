# Serverless Order Pipeline

An event-driven order pipeline on Azure: HTTP intake, Service Bus topics for each stage, Cosmos DB for order state, and retries with dead-lettering. The same pipeline is implemented in **Python**, **TypeScript** and **C#**, and deployed with **Terraform**.

See [docs/architecture.md](docs/architecture.md) for the flow, state machine, and failure handling.

## Repository layout

```
contracts/          Shared order schema and test fixtures (single source of truth)
python/             Core rules, Functions app (v2 model), tests
typescript/         Core rules, Functions app (v4 model), tests
csharp/             Core library and test runner; Functions host (isolated worker)
infra/terraform/    Service Bus, Cosmos DB, Function App, managed-identity RBAC
docs/               Architecture notes
.github/workflows/  CI: tests for all three implementations, Terraform fmt/validate
```

## Run the tests

```bash
# Python
cd python && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt && pytest -q

# TypeScript
cd typescript && npm ci && npm test

# C# core (no NuGet packages needed)
dotnet run --project csharp/OrderPipeline.Tests
```

## Deploy

1. Copy `infra/terraform/terraform.tfvars.example` to `terraform.tfvars` and set `name_suffix` to something unique.
2. `terraform init && terraform plan && terraform apply` in `infra/terraform`.
3. Deploy the chosen implementation to the Function App named in the outputs (`func azure functionapp publish` for Python or TypeScript; `func` or zip deploy for C#).
4. Test: `POST https://<intake_hostname>/api/orders` with a body matching `contracts/fixtures/valid-order.json`. The function key is required.

Nothing has been deployed yet. There is no Azure subscription in this project so far.

## Status

| Part | State |
|---|---|
| Shared rules and fixtures | Done, used by all three tests |
| Python implementation | Tests pass; Functions app imports |
| TypeScript implementation | Tests pass; compiles with `tsc` |
| C# core | Tests pass |
| C# Functions host | Written, **not compiled** (NuGet unavailable where it was written) |
| Terraform | Formatted; **not validated** against the Azure provider (registry unavailable where it was written) |
| CI | Written; not yet run on GitHub |

## Limits

- Payment is simulated; there is no real payment provider.
- No alerting or replay tooling for dead-lettered messages yet.
- Single region. Multi-region failover is a separate project in the planned series.

## Licence

MIT. See [LICENSE](LICENSE).
