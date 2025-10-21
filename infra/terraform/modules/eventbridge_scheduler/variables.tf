variable "environment" {
  description = "Deployment environment (use dev)."
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project identifier used in resource names."
  type        = string
}

variable "state_machine_arn" {
  description = "Target Step Functions state machine ARN."
  type        = string
}

variable "sources" {
  description = "List of source schedules."
  type = list(object({
    id                  = string
    name                = string
    schedule_expression = string
    timezone            = optional(string)
    description         = optional(string)
    endpoint = optional(object({
      url = string
    }))
    settings = optional(object({
      threshold_seconds = optional(number)
      force_fetch       = optional(bool)
    }))
  }))
  default = []
}

variable "tags" {
  description = "Base tags to apply to resources."
  type        = map(string)
  default     = {}
}
