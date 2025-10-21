resource "aws_sfn_state_machine" "this" {
  name     = var.name
  role_arn = var.role_arn

  definition = var.definition
  type       = upper(var.state_machine_type)

  dynamic "logging_configuration" {
    for_each = var.logging_configuration == null ? [] : [var.logging_configuration]
    content {
      log_destination        = logging_configuration.value.log_destination_arn
      level                  = logging_configuration.value.level
      include_execution_data = logging_configuration.value.include_execution_data
    }
  }

  tracing_configuration {
    enabled = var.tracing_enabled
  }

  tags = var.tags
}
