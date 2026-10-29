using Azure.Identity;
using Azure.Messaging.ServiceBus;
using Microsoft.Azure.Cosmos;
using Microsoft.Azure.Functions.Worker;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

// UNVERIFIED (see OrderPipeline.Functions.csproj).
var host = new HostBuilder()
    .ConfigureFunctionsWorkerDefaults()
    .ConfigureServices(services =>
    {
        var credential = new DefaultAzureCredential();
        services.AddSingleton(_ => new ServiceBusClient(
            Environment.GetEnvironmentVariable("ServiceBusConnection__fullyQualifiedNamespace"), credential));
        services.AddSingleton(_ => new CosmosClient(
            Environment.GetEnvironmentVariable("COSMOS_ENDPOINT"), credential));
        services.AddSingleton<OrderStore>();
    })
    .Build();

host.Run();
