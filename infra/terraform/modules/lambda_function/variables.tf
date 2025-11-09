variable "function_name" {
  description = "Lambda function name"
  type        = string
}

variable "role_arn" {
  description = "IAM role ARN for Lambda"
  type        = string
}

variable "handler" {
  description = "Lambda handler"
  type        = string
  default     = "handler.lambda_handler"
}

variable "runtime" {
  description = "Runtime identifier"
  type        = string
  default     = "python3.11"
}

variable "filename" {
  description = "Path to deployment package"
  type        = string
}

variable "source_code_hash" {
  description = "Base64-encoded hash of deployment package"
  type        = string
  default     = null
}

variable "timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 60
}

variable "memory_size" {
  description = "Memory size in MB"
  type        = number
  default     = 128
}

variable "environment" {
  description = "Environment variables for function"
  type        = map(string)
  default     = {}
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}
