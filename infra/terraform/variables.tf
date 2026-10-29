variable "project" {
  description = "Short project name used in resource names (lowercase letters and digits only)."
  type        = string
  default     = "orderpipe"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.project))
    error_message = "project must be 3-12 lowercase letters or digits."
  }
}

variable "environment" {
  description = "Deployment environment name, e.g. dev, test, prod."
  type        = string
  default     = "dev"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "southafricanorth"
}

variable "runtime" {
  description = "Which implementation to deploy to the Function App."
  type        = string
  default     = "python"

  validation {
    condition     = contains(["python", "node", "dotnet"], var.runtime)
    error_message = "runtime must be one of: python, node, dotnet."
  }
}

variable "name_suffix" {
  description = "Suffix that makes globally unique names (storage account, Cosmos account, Function App) unique."
  type        = string
}

variable "dead_letter_max_delivery_count" {
  description = "Deliveries before Service Bus moves a message to the dead-letter queue."
  type        = number
  default     = 5
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
