# Test Results

These are real, unedited runs from this repository's own test suites, captured in the build environment (not a staged or hand-written transcript). Raw output files are in `docs/test-results/`. They're a snapshot as of the commit that added them — re-run the commands yourself to verify the current state; CI (`.github/workflows/ci.yml`) runs them on every push.

> Nothing here was run against a deployed Azure environment. These are unit tests against the pure business rules and, for Python, a successful import of the Functions app. See [architecture.md](architecture.md) and the main [README](../README.md) for what has and hasn't been verified end-to-end.

## Python — `pytest`

```
$ pytest -v
============================= test session starts ==============================
platform linux -- Python 3.13.18, pytest-9.2.0, pluggy-1.7.0
collecting ... collected 17 items

tests/test_core.py::test_valid_fixture_has_no_errors PASSED              [  5%]
tests/test_core.py::test_total_mismatch_is_reported PASSED               [ 11%]
tests/test_core.py::test_empty_items_is_reported PASSED                  [ 17%]
tests/test_core.py::test_field_errors[<lambda>-orderId is required] PASSED [ 23%]
tests/test_core.py::test_field_errors[<lambda>-customerId is required] PASSED [ 29%]
tests/test_core.py::test_field_errors[<lambda>-currency must be a 3-letter uppercase code] PASSED [ 35%]
tests/test_core.py::test_field_errors[<lambda>-total must be a number >= 0] PASSED [ 41%]
tests/test_core.py::test_field_errors[<lambda>-items[0].quantity must be an integer >= 1_0] PASSED [ 47%]
tests/test_core.py::test_field_errors[<lambda>-items[0].quantity must be an integer >= 1_1] PASSED [ 52%]
tests/test_core.py::test_field_errors[<lambda>-items[0].unitPrice must be a number >= 0] PASSED [ 58%]
tests/test_core.py::test_field_errors[<lambda>-items[0].sku is required] PASSED [ 64%]
tests/test_core.py::test_non_object_order_rejected PASSED                [ 70%]
tests/test_core.py::test_compute_total_rounds_to_cents PASSED            [ 76%]
tests/test_core.py::test_valid_transitions PASSED                        [ 82%]
tests/test_core.py::test_invalid_transition_raises PASSED                [ 88%]
tests/test_core.py::test_payment_policy PASSED                           [ 94%]
tests/test_core.py::test_retry_budget PASSED                             [100%]

============================== 17 passed in 0.06s ==============================
```

`ruff check .` — all checks passed. `python -c "import function_app"` — imports cleanly (confirms the Functions app wires up without errors; it has not been run inside the Azure Functions host).

Full file: [`test-results/python.txt`](test-results/python.txt)

## TypeScript — `node --test` (after `tsc` build)

```
$ npm test
ok 1 - valid fixture has no errors
ok 2 - total mismatch is reported
ok 3 - empty items is reported
ok 4 - field error: orderId required
ok 5 - field error: customerId required
ok 6 - field error: currency format
ok 7 - field error: total type
ok 8 - field error: quantity >= 1
ok 9 - field error: quantity not bool
ok 10 - field error: unitPrice >= 0
ok 11 - field error: sku required
ok 12 - non-object order rejected
ok 13 - computeTotal rounds to cents
ok 14 - valid transitions
ok 15 - invalid transition throws
ok 16 - payment policy
ok 17 - retry budget
1..17
# tests 17
# pass 17
# fail 0
```

Full file (includes the `tsc` build step): [`test-results/typescript.txt`](test-results/typescript.txt)

## C# — dependency-free test runner

No test framework is referenced because NuGet was unreachable in the build environment; `OrderPipeline.Tests` is a plain console app that runs 15 assertions and reports pass/fail counts.

```
$ dotnet run --project csharp/OrderPipeline.Tests
15 passed, 0 failed
```

This covers the same rules as the Python/TypeScript suites, at a coarser granularity (one test per rule rather than one per invalid field, since there's no parametrize/table-test helper without a framework). Full file: [`test-results/csharp.txt`](test-results/csharp.txt)

**Not covered by any test here:** `csharp/OrderPipeline.Functions` (the actual Azure Functions host). It needs NuGet packages the build environment couldn't reach, so it has never been compiled. CI builds it on every push — check the Actions tab for current status.

## Terraform

```
$ terraform fmt -check -recursive
(no output — all files already formatted)
```

`terraform validate` could not be run in the build environment (the Terraform provider registry was unreachable). CI runs `terraform init` and `terraform validate` on every push against real network access — check the Actions tab for current status.

## Cross-implementation agreement

All three implementations are tested against the same fixtures in `contracts/fixtures/`, so "17 tests pass in Python" and "17 tests pass in TypeScript" aren't just two unrelated numbers that happen to match — they're both checking the same `valid-order.json`, `invalid-total.json`, and `invalid-empty-items.json`, plus the same set of single-field mutations (see each language's test file for the exact list). The C# suite checks a subset of the same cases. If you change `contracts/order.schema.json` or add a fixture, update all three test files to keep that true.
