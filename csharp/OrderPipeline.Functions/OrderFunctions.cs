using System.Net;
using Azure.Messaging.ServiceBus;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Azure.Functions.Worker.Http;
using Microsoft.Extensions.Logging;
using OrderPipeline.Core;

namespace OrderPipeline.Functions;

/// <summary>Triggers for the order pipeline. UNVERIFIED.</summary>
public sealed class OrderFunctions(OrderStore store, ILogger<OrderFunctions> log)
{
    [Function("Intake")]
    public async Task<HttpResponseData> Intake(
        [HttpTrigger(AuthorizationLevel.Function, "post", Route = "orders")] HttpRequestData req)
    {
        Order? order;
        try
        {
            order = await req.ReadFromJsonAsync<Order>();
        }
        catch (System.Text.Json.JsonException)
        {
            return await Respond(req, HttpStatusCode.BadRequest, "Body must be JSON");
        }

        if (order is null || string.IsNullOrWhiteSpace(order.OrderId))
        {
            return await Respond(req, HttpStatusCode.BadRequest, "orderId is required");
        }

        await store.SaveAsync(order.OrderId, order.CustomerId, OrderRules.Status.Received);
        await store.SendAsync("orders", order);

        var response = req.CreateResponse(HttpStatusCode.Accepted);
        await response.WriteAsJsonAsync(new { orderId = order.OrderId, status = OrderRules.Status.Received });
        return response;
    }

    [Function("Validation")]
    public async Task Validation(
        [ServiceBusTrigger("orders", "validation", Connection = "ServiceBusConnection")] ServiceBusReceivedMessage message)
    {
        var order = message.Body.ToObjectFromJson<Order>();

        // A malformed message with no orderId can't be tracked in Cosmos, so it
        // is logged and dropped (not retried) rather than throwing, which would
        // make Service Bus redeliver it forever.
        if (order is null || string.IsNullOrWhiteSpace(order.OrderId))
        {
            log.LogError("dropping order message with no orderId: errors={Errors}", string.Join("; ", OrderRules.Validate(order)));
            return;
        }

        var errors = OrderRules.Validate(order);
        if (errors.Count > 0)
        {
            log.LogInformation("order {OrderId} rejected: {Errors}", order.OrderId, string.Join("; ", errors));
            await store.MoveAsync(order, OrderRules.Status.Rejected, string.Join("; ", errors));
            return;
        }

        await store.MoveAsync(order, OrderRules.Status.Validated);
        await store.SendAsync("payments", order);
    }

    [Function("Payment")]
    public async Task Payment(
        [ServiceBusTrigger("payments", "payment", Connection = "ServiceBusConnection")] ServiceBusReceivedMessage message)
    {
        var order = message.Body.ToObjectFromJson<Order>()!;
        if (OrderRules.AuthorizePayment(order))
        {
            await store.MoveAsync(order, OrderRules.Status.Paid);
            await store.SendAsync("fulfilment", order);
            return;
        }

        if (OrderRules.ShouldRetryPayment(message.DeliveryCount))
        {
            await store.MoveAsync(order, OrderRules.Status.PaymentFailed, "declined");
            // Throwing makes Service Bus redeliver the message for another attempt.
            throw new InvalidOperationException($"payment declined for {order.OrderId}; retrying");
        }

        await store.MoveAsync(order, OrderRules.Status.DeadLettered, "payment declined after retries");
        log.LogWarning("order {OrderId} dead-lettered after payment retries", order.OrderId);
    }

    [Function("Fulfilment")]
    public async Task Fulfilment(
        [ServiceBusTrigger("fulfilment", "fulfilment", Connection = "ServiceBusConnection")] ServiceBusReceivedMessage message)
    {
        await store.MoveAsync(message.Body.ToObjectFromJson<Order>()!, OrderRules.Status.Fulfilled);
    }

    private static async Task<HttpResponseData> Respond(HttpRequestData req, HttpStatusCode code, string text)
    {
        var response = req.CreateResponse(code);
        await response.WriteStringAsync(text);
        return response;
    }
}
