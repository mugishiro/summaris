variable "bucket_name" {
  description = "Name of the S3 bucket."
  type        = string
}

variable "force_destroy" {
  description = "Whether to allow Terraform to delete non-empty buckets."
  type        = bool
  default     = false
}

variable "enable_versioning" {
  description = "Enable bucket versioning."
  type        = bool
  default     = false
}

variable "enable_encryption" {
  description = "Enable default server-side encryption."
  type        = bool
  default     = true
}

variable "enable_public_block" {
  description = "Configure a public access block for the bucket."
  type        = bool
  default     = true
}

variable "encryption_algorithm" {
  description = "SSE algorithm to apply when encryption is enabled."
  type        = string
  default     = "AES256"
}

variable "tags" {
  description = "Tags applied to all bucket resources."
  type        = map(string)
  default     = {}
}
