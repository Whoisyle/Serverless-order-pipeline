/**
 * Azure Functions (Node.js v4 model) for the order pipeline.
 * Flow: HTTP intake -> topic "orders" -> validation -> topic "payments" -> payment
 * -> topic "fulfilment" -> fulfilment. Order state lives in Cosmos DB.
 */
import { app, HttpRequest, HttpResponseInit, InvocationContext } from "@azure/functions";
import { CosmosClient, Container } from "@azure/cosmos";
import { DefaultAzureCredential } from "@azure/identity";
import { ServiceBusClient } from "@azure/service-bus";
import {
  authorizePayment,
  Order,
  Status,
  shouldRetryPayment,
  transition,
  validateOrder,
} from "./core";

const credential = new DefaultAzureCredential();
let serviceBus: ServiceBusClient | undefined;
let orders: Container | undefined;

function bus(): ServiceBusClient {
  serviceBus ??= new ServiceBusClient(
    process.env["ServiceBusConnection__fullyQualifiedNamespace"]!,
    credential,
  );
  return serviceBus;
}

function ordersContainer(): Container {
  orders ??= new CosmosClient({
    endpoint: process.env["COSMOS_ENDPOINT"]!,
    aadCredentials: credential,
  })
    .database(process.env["COSMOS_DATABASE"] ?? "orders")
    .container("orders");
  return orders;
}

async function send(topic: string, payload: unknown): Promise<void> {
  const sender = bus().createSender(topic);
  try {
    await sender.sendMessages({ body: payload });
  } finally {
    await sender.close();
  }
}

async function save(order: Pick<Order, "orderId" | "customerId">, status: string, reason?: string): Promise<void> {
  await ordersContainer().items.upsert({
    id: order.orderId,
    orderId: order.orderId,
    customerId: order.customerId,
    status,
    reason: reason ?? null,
    updatedAt: new Date().toISOString(),
  });
}

/** Advance an order to a new status, refusing illegal transitions. */
async function move(order: Pick<Order, "orderId" | "customerId">, target: string, reason?: string): Promise<void> {
  let current: string = Status.Received;
  try {
    const { resource } = await ordersContainer().item(order.orderId, order.orderId).read();
    if (resource?.status) current = resource.status;
  } catch {
    // First write for this order: treat as received.
  }
  if (current !== target) transition(current, target);
  await save(order, target, reason);
}

app.http("intake", {
  methods: ["POST"],
  authLevel: "function",
  route: "orders",
  handler: async (request: HttpRequest): Promise<HttpResponseInit> => {
    let order: Partial<Order>;
    try {
      order = (await request.json()) as Partial<Order>;
    } catch {
      return { status: 400, body: "Body must be JSON" };
    }
    if (!order || !order.orderId) {
      return { status: 400, body: "orderId is required" };
    }
    await save({ orderId: order.orderId, customerId: order.customerId ?? "" }, Status.Received);
    await send("orders", order);
    return { status: 202, jsonBody: { orderId: order.orderId, status: Status.Received } };
  },
});

app.serviceBusTopic("validation", {
  topicName: "orders",
  subscriptionName: "validation",
  connection: "ServiceBusConnection",
  handler: async (message: unknown, context: InvocationContext): Promise<void> => {
    const order = message as Partial<Order>;
    const errors = validateOrder(order);

    // A malformed message with no orderId can't be tracked in Cosmos, so it is
    // logged and dropped (not retried) rather than throwing, which would make
    // Service Bus redeliver it forever.
    if (!order?.orderId) {
      context.error(`dropping order message with no orderId: errors=${errors.join("; ")}`);
      return;
    }

    if (errors.length > 0) {
      context.log(`order ${order.orderId} rejected: ${errors.join("; ")}`);
      await move(order as Order, Status.Rejected, errors.join("; "));
      return;
    }
    await move(order as Order, Status.Validated);
    await send("payments", order);
  },
});

app.serviceBusTopic("payment", {
  topicName: "payments",
  subscriptionName: "payment",
  connection: "ServiceBusConnection",
  handler: async (message: unknown, context: InvocationContext): Promise<void> => {
    const order = message as Order;
    if (authorizePayment(order)) {
      await move(order, Status.Paid);
      await send("fulfilment", order);
      return;
    }
    const deliveryCount = context.triggerMetadata?.deliveryCount as number | undefined;
    if (shouldRetryPayment(deliveryCount ?? 1)) {
      await move(order, Status.PaymentFailed, "declined");
      // Throwing makes Service Bus redeliver the message for another attempt.
      throw new Error(`payment declined for ${order.orderId}; retrying`);
    }
    await move(order, Status.DeadLettered, "payment declined after retries");
    context.warn(`order ${order.orderId} dead-lettered after payment retries`);
  },
});

app.serviceBusTopic("fulfilment", {
  topicName: "fulfilment",
  subscriptionName: "fulfilment",
  connection: "ServiceBusConnection",
  handler: async (message: unknown): Promise<void> => {
    await move(message as Order, Status.Fulfilled);
  },
});
