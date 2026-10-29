output "function_app_name" {
  description = "Name of the Function App to deploy code to."
  value       = azurerm_linux_function_app.this.name
}

output "intake_hostname" {
  description = "Hostname of the HTTP intake endpoint (POST /api/orders)."
  value       = azurerm_linux_function_app.this.default_hostname
}

output "servicebus_namespace" {
  description = "Service Bus namespace (identity-based access, no connection strings)."
  value       = "${azurerm_servicebus_namespace.this.name}.servicebus.windows.net"
}

output "cosmos_endpoint" {
  description = "Cosmos DB endpoint (identity-based access)."
  value       = azurerm_cosmosdb_account.this.endpoint
}
