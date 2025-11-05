variable "environment" {
  description = "Deployment environment (dev only)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "aws_account_id" {
  description = "AWS account ID used in IAM ARNs"
  type        = string
}

variable "project_name" {
  description = "Project identifier used in naming"
  type        = string
  default     = "news"
}

variable "default_tags" {
  description = "Base tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "enable_lambda_deployment" {
  description = "Whether to deploy Lambda functions from local artifacts"
  type        = bool
  default     = false
}

variable "enable_raw_archive_lifecycle" {
  description = "Toggle lifecycle rule for raw archive bucket"
  type        = bool
  default     = true
}

variable "collector_package" {
  description = "Path to collector Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "preprocessor_package" {
  description = "Path to preprocessor Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "summarizer_package" {
  description = "Path to summarizer Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "diff_validator_package" {
  description = "Path to diff validator Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "postprocess_package" {
  description = "Path to postprocess Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "checker_package" {
  description = "Path to checker Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "dispatcher_package" {
  description = "Path to dispatcher Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "queue_worker_package" {
  description = "Path to queue worker Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "content_api_package" {
  description = "Path to content API Lambda zip (required if enable_lambda_deployment)"
  type        = string
  default     = null
}

variable "raw_archive_suffix" {
  description = "Optional fixed suffix for the raw archive bucket to avoid recreation"
  type        = string
  default     = null
}

variable "scheduler_sources" {
  description = "List of source schedules for EventBridge Scheduler."
  type = list(object({
    id                  = string
    name                = string
    schedule_expression = string
    timezone            = optional(string)
    description         = optional(string)
    endpoint = optional(object({
      url = string
    }))
  }))
  default = []
}

variable "collector_lambda_arn" {
  description = "Existing collector Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.collector_lambda_arn != ""
    error_message = "collector_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "preprocessor_lambda_arn" {
  description = "Existing preprocessor Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.preprocessor_lambda_arn != ""
    error_message = "preprocessor_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "summarizer_lambda_arn" {
  description = "Existing summarizer Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.summarizer_lambda_arn != ""
    error_message = "summarizer_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "diff_validator_lambda_arn" {
  description = "Existing diff validator Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.diff_validator_lambda_arn != ""
    error_message = "diff_validator_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "postprocess_lambda_arn" {
  description = "Existing postprocess Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.postprocess_lambda_arn != ""
    error_message = "postprocess_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "checker_lambda_arn" {
  description = "Existing checker Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.checker_lambda_arn != ""
    error_message = "checker_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "dispatcher_lambda_arn" {
  description = "Existing dispatcher Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.dispatcher_lambda_arn != ""
    error_message = "dispatcher_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "queue_worker_lambda_arn" {
  description = "Existing queue worker Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.queue_worker_lambda_arn != ""
    error_message = "queue_worker_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "content_api_lambda_arn" {
  description = "Existing content API Lambda ARN (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.content_api_lambda_arn != ""
    error_message = "content_api_lambda_arn must be set when enable_lambda_deployment is false."
  }
}

variable "content_api_lambda_invoke_arn" {
  description = "Invoke ARN of an existing content API Lambda (used when enable_lambda_deployment=false)"
  type        = string
  default     = ""

  validation {
    condition     = var.enable_lambda_deployment || var.content_api_lambda_invoke_arn != ""
    error_message = "content_api_lambda_invoke_arn must be set when enable_lambda_deployment is false."
  }
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for summarizer"
  type        = string
  default     = "anthropic.claude-3-sonnet-20240229-v1:0"
}

variable "prompt_secret_name" {
  description = "Secrets Manager name storing summarizer prompts"
  type        = string
  default     = ""
}

variable "summarizer_provider" {
  description = "Preferred summarizer provider (cloudflare or bedrock)"
  type        = string
  default     = "cloudflare"
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID used for Workers AI"
  type        = string
  default     = ""
}

variable "cloudflare_model_id" {
  description = "Cloudflare Workers AI model identifier for summarization"
  type        = string
  default     = "@cf/meta/llama-3-8b-instruct"
}

variable "cloudflare_timeout_seconds" {
  description = "Timeout in seconds when calling Cloudflare Workers AI"
  type        = number
  default     = 40
}

variable "cloudflare_translate_model_id" {
  description = "Cloudflare Workers AI model identifier for translation"
  type        = string
  default     = "@cf/meta/m2m100-1.2b"
}

variable "cloudflare_translate_timeout_seconds" {
  description = "Timeout in seconds when calling Cloudflare translation"
  type        = number
  default     = 20
}

variable "cloudflare_translate_source_lang" {
  description = "Source language hint for Cloudflare translation (auto to detect automatically)"
  type        = string
  default     = "auto"
}

variable "cloudflare_api_token_secret_name" {
  description = "Secrets Manager secret name storing the Cloudflare API token"
  type        = string
  default     = ""
}

variable "detail_ttl_seconds" {
  description = "Seconds to keep generated detailed summaries before refreshing"
  type        = number
  default     = 43200
}

variable "detail_pending_timeout_seconds" {
  description = "Seconds to wait before considering a pending on-demand detail generation as timed out"
  type        = number
  default     = 900
}

variable "summary_ttl_seconds" {
  description = "Seconds to retain summary records in DynamoDB"
  type        = number
  default     = 172800
}

variable "source_status_ttl_seconds" {
  description = "Seconds to retain source status records in DynamoDB"
  type        = number
  default     = 172800
}

variable "enable_frontend_hosting" {
  description = "Whether to provision Amplify Hosting resources for the frontend"
  type        = bool
  default     = false
}

variable "frontend_branch_name" {
  description = "Amplify branch name used for frontend deployments"
  type        = string
  default     = "main"
}

variable "frontend_stage" {
  description = "Amplify stage associated with the frontend branch"
  type        = string
  default     = "PRODUCTION"
}

variable "frontend_revalidate_secret" {
  description = "Shared secret for triggering Next.js revalidation endpoints"
  type        = string
  default     = ""
}

variable "frontend_repository" {
  description = "Git repository URL connected to Amplify"
  type        = string
  default     = ""
}

variable "frontend_additional_environment_variables" {
  description = "Additional environment variables to inject into the Amplify frontend app"
  type        = map(string)
  default     = {}
}

variable "queue_worker_visibility_timeout_seconds" {
  description = "Visibility timeout used for the raw queue so that queue worker Lambda can finish processing."
  type        = number
  default     = 300
}

variable "raw_queue_message_retention_seconds" {
  description = "Retention period for messages in the raw ingestion queue."
  type        = number
  default     = 345600
}

variable "raw_queue_dlq_retention_seconds" {
  description = "Retention period for messages in the raw queue DLQ."
  type        = number
  default     = 1209600
}

variable "amplify_github_access_token" {
  description = "GitHub personal access token used by Amplify to clone the repository (leave empty to skip)."
  type        = string
  default     = ""
  sensitive   = true
}
