using System.Text.Json.Serialization;
using Azure.Messaging.ServiceBus;
using Microsoft.Azure.Cosmos;
using OrderPipeline.Core;

namespace OrderPipeline.Functions;

/// <summary>Order state in Cosmos DB plus publishing to Service Bus topics. UNVERIFIED.</summary>
public sealed class OrderStore(ServiceBusClient bus, CosmosClient cosmos)
{
    private Container Orders =>
        cosmos.GetContainer(Environment.GetEnvironmentVariable("COSMOS_DATABASE") ?? "orders", "orders");

    public async Task SaveAsync(string orderId, string customerId, string status, string? reason = null)
    {
        var doc = new OrderState
        {
            Id = orderId,
            OrderId = orderId,
            CustomerId = customerId,
            Status = status,
            Reason = reason,
            UpdatedAt = DateTimeOffset.UtcNow.ToString("O"),
        };
        await Orders.UpsertItemAsync(doc, new PartitionKey(orderId));
    }

    /// <summary>Advance an order to a new status, refusing illegal transitions.</summary>
    public async Task MoveAsync(Order order, string target, string? reason = null)
    {
        var current = OrderRules.Status.Received;
        try
        {
            var existing = await Orders.ReadItemAsync<OrderState>(order.OrderId, new PartitionKey(order.OrderId));
            current = existing.Resource.Status;
        }
        catch (CosmosException ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            // First write for this order.
        }

        if (current != target)
        {
            OrderRules.Transition(current, target);
        }
        await SaveAsync(order.OrderId, order.CustomerId, target, reason);
    }

    public async Task SendAsync(string topic, Order order)
    {
        var sender = bus.CreateSender(topic);
        await sender.SendMessageAsync(new ServiceBusMessage(BinaryData.FromObjectAsJson(order)));
        await sender.DisposeAsync();
    }
}

// Both System.Text.Json's [JsonPropertyName] and Newtonsoft.Json's [JsonProperty] are
// applied to every property. The Microsoft.Azure.Cosmos SDK's default serializer wraps
// Newtonsoft.Json internally, not System.Text.Json, so a System.Text.Json-only attribute
// could be silently ignored depending on which serializer is actually in effect -- this
// could not be confirmed without compiling against the real SDK. Covering both is correct
// regardless of which one Cosmos uses, and keeps this document's field names camelCase,
// matching Python's and TypeScript's plain dict/object writes to the same container shape
// (see docs/architecture.md's Known gaps for why this matters only if `runtime` is
// switched against existing data).
public sealed class OrderState
{
    [JsonPropertyName("id")]
    [Newtonsoft.Json.JsonProperty("id")]
    public string Id { get; set; } = "";

    [JsonPropertyName("orderId")]
    [Newtonsoft.Json.JsonProperty("orderId")]
    public string OrderId { get; set; } = "";

    [JsonPropertyName("customerId")]
    [Newtonsoft.Json.JsonProperty("customerId")]
    public string CustomerId { get; set; } = "";

    [JsonPropertyName("status")]
    [Newtonsoft.Json.JsonProperty("status")]
    public string Status { get; set; } = "";

    [JsonPropertyName("reason")]
    [Newtonsoft.Json.JsonProperty("reason")]
    public string? Reason { get; set; }

    [JsonPropertyName("updatedAt")]
    [Newtonsoft.Json.JsonProperty("updatedAt")]
    public string UpdatedAt { get; set; } = "";
}
