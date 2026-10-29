locals {
  base = "${var.project}-${var.environment}"
  # Storage account names: 3-24 lowercase letters/digits, globally unique.
  storage_name = substr(replace("st${var.project}${var.environment}${var.name_suffix}", "-", ""), 0, 24)
  tags         = merge({ project = var.project, environment = var.environment, workload = "order-pipeline" }, var.tags)

  topics = {
    orders     = { subscription = "validation" }
    payments   = { subscription = "payment" }
    fulfilment = { subscription = "fulfilment" }
  }
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.base}"
  location = var.location
  tags     = local.tags
}

# ---------- Messaging: Service Bus topics, subscriptions, dead-lettering ----------

resource "azurerm_servicebus_namespace" "this" {
  name                = "sb-${local.base}-${var.name_suffix}"
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Standard"
  local_auth_enabled  = false
  tags                = local.tags
}

resource "azurerm_servicebus_topic" "this" {
  for_each     = local.topics
  name         = each.key
  namespace_id = azurerm_servicebus_namespace.this.id
}

resource "azurerm_servicebus_subscription" "this" {
  for_each                             = local.topics
  name                                 = each.value.subscription
  topic_id                             = azurerm_servicebus_topic.this[each.key].id
  max_delivery_count                   = var.dead_letter_max_delivery_count
  dead_lettering_on_message_expiration = true
  requires_session                     = false
}

# ---------- State: Cosmos DB (serverless, Entra ID only) ----------

resource "azurerm_cosmosdb_account" "this" {
  name                          = "cosmos-${local.base}-${var.name_suffix}"
  location                      = azurerm_resource_group.this.location
  resource_group_name           = azurerm_resource_group.this.name
  offer_type                    = "Standard"
  kind                          = "GlobalDocumentDB"
  local_authentication_disabled = true

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.this.location
    failover_priority = 0
  }

  capabilities {
    name = "EnableServerless"
  }

  tags = local.tags
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = "orders"
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
}

resource "azurerm_cosmosdb_sql_container" "orders" {
  name                = "orders"
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
  database_name       = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths = ["/orderId"]
}

# ---------- Compute: Function App (Linux, consumption) with managed identity ----------

resource "azurerm_storage_account" "functions" {
  name                      = local.storage_name
  resource_group_name       = azurerm_resource_group.this.name
  location                  = azurerm_resource_group.this.location
  account_tier              = "Standard"
  account_replication_type  = "LRS"
  min_tls_version           = "TLS1_2"
  shared_access_key_enabled = false
  tags                      = local.tags
}

resource "azurerm_service_plan" "this" {
  name                = "plan-${local.base}"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  os_type             = "Linux"
  sku_name            = "Y1"
  tags                = local.tags
}

resource "azurerm_linux_function_app" "this" {
  name                          = "func-${local.base}-${var.name_suffix}"
  resource_group_name           = azurerm_resource_group.this.name
  location                      = azurerm_resource_group.this.location
  service_plan_id               = azurerm_service_plan.this.id
  storage_account_name          = azurerm_storage_account.functions.name
  storage_uses_managed_identity = true
  https_only                    = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    minimum_tls_version = "1.2"
    ftps_state          = "Disabled"

    application_stack {
      python_version              = var.runtime == "python" ? "3.11" : null
      node_version                = var.runtime == "node" ? "20" : null
      dotnet_version              = var.runtime == "dotnet" ? "8.0" : null
      use_dotnet_isolated_runtime = var.runtime == "dotnet" ? true : null
    }
  }

  app_settings = {
    "ServiceBusConnection__fullyQualifiedNamespace" = "${azurerm_servicebus_namespace.this.name}.servicebus.windows.net"
    "COSMOS_ENDPOINT"                               = azurerm_cosmosdb_account.this.endpoint
    "COSMOS_DATABASE"                               = azurerm_cosmosdb_sql_database.this.name
    "AzureWebJobsStorage__accountName"              = azurerm_storage_account.functions.name
  }

  tags = local.tags
}

# ---------- Access: least-privilege, identity-based, no keys ----------

resource "azurerm_role_assignment" "sb_sender" {
  scope                = azurerm_servicebus_namespace.this.id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_linux_function_app.this.identity[0].principal_id
}

resource "azurerm_role_assignment" "sb_receiver" {
  scope                = azurerm_servicebus_namespace.this.id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_linux_function_app.this.identity[0].principal_id
}

resource "azurerm_role_assignment" "functions_storage" {
  scope                = azurerm_storage_account.functions.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_linux_function_app.this.identity[0].principal_id
}

# Built-in "Cosmos DB Built-in Data Contributor" role.
resource "azurerm_cosmosdb_sql_role_assignment" "functions_data" {
  resource_group_name = azurerm_resource_group.this.name
  account_name        = azurerm_cosmosdb_account.this.name
  role_definition_id  = "${azurerm_cosmosdb_account.this.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_linux_function_app.this.identity[0].principal_id
  scope               = azurerm_cosmosdb_account.this.id
}
