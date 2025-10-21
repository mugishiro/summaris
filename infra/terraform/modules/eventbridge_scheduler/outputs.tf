output "schedule_names" {
  description = "Names of created scheduler schedules."
  value       = [for schedule in aws_scheduler_schedule.this : schedule.name]
}

output "role_arn" {
  description = "IAM role ARN used by EventBridge Scheduler."
  value       = aws_iam_role.scheduler.arn
}
