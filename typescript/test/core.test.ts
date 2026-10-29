import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  authorizePayment,
  canTransition,
  computeTotal,
  InvalidTransitionError,
  shouldRetryPayment,
  Status,
  transition,
  validateOrder,
} from "../src/core";

// Fixtures live at the repo root so every implementation reads the same inputs.
const FIXTURES = join(__dirname, "..", "..", "..", "contracts", "fixtures"); // dist/test -> repo root
const load = (name: string) => JSON.parse(readFileSync(join(FIXTURES, name), "utf-8"));

test("valid fixture has no errors", () => {
  assert.deepEqual(validateOrder(load("valid-order.json")), []);
});

test("total mismatch is reported", () => {
  const errors = validateOrder(load("invalid-total.json"));
  assert.ok(errors.some((e) => e.includes("does not match")));
});

test("empty items is reported", () => {
  assert.ok(validateOrder(load("invalid-empty-items.json")).includes("items must be a non-empty list"));
});

const cases: Array<[string, (o: any) => void, string]> = [
  ["orderId required", (o) => (o.orderId = ""), "orderId is required"],
  ["customerId required", (o) => (o.customerId = "  "), "customerId is required"],
  ["currency format", (o) => (o.currency = "zar"), "currency must be a 3-letter uppercase code"],
  ["total type", (o) => (o.total = "10"), "total must be a number >= 0"],
  ["quantity >= 1", (o) => (o.items[0].quantity = 0), "items[0].quantity must be an integer >= 1"],
  ["quantity not bool", (o) => (o.items[0].quantity = true), "items[0].quantity must be an integer >= 1"],
  ["unitPrice >= 0", (o) => (o.items[0].unitPrice = -1), "items[0].unitPrice must be a number >= 0"],
  ["sku required", (o) => delete o.items[0].sku, "items[0].sku is required"],
];

for (const [name, mutate, expected] of cases) {
  test(`field error: ${name}`, () => {
    const order = load("valid-order.json");
    mutate(order);
    assert.ok(validateOrder(order).includes(expected), `expected "${expected}"`);
  });
}

test("non-object order rejected", () => {
  assert.deepEqual(validateOrder(["x"]), ["order must be an object"]);
});

test("computeTotal rounds to cents", () => {
  assert.equal(computeTotal([{ sku: "a", quantity: 3, unitPrice: 0.1 }]), 0.3);
});

test("valid transitions", () => {
  assert.equal(transition(Status.Received, Status.Validated), Status.Validated);
  assert.equal(transition(Status.PaymentFailed, Status.Paid), Status.Paid);
  assert.equal(transition(Status.Paid, Status.Fulfilled), Status.Fulfilled);
  assert.ok(canTransition(Status.Validated, Status.PaymentFailed));
});

test("invalid transition throws", () => {
  assert.throws(() => transition(Status.Fulfilled, Status.Paid), InvalidTransitionError);
});

test("payment policy", () => {
  assert.equal(authorizePayment({ total: 100 }), true);
  assert.equal(authorizePayment({ total: 20_000 }), false);
});

test("retry budget", () => {
  assert.equal(shouldRetryPayment(1), true);
  assert.equal(shouldRetryPayment(2), true);
  assert.equal(shouldRetryPayment(3), false);
});
