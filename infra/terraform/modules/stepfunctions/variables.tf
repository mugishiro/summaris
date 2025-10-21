variable "name" {
  description = "Name of the Step Functions state machine."
  type        = string
}

variable "role_arn" {
  description = "IAM role ARN assumed by the state machine."
  type        = string
}

variable "definition" {
  description = "JSON definition for the state machine."
  type        = string
}

variable "state_machine_type" {
  description = "Type of the state machine (STANDARD or EXPRESS)."
  type        = string
  default     = "STANDARD"

  validation {
    condition     = contains(["STANDARD", "EXPRESS"], upper(var.state_machine_type))
    error_message = "state_machine_type must be STANDARD or EXPRESS."
  }
}

variable "logging_configuration" {
  description = "Optional logging configuration for the state machine."
  type = object({
    level                  = string
    include_execution_data = bool
    log_destination_arn    = string
  })
  default = null

  validation {
    condition     = var.logging_configuration == null || contains(["ALL", "ERROR", "FATAL", "OFF"], upper(var.logging_configuration.level))
    error_message = "logging_configuration.level must be one of ALL, ERROR, FATAL, or OFF."
  }
}

variable "tracing_enabled" {
  description = "Whether to enable X-Ray tracing."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Resource tags to apply."
  type        = map(string)
  default     = {}
}
