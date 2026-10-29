/**
 * Pure order rules: validation, totals, status transitions, and payment policy.
 * No cloud SDKs are imported here, so this module is unit-testable without Azure.
 * Must match python/order_pipeline/core.py and csharp/OrderPipeline/OrderRules.cs.
 */

export const CURRENCY_RE = /^[A-Z]{3}$/;
export const TOTAL_TOLERANCE = 0.01;
export const MAX_PAYMENT_ATTEMPTS = 3;
/** Simulated payment policy: totals above this are declined so failure paths can be exercised. */
export const PAYMENT_LIMIT = 10_000;

export const Status = {
  Received: "received",
  Validated: "validated",
  Rejected: "rejected",
  Paid: "paid",
  PaymentFailed: "payment_failed",
  Fulfilled: "fulfilled",
  DeadLettered: "dead_lettered",
} as const;
export type OrderStatus = (typeof Status)[keyof typeof Status];

const TRANSITIONS: Record<string, ReadonlySet<string>> = {
  [Status.Received]: new Set([Status.Validated, Status.Rejected]),
  [Status.Validated]: new Set([Status.Paid, Status.PaymentFailed]),
  [Status.PaymentFailed]: new Set([Status.Paid, Status.DeadLettered]),
  [Status.Paid]: new Set([Status.Fulfilled]),
};

export class InvalidTransitionError extends Error {}

export interface OrderItem {
  sku: string;
  quantity: number;
  unitPrice: number;
}

export interface Order {
  orderId: string;
  customerId: string;
  items: OrderItem[];
  total: number;
  currency: string;
}

export function canTransition(current: string, target: string): boolean {
  return TRANSITIONS[current]?.has(target) ?? false;
}

export function transition(current: string, target: string): string {
  if (!canTransition(current, target)) {
    throw new InvalidTransitionError(`Cannot move order from '${current}' to '${target}'`);
  }
  return target;
}

const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);
const isNumber = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const nonEmpty = (v: unknown): v is string => typeof v === "string" && v.trim() !== "";

export function computeTotal(items: OrderItem[]): number {
  const sum = items.reduce((acc, item) => acc + item.quantity * item.unitPrice, 0);
  return Math.round(sum * 100) / 100;
}

/** Returns human-readable errors. An empty array means the order is valid. */
export function validateOrder(order: unknown): string[] {
  if (typeof order !== "object" || order === null || Array.isArray(order)) {
    return ["order must be an object"];
  }
  const o = order as Record<string, unknown>;
  const errors: string[] = [];

  if (!nonEmpty(o.orderId)) errors.push("orderId is required");
  if (!nonEmpty(o.customerId)) errors.push("customerId is required");

  let itemsOk = Array.isArray(o.items) && o.items.length > 0;
  if (!itemsOk) {
    errors.push("items must be a non-empty list");
  } else {
    (o.items as unknown[]).forEach((raw, i) => {
      if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
        errors.push(`items[${i}] must be an object`);
        itemsOk = false;
        return;
      }
      const item = raw as Record<string, unknown>;
      if (!nonEmpty(item.sku)) {
        errors.push(`items[${i}].sku is required`);
        itemsOk = false;
      }
      if (!isInt(item.quantity) || (item.quantity as number) < 1) {
        errors.push(`items[${i}].quantity must be an integer >= 1`);
        itemsOk = false;
      }
      if (!isNumber(item.unitPrice) || (item.unitPrice as number) < 0) {
        errors.push(`items[${i}].unitPrice must be a number >= 0`);
        itemsOk = false;
      }
    });
  }

  if (typeof o.currency !== "string" || !CURRENCY_RE.test(o.currency)) {
    errors.push("currency must be a 3-letter uppercase code");
  }

  if (!isNumber(o.total) || o.total < 0) {
    errors.push("total must be a number >= 0");
  } else if (itemsOk) {
    const expected = computeTotal(o.items as OrderItem[]);
    if (Math.abs(o.total - expected) > TOTAL_TOLERANCE) {
      errors.push(`total ${o.total} does not match items sum ${expected}`);
    }
  }

  return errors;
}

export function authorizePayment(order: Pick<Order, "total">): boolean {
  return order.total <= PAYMENT_LIMIT;
}

/** deliveryCount is 1 on the first attempt. */
export function shouldRetryPayment(deliveryCount: number): boolean {
  return deliveryCount < MAX_PAYMENT_ATTEMPTS;
}
