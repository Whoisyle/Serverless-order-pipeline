using System.Text.Json;
using OrderPipeline.Core;

// Dependency-free test runner: no NuGet packages, so it builds offline.
// Exit code is non-zero if any test fails.

var failures = new List<string>();
var passed = 0;

void Test(string name, Action body)
{
    try
    {
        body();
        passed++;
    }
    catch (Exception ex)
    {
        failures.Add($"{name}: {ex.Message}");
    }
}

static void Assert(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static void AssertEqual<T>(T expected, T actual)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual))
    {
        throw new InvalidOperationException($"expected '{expected}' but was '{actual}'");
    }
}

static string FixturesDir()
{
    var dir = new DirectoryInfo(AppContext.BaseDirectory);
    while (dir is not null && !Directory.Exists(Path.Combine(dir.FullName, "contracts", "fixtures")))
    {
        dir = dir.Parent;
    }
    return dir is null
        ? throw new DirectoryNotFoundException("contracts/fixtures not found above the test binary")
        : Path.Combine(dir.FullName, "contracts", "fixtures");
}

static Order Load(string name)
{
    var json = File.ReadAllText(Path.Combine(FixturesDir(), name));
    return JsonSerializer.Deserialize<Order>(json, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })!;
}

Test("valid fixture has no errors", () =>
    AssertEqual(0, OrderRules.Validate(Load("valid-order.json")).Count));

Test("total mismatch is reported", () =>
    Assert(OrderRules.Validate(Load("invalid-total.json")).Any(e => e.Contains("does not match")), "expected mismatch error"));

Test("empty items is reported", () =>
    Assert(OrderRules.Validate(Load("invalid-empty-items.json")).Contains("items must be a non-empty list"), "expected empty items error"));

void FieldError(string name, Action<Order> mutate, string expected) =>
    Test($"field error: {name}", () =>
    {
        var order = Load("valid-order.json");
        mutate(order);
        Assert(OrderRules.Validate(order).Contains(expected), $"expected '{expected}'");
    });

FieldError("orderId required", o => o.OrderId = "", "orderId is required");
FieldError("customerId required", o => o.CustomerId = "  ", "customerId is required");
FieldError("currency format", o => o.Currency = "zar", "currency must be a 3-letter uppercase code");
FieldError("quantity >= 1", o => o.Items![0].Quantity = 0, "items[0].quantity must be an integer >= 1");
FieldError("unitPrice >= 0", o => o.Items![0].UnitPrice = -1, "items[0].unitPrice must be a number >= 0");
FieldError("sku required", o => o.Items![0].Sku = "", "items[0].sku is required");

Test("null order rejected", () =>
    AssertEqual("order must be an object", OrderRules.Validate(null).Single()));

Test("ComputeTotal rounds to cents", () =>
    AssertEqual(0.3, OrderRules.ComputeTotal(new[] { new OrderItem { Sku = "a", Quantity = 3, UnitPrice = 0.1 } })));

Test("valid transitions", () =>
{
    AssertEqual(OrderRules.Status.Validated, OrderRules.Transition(OrderRules.Status.Received, OrderRules.Status.Validated));
    AssertEqual(OrderRules.Status.Paid, OrderRules.Transition(OrderRules.Status.PaymentFailed, OrderRules.Status.Paid));
    AssertEqual(OrderRules.Status.Fulfilled, OrderRules.Transition(OrderRules.Status.Paid, OrderRules.Status.Fulfilled));
});

Test("invalid transition throws", () =>
{
    try
    {
        OrderRules.Transition(OrderRules.Status.Fulfilled, OrderRules.Status.Paid);
        throw new InvalidOperationException("expected InvalidTransitionException");
    }
    catch (InvalidTransitionException)
    {
    }
});

Test("payment policy", () =>
{
    Assert(OrderRules.AuthorizePayment(new Order { Total = 100 }), "100 should be authorized");
    Assert(!OrderRules.AuthorizePayment(new Order { Total = 20_000 }), "20000 should be declined");
});

Test("retry budget", () =>
{
    Assert(OrderRules.ShouldRetryPayment(1), "attempt 1 should retry");
    Assert(OrderRules.ShouldRetryPayment(2), "attempt 2 should retry");
    Assert(!OrderRules.ShouldRetryPayment(3), "attempt 3 should not retry");
});

Console.WriteLine($"{passed} passed, {failures.Count} failed");
foreach (var failure in failures)
{
    Console.Error.WriteLine($"FAIL {failure}");
}
return failures.Count == 0 ? 0 : 1;
