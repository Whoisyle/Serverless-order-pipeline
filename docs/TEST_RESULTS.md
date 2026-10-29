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

**Not covered by any test here:** `csharp/OrderPipeline.Functions` (the actual Azure Functions host). It needs NuGet packages this build environment couldn't reach, so it was never compiled locally — but CI (which has real NuGet access) builds it on every push, and that build passes. See [Known limits](../README.md#known-limits) for what that does and doesn't prove.

## Dead-letter tool

```
$ pytest -v
============================= test session starts ==============================
collecting ... collected 12 items

tests/test_core.py::test_extract_order_id_from_valid_json_bytes PASSED   [  8%]
tests/test_core.py::test_extract_order_id_from_valid_json_str PASSED     [ 16%]
tests/test_core.py::test_extract_order_id_missing_field PASSED           [ 25%]
tests/test_core.py::test_extract_order_id_non_dict_json PASSED           [ 33%]
tests/test_core.py::test_extract_order_id_malformed_json PASSED          [ 41%]
tests/test_core.py::test_extract_order_id_none_body PASSED               [ 50%]
tests/test_core.py::test_extract_order_id_bad_unicode PASSED             [ 58%]
tests/test_core.py::test_can_resubmit_with_order_id PASSED               [ 66%]
tests/test_core.py::test_cannot_resubmit_without_order_id PASSED         [ 75%]
tests/test_core.py::test_format_table_empty PASSED                       [ 83%]
tests/test_core.py::test_format_table_has_header_and_row PASSED          [ 91%]
tests/test_core.py::test_format_table_shows_unknown_for_missing_order_id PASSED [100%]

============================== 12 passed in 0.04s ==============================
```

Covers `tools/deadletter/core.py` (pure logic) only. `cli.py` (the actual Service Bus calls) has not been run against a live namespace. Full file: [`test-results/deadletter.txt`](test-results/deadletter.txt)

## Terraform

```
$ terraform fmt -check -recursive
(no output — all files already formatted)
```

`terraform validate` could not be run in this build environment (the Terraform provider registry was unreachable) — but it does run in CI on every push, against the real registry, and currently passes.

## What CI has actually confirmed, and what it hasn't

The first real CI run (after this repository was pushed to GitHub) caught two failures this build environment's sandbox couldn't: `pytest -q` failed in Python because the README's own documented command (bare `pytest`, not `python -m pytest`) doesn't add the current directory to the import path; and the C# Functions host failed to build, first for a missing namespace import, then for a malformed XML comment in its `.csproj`. Both are fixed and CI is green now (5/5 jobs). A closer manual review after that also found and fixed a real correctness issue CI's green checkmark didn't catch: `Order`'s C# properties were PascalCase while the wire format is camelCase, which would have silently deserialized every field to empty in production — System.Text.Json is case-sensitive by default, and the only place that was configured correctly was the test runner itself, which is why "15 tests pass" didn't reveal it.

The takeaway: a green CI run means the code compiles and the unit tests against pure logic pass. It does not mean any of this has been exercised against a real HTTP request, a real Service Bus message, or a real Cosmos DB write — that's a different, larger kind of verification this repository hasn't had yet.

## Cross-implementation agreement

All three implementations are tested against the same fixtures in `contracts/fixtures/`, so "17 tests pass in Python" and "17 tests pass in TypeScript" aren't just two unrelated numbers that happen to match — they're both checking the same `valid-order.json`, `invalid-total.json`, and `invalid-empty-items.json`, plus the same set of single-field mutations (see each language's test file for the exact list). The C# suite checks a subset of the same cases. If you change `contracts/order.schema.json` or add a fixture, update all three test files to keep that true.
