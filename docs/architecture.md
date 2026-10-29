# Architecture

## Flow

```
client ──POST /api/orders──▶ [intake] ──▶ Service Bus topic "orders"
                                              │ subscription "validation"
                                              ▼
                                         [validation] ──▶ topic "payments"
                                              │ subscription "payment"
                                              ▼
                                          [payment] ──▶ topic "fulfilment"
                                              │ subscription "fulfilment"
                                              ▼
                                         [fulfilment]

Every stage writes order state to Cosmos DB (container "orders", partition key /orderId).
```

## Order states

| From | To | When |
|---|---|---|
| (none) | `received` | intake accepts a request |
| `received` | `validated` | validation passes |
| `received` | `rejected` | validation fails (reason recorded) |
| `validated` | `paid` | payment authorised |
| `validated` | `payment_failed` | payment declined, will retry |
| `payment_failed` | `paid` | retry succeeds |
| `payment_failed` | `dead_lettered` | retry budget exhausted |
| `paid` | `fulfilled` | fulfilment completes |

Illegal transitions raise an error in every implementation, so a message redelivered after a crash cannot move an order backwards.

## Failure handling

- **Payment declines** raise an error inside the trigger. Service Bus redelivers the message until `max_delivery_count` (5 by default, see Terraform) is reached, then moves it to the dead-letter queue. The payment stage also stops retrying itself after 3 deliveries and marks the order `dead_lettered`.
- **Invalid orders** are recorded as `rejected` and not retried. They are not errors, so they do not clog the queue.
- **Duplicate messages** are safe because each write is an upsert keyed by `orderId`, and transitions are checked against the stored state.

## Identity and secrets

No connection strings or keys. Function Apps use a system-assigned managed identity with these roles:

- Service Bus namespace: Azure Service Bus Data Sender and Data Receiver
- Storage account: Storage Blob Data Owner (for the Functions host)
- Cosmos DB account: Cosmos DB Built-in Data Contributor (data plane only; key auth is disabled)

## Implementations

The three implementations share the rules in `contracts/` and must agree on every fixture:

| Language | Core | Functions host | Verified here |
|---|---|---|---|
| Python | `python/order_pipeline/core.py` | `python/function_app.py` (v2 model) | 17 tests pass, Functions app imports |
| TypeScript | `typescript/src/core.ts` | `typescript/src/functions.ts` (v4 model) | 17 tests pass |
| C# | `csharp/OrderPipeline/Core/OrderRules.cs` | `csharp/OrderPipeline.Functions/` (isolated worker) | 15 tests pass; Functions host **not compiled** (needs NuGet) |

Python and TypeScript both build the same pipeline; C# core tests cover the same rules. Only one implementation needs to be deployed. Choose it with the Terraform `runtime` variable.

## Known gaps (v1)

- Payment is simulated (`PAYMENT_LIMIT`). No real payment provider.
- No dead-letter processing or alerting yet; dead-lettered messages must be inspected manually.
- Cosmos DB is serverless, single region. Multi-region failover is a separate project.
- Terraform has not been validated against the Azure provider in this environment (the registry was unreachable). Run `terraform validate` and `terraform plan` before first deploy.
