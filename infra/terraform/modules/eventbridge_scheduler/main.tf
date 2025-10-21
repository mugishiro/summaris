locals {
  sources = { for source in var.sources : source.id => source }
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.environment}-${var.project_name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json

  tags = merge(var.tags, {
    Environment = var.environment
    Service     = "eventbridge-scheduler"
  })
}

data "aws_iam_policy_document" "scheduler_permissions" {
  statement {
    sid    = "AllowStateMachineStart"
    effect = "Allow"
    actions = [
      "states:StartExecution"
    ]
    resources = [var.state_machine_arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.environment}-${var.project_name}-scheduler-start"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_permissions.json
}

resource "aws_scheduler_schedule" "this" {
  for_each = local.sources

  name        = substr("${var.environment}-${var.project_name}-${each.key}", 0, 64)
  description = coalesce(each.value.description, "Schedule for ${each.value.name}")

  schedule_expression          = each.value.schedule_expression
  schedule_expression_timezone = try(each.value.timezone, null)

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.state_machine_arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode(
      merge(
        {
          source = {
            id   = each.value.id
            name = each.value.name
          }
        },
        try(each.value.endpoint.url, null) != null ? {
          endpoint = {
            url = each.value.endpoint.url
          }
        } : {},
        each.value.settings != null && try(each.value.settings.threshold_seconds, null) != null ? {
          threshold_seconds = each.value.settings.threshold_seconds
        } : {},
        each.value.settings != null && try(each.value.settings.force_fetch, null) != null ? {
          force_fetch = each.value.settings.force_fetch
        } : {}
      )
    )
  }

  state = "ENABLED"
}
