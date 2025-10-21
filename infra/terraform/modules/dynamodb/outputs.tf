output "id" {
  description = "DynamoDB table ID."
  value       = aws_dynamodb_table.this.id
}

output "arn" {
  description = "DynamoDB table ARN."
  value       = aws_dynamodb_table.this.arn
}

output "name" {
  description = "DynamoDB table name."
  value       = aws_dynamodb_table.this.name
}
