variable "table_name" {
  description = "Name of the DynamoDB table."
  type        = string
}

variable "billing_mode" {
  description = "Billing mode for DynamoDB table (e.g. PAY_PER_REQUEST)."
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "hash_key" {
  description = "Partition key attribute name."
  type        = string
}

variable "range_key" {
  description = "Sort key attribute name (optional)."
  type        = string
  default     = null
}

variable "attributes" {
  description = "List of attribute definitions for the table."
  type = list(object({
    name = string
    type = string
  }))
}

variable "point_in_time_recovery_enabled" {
  description = "Whether to enable point-in-time recovery."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Resource tags to apply to the table."
  type        = map(string)
  default     = {}
}

variable "ttl_attribute" {
  description = "Optional TTL attribute name to enable time-to-live on the table."
  type        = string
  default     = null
}
