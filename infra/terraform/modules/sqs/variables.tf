variable "queue_name" {
  description = "Name of the primary SQS queue."
  type        = string
}

variable "fifo_queue" {
  description = "Whether the queue is FIFO."
  type        = bool
  default     = false
}

variable "content_based_deduplication" {
  description = "Enable content-based deduplication for FIFO queues."
  type        = bool
  default     = true
}

variable "delay_seconds" {
  description = "Number of seconds to delay delivery of all messages in the queue."
  type        = number
  default     = 0
}

variable "max_message_size" {
  description = "The limit of how many bytes a message can contain before Amazon SQS rejects it."
  type        = number
  default     = 262144
}

variable "message_retention_seconds" {
  description = "The number of seconds Amazon SQS retains a message."
  type        = number
  default     = 345600
}

variable "receive_wait_time_seconds" {
  description = "The time for which a ReceiveMessage call waits for a message to arrive."
  type        = number
  default     = 0
}

variable "visibility_timeout_seconds" {
  description = "The visibility timeout for the queue."
  type        = number
  default     = 30
}

variable "kms_master_key_id" {
  description = "KMS master key ID for SSE."
  type        = string
  default     = null
}

variable "kms_data_key_reuse_period_seconds" {
  description = "KMS data key reuse period in seconds."
  type        = number
  default     = null
}

variable "dlq_enabled" {
  description = "Whether to create and attach a dead-letter queue."
  type        = bool
  default     = false
}

variable "dlq_queue_name" {
  description = "Optional override name for the DLQ."
  type        = string
  default     = ""
}

variable "dlq_max_receive_count" {
  description = "Maximum receives before moving message to DLQ."
  type        = number
  default     = 5
}

variable "dlq_message_retention_seconds" {
  description = "Retention period for DLQ messages."
  type        = number
  default     = 1209600
}

variable "tags" {
  description = "Resource tags."
  type        = map(string)
  default     = {}
}
