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

public sealed class OrderState
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    public string OrderId { get; set; } = "";
    public string CustomerId { get; set; } = "";
    public string Status { get; set; } = "";
    public string? Reason { get; set; }
    public string UpdatedAt { get; set; } = "";
}
