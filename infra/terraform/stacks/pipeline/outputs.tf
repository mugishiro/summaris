output "summary_table_name" {
  value       = module.summary_table.name
  description = "Name of the DynamoDB table storing summaries"
}

output "raw_archive_bucket" {
  value       = module.raw_archive_bucket.bucket_name
  description = "S3 bucket used for raw article archival"
}

output "source_status_table_name" {
  value       = module.source_status_table.name
  description = "DynamoDB table storing source status metadata"
}

output "dynamodb_export_bucket" {
  value       = module.ddb_export_bucket.bucket_name
  description = "S3 bucket used for DynamoDB exports"
}

output "dynamodb_export_role_arn" {
  value       = aws_iam_role.ddb_export.arn
  description = "IAM role assumed by DynamoDB export tasks"
}

output "state_machine_arn" {
  value       = module.pipeline_state_machine.arn
  description = "ARN of the Step Functions pipeline"
}

output "scheduler_names" {
  value       = length(var.scheduler_sources) > 0 ? module.ingestion_scheduler[0].schedule_names : []
  description = "EventBridge scheduler names for source polling"
}

output "raw_queue_url" {
  value       = module.raw_queue.queue_url
  description = "URL of the raw ingestion SQS queue"
}

output "raw_queue_arn" {
  value       = module.raw_queue.queue_arn
  description = "ARN of the raw ingestion SQS queue"
}

output "raw_queue_dlq_arn" {
  value       = module.raw_queue.dlq_arn
  description = "ARN of the raw queue DLQ (if created)"
}

output "content_api_url" {
  value       = "${aws_apigatewayv2_api.content.api_endpoint}/${local.api_stage_name}"
  description = "Base URL for the content API (clusters endpoints)"
}

output "frontend_amplify_app_id" {
  value       = var.enable_frontend_hosting ? aws_amplify_app.frontend[0].id : null
  description = "Amplify App ID for the frontend (null when hosting is disabled)"
}

output "frontend_amplify_default_domain" {
  value       = var.enable_frontend_hosting ? aws_amplify_app.frontend[0].default_domain : null
  description = "Amplify default domain assigned to the frontend app"
}

output "frontend_amplify_branch_domain" {
  value       = var.enable_frontend_hosting ? "${var.frontend_branch_name}.${aws_amplify_app.frontend[0].default_domain}" : null
  description = "Computed domain for the configured Amplify branch on Amplify's default domain"
}
