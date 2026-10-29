using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace OrderPipeline.Core;

/// <summary>Pure order rules. Must match python/order_pipeline/core.py and typescript/src/core.ts.</summary>
public static class OrderRules
{
    public const double TotalTolerance = 0.01;
    public const int MaxPaymentAttempts = 3;
    /// <summary>Simulated payment policy: totals above this are declined.</summary>
    public const double PaymentLimit = 10_000.0;

    private static readonly Regex CurrencyPattern = new("^[A-Z]{3}$", RegexOptions.CultureInvariant);

    public static class Status
    {
        public const string Received = "received";
        public const string Validated = "validated";
        public const string Rejected = "rejected";
        public const string Paid = "paid";
        public const string PaymentFailed = "payment_failed";
        public const string Fulfilled = "fulfilled";
        public const string DeadLettered = "dead_lettered";
    }

    private static readonly Dictionary<string, HashSet<string>> Transitions = new()
    {
        [Status.Received] = new() { Status.Validated, Status.Rejected },
        [Status.Validated] = new() { Status.Paid, Status.PaymentFailed },
        [Status.PaymentFailed] = new() { Status.Paid, Status.DeadLettered },
        [Status.Paid] = new() { Status.Fulfilled },
    };

    public static bool CanTransition(string current, string target) =>
        Transitions.TryGetValue(current, out var allowed) && allowed.Contains(target);

    public static string Transition(string current, string target)
    {
        if (!CanTransition(current, target))
        {
            throw new InvalidTransitionException($"Cannot move order from '{current}' to '{target}'");
        }
        return target;
    }

    public static double ComputeTotal(IEnumerable<OrderItem> items) =>
        Math.Round(items.Sum(i => i.Quantity * i.UnitPrice), 2, MidpointRounding.AwayFromZero);

    /// <summary>Returns human-readable errors. An empty list means the order is valid.</summary>
    public static IReadOnlyList<string> Validate(Order? order)
    {
        if (order is null)
        {
            return new[] { "order must be an object" };
        }

        var errors = new List<string>();

        if (string.IsNullOrWhiteSpace(order.OrderId)) errors.Add("orderId is required");
        if (string.IsNullOrWhiteSpace(order.CustomerId)) errors.Add("customerId is required");

        var itemsOk = order.Items is { Count: > 0 };
        if (!itemsOk)
        {
            errors.Add("items must be a non-empty list");
        }
        else
        {
            for (var i = 0; i < order.Items!.Count; i++)
            {
                var item = order.Items[i];
                if (item is null)
                {
                    errors.Add($"items[{i}] must be an object");
                    itemsOk = false;
                    continue;
                }
                if (string.IsNullOrWhiteSpace(item.Sku))
                {
                    errors.Add($"items[{i}].sku is required");
                    itemsOk = false;
                }
                if (item.Quantity < 1)
                {
                    errors.Add($"items[{i}].quantity must be an integer >= 1");
                    itemsOk = false;
                }
                if (item.UnitPrice < 0)
                {
                    errors.Add($"items[{i}].unitPrice must be a number >= 0");
                    itemsOk = false;
                }
            }
        }

        if (order.Currency is null || !CurrencyPattern.IsMatch(order.Currency))
        {
            errors.Add("currency must be a 3-letter uppercase code");
        }

        if (order.Total < 0)
        {
            errors.Add("total must be a number >= 0");
        }
        else if (itemsOk)
        {
            var expected = ComputeTotal(order.Items!);
            if (Math.Abs(order.Total - expected) > TotalTolerance)
            {
                errors.Add($"total {order.Total} does not match items sum {expected}");
            }
        }

        return errors;
    }

    public static bool AuthorizePayment(Order order) => order.Total <= PaymentLimit;

    /// <summary>deliveryCount is 1 on the first attempt.</summary>
    public static bool ShouldRetryPayment(int deliveryCount) => deliveryCount < MaxPaymentAttempts;
}

public sealed class InvalidTransitionException(string message) : Exception(message);

// Explicit JsonPropertyName on every property: the wire format (contracts/order.schema.json
// and every fixture) is camelCase, System.Text.Json is case-sensitive by default, and relying
// on a host-level PropertyNameCaseInsensitive setting would make this model's correctness
// depend on configuration that lives somewhere else. OrderPipeline.Tests also sets
// PropertyNameCaseInsensitive=true when loading fixtures directly, which still works fine
// alongside these attributes -- explicit attributes always take precedence.
public sealed class OrderItem
{
    [JsonPropertyName("sku")]
    public string Sku { get; set; } = "";

    [JsonPropertyName("quantity")]
    public int Quantity { get; set; }

    [JsonPropertyName("unitPrice")]
    public double UnitPrice { get; set; }
}

public sealed class Order
{
    [JsonPropertyName("orderId")]
    public string OrderId { get; set; } = "";

    [JsonPropertyName("customerId")]
    public string CustomerId { get; set; } = "";

    [JsonPropertyName("items")]
    public List<OrderItem>? Items { get; set; }

    [JsonPropertyName("total")]
    public double Total { get; set; }

    [JsonPropertyName("currency")]
    public string? Currency { get; set; }
}
