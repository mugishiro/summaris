terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.61"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  project_prefix     = "${var.environment}-${var.project_name}"
  collector_arn      = var.enable_lambda_deployment ? module.lambda_collector[0].arn : var.collector_lambda_arn
  preprocessor_arn   = var.enable_lambda_deployment ? module.lambda_preprocessor[0].arn : var.preprocessor_lambda_arn
  summarizer_arn     = var.enable_lambda_deployment ? module.lambda_summarizer[0].arn : var.summarizer_lambda_arn
  store_arn          = var.enable_lambda_deployment ? module.lambda_postprocess[0].arn : var.postprocess_lambda_arn
  checker_arn        = var.enable_lambda_deployment ? module.lambda_checker[0].arn : var.checker_lambda_arn
  dispatcher_arn     = var.enable_lambda_deployment ? module.lambda_dispatcher[0].arn : var.dispatcher_lambda_arn
  queue_worker_arn   = var.enable_lambda_deployment ? module.lambda_queue_worker[0].arn : var.queue_worker_lambda_arn
  content_api_arn    = var.enable_lambda_deployment ? module.lambda_content_api[0].arn : var.content_api_lambda_arn
  content_api_invoke = var.enable_lambda_deployment ? module.lambda_content_api[0].invoke_arn : var.content_api_lambda_invoke_arn
  raw_archive_suffix = coalesce(var.raw_archive_suffix, substr(md5("${var.aws_account_id}-${var.environment}"), 0, 8))
  api_stage_name     = var.environment
  alarm_topic_name = (
    var.alarm_sns_topic_name != null && trimspace(var.alarm_sns_topic_name) != ""
  ) ? trimspace(var.alarm_sns_topic_name) : "${local.project_prefix}-alerts"
  custom_domain_name = trimspace(var.frontend_custom_domain_name)
}

data "aws_partition" "current" {}

resource "aws_sns_topic" "alerts" {
  name = local.alarm_topic_name

  tags = merge(var.default_tags, {
    Name        = local.alarm_topic_name
    Environment = var.environment
    Service     = "monitoring"
  })
}

resource "aws_sns_topic_subscription" "alert_emails" {
  for_each = {
    for email in var.alarm_notification_emails : trimspace(email) => trimspace(email)
    if email != null && trimspace(email) != ""
  }

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = each.value
}

module "summary_table" {
  source = "../../modules/dynamodb"

  table_name    = "${local.project_prefix}-summary"
  billing_mode  = "PAY_PER_REQUEST"
  hash_key      = "pk"
  range_key     = "sk"
  ttl_attribute = "expires_at"

  attributes = [
    {
      name = "pk"
      type = "S"
    },
    {
      name = "sk"
      type = "S"
    }
  ]

  point_in_time_recovery_enabled = true

  tags = merge(var.default_tags, {
    Name        = "${local.project_prefix}-summary"
    Environment = var.environment
  })
}

module "source_status_table" {
  source = "../../modules/dynamodb"

  table_name    = "${local.project_prefix}-source-status"
  billing_mode  = "PAY_PER_REQUEST"
  hash_key      = "pk"
  range_key     = "sk"
  ttl_attribute = "expires_at"

  attributes = [
    {
      name = "pk"
      type = "S"
    },
    {
      name = "sk"
      type = "S"
    }
  ]

  point_in_time_recovery_enabled = true

  tags = merge(var.default_tags, {
    Name        = "${local.project_prefix}-source-status"
    Environment = var.environment
  })
}

module "raw_archive_bucket" {
  source = "../../modules/s3_secure_bucket"

  bucket_name          = "${local.project_prefix}-raw-${local.raw_archive_suffix}"
  force_destroy        = true
  enable_versioning    = true
  enable_encryption    = true
  enable_public_block  = false
  encryption_algorithm = "AES256"

  tags = merge(var.default_tags, {
    Name        = "${local.project_prefix}-raw"
    Environment = var.environment
  })
}

resource "random_id" "ddb_export_suffix" {
  byte_length = 4
}

module "ddb_export_bucket" {
  source = "../../modules/s3_secure_bucket"

  bucket_name         = "${local.project_prefix}-ddb-export-${random_id.ddb_export_suffix.hex}"
  force_destroy       = false
  enable_versioning   = true
  enable_encryption   = true
  enable_public_block = true

  tags = merge(var.default_tags, {
    Name        = "${local.project_prefix}-ddb-export"
    Environment = var.environment
  })
}

data "aws_iam_policy_document" "ddb_export_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["dynamodb.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ddb_export" {
  name               = "${local.project_prefix}-ddb-export"
  assume_role_policy = data.aws_iam_policy_document.ddb_export_assume.json

  tags = merge(var.default_tags, {
    Service = "dynamodb-export"
  })
}

data "aws_iam_policy_document" "ddb_export_s3_access" {
  statement {
    sid    = "BucketActions"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
      "s3:GetBucketLocation"
    ]
    resources = [module.ddb_export_bucket.bucket_arn]
  }

  statement {
    sid    = "ObjectActions"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
      "s3:PutObjectTagging"
    ]
    resources = ["${module.ddb_export_bucket.bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "ddb_export" {
  name   = "${local.project_prefix}-ddb-export-s3"
  role   = aws_iam_role.ddb_export.id
  policy = data.aws_iam_policy_document.ddb_export_s3_access.json
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  count  = var.enable_raw_archive_lifecycle ? 1 : 0
  bucket = module.raw_archive_bucket.bucket_id

  rule {
    id     = "expire-objects"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 2
    }
  }
}

resource "aws_iam_role" "lambda" {
  count = var.enable_lambda_deployment ? 1 : 0

  name               = "${local.project_prefix}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json

  tags = merge(var.default_tags, {
    Service = "lambda-shared"
  })
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  count      = var.enable_lambda_deployment ? 1 : 0
  role       = aws_iam_role.lambda[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  count      = var.enable_lambda_deployment ? 1 : 0
  role       = aws_iam_role.lambda[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonBedrockFullAccess"
}

resource "aws_iam_role_policy" "lambda_inline" {
  count = var.enable_lambda_deployment ? 1 : 0

  name   = "${local.project_prefix}-lambda-inline"
  role   = aws_iam_role.lambda[0].id
  policy = data.aws_iam_policy_document.lambda_inline.json
}

data "aws_iam_policy_document" "lambda_inline" {
  statement {
    sid    = "SecretsManagerAccess"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:secretsmanager:${var.aws_region}:${var.aws_account_id}:secret:*"
    ]
  }

  statement {
    sid    = "DynamoDBSummaryAccess"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:BatchGetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:UpdateItem"
    ]
    resources = [
      module.summary_table.arn,
      "${module.summary_table.arn}/index/*"
    ]
  }

  statement {
    sid    = "SourceStatusAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem"
    ]
    resources = [module.source_status_table.arn]
  }

  statement {
    sid    = "S3Access"
    effect = "Allow"
    actions = [
      "s3:PutObject"
    ]
    resources = [
      "${module.raw_archive_bucket.bucket_arn}/*"
    ]
  }

  statement {
    sid    = "AmazonTranslate"
    effect = "Allow"
    actions = [
      "translate:TranslateText"
    ]
    resources = ["*"]
  }

  statement {
    sid    = "SQSSendMessage"
    effect = "Allow"
    actions = [
      "sqs:SendMessage"
    ]
    resources = [
      module.raw_queue.queue_arn
    ]
  }

  statement {
    sid    = "SQSConsumerAccess"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:DeleteMessageBatch",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
      "sqs:ChangeMessageVisibilityBatch"
    ]
    resources = [
      module.raw_queue.queue_arn
    ]
  }


  statement {
    sid    = "InvokePipelineFunctions"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction"
    ]
    resources = [
      local.collector_arn,
      local.preprocessor_arn,
      local.summarizer_arn,
      local.store_arn,
      local.queue_worker_arn
    ]
  }

  statement {
    sid    = "AlertTopicPublish"
    effect = "Allow"
    actions = [
      "sns:Publish"
    ]
    resources = [aws_sns_topic.alerts.arn]
  }
}

module "lambda_collector" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-collector"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.collector_package
  source_code_hash = var.collector_package != null ? filebase64sha256(var.collector_package) : null
  timeout          = 20

  tags = merge(var.default_tags, { Service = "collector" })
}

module "lambda_preprocessor" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-preprocessor"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.preprocessor_package
  source_code_hash = var.preprocessor_package != null ? filebase64sha256(var.preprocessor_package) : null
  timeout          = 240

  environment = {
    SIMHASH_BITS             = "64"
    LANGUAGE_SCORE_THRESHOLD = "0.5"
    DEFAULT_LANGUAGE         = "unknown"
  }

  tags = merge(var.default_tags, { Service = "preprocessor" })
}

module "lambda_summarizer" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-summarizer"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.summarizer_package
  source_code_hash = var.summarizer_package != null ? filebase64sha256(var.summarizer_package) : null
  timeout          = 120

  environment = {
    BEDROCK_MODEL_ID                 = var.bedrock_model_id
    PROMPT_SECRET_NAME               = var.prompt_secret_name
    SUMMARIZER_PROVIDER              = var.summarizer_provider
    CLOUDFLARE_ACCOUNT_ID            = var.cloudflare_account_id
    CLOUDFLARE_MODEL_ID              = var.cloudflare_model_id
    CLOUDFLARE_TIMEOUT_SECONDS       = tostring(var.cloudflare_timeout_seconds)
    CLOUDFLARE_API_TOKEN_SECRET_NAME = var.cloudflare_api_token_secret_name
  }

  tags = merge(var.default_tags, { Service = "summarizer" })
}

module "lambda_checker" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-checker"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.checker_package
  source_code_hash = var.checker_package != null ? filebase64sha256(var.checker_package) : null
  timeout          = 15

  environment = {
    SOURCE_STATUS_TABLE       = module.source_status_table.name
    SOURCE_STATUS_TTL_SECONDS = tostring(var.source_status_ttl_seconds)
  }

  tags = merge(var.default_tags, { Service = "checker" })
}

module "lambda_dispatcher" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-dispatcher"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.dispatcher_package
  source_code_hash = var.dispatcher_package != null ? filebase64sha256(var.dispatcher_package) : null
  timeout          = 15

  environment = {
    RAW_QUEUE_URL      = module.raw_queue.queue_url
    SUMMARY_TABLE_NAME = module.summary_table.name
  }

  tags = merge(var.default_tags, { Service = "dispatcher" })
}

module "lambda_postprocess" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-store"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.postprocess_package
  source_code_hash = var.postprocess_package != null ? filebase64sha256(var.postprocess_package) : null
  timeout          = 240

  environment = {
    SUMMARY_TABLE_NAME                   = module.summary_table.name
    RAW_BUCKET_NAME                      = module.raw_archive_bucket.bucket_name
    ENABLE_TITLE_TRANSLATION             = tostring(var.enable_title_translation)
    ENABLE_SUMMARY_TRANSLATION           = tostring(var.enable_summary_translation)
    TRANSLATE_REGION                     = var.aws_region
    DETAIL_TTL_SECONDS                   = tostring(var.detail_ttl_seconds)
    SUMMARY_TTL_SECONDS                  = tostring(var.summary_ttl_seconds)
    CLOUDFLARE_ACCOUNT_ID                = var.cloudflare_account_id
    CLOUDFLARE_TRANSLATE_MODEL_ID        = var.cloudflare_translate_model_id
    CLOUDFLARE_TRANSLATE_TIMEOUT_SECONDS = tostring(var.cloudflare_translate_timeout_seconds)
    CLOUDFLARE_TRANSLATE_SOURCE_LANG     = var.cloudflare_translate_source_lang
    CLOUDFLARE_API_TOKEN_SECRET_NAME     = var.cloudflare_api_token_secret_name
  }

  tags = merge(var.default_tags, { Service = "postprocess" })
}

module "lambda_queue_worker" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-queue-worker"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.queue_worker_package
  source_code_hash = var.queue_worker_package != null ? filebase64sha256(var.queue_worker_package) : null
  timeout          = 240

  environment = {
    COLLECTOR_LAMBDA_ARN      = local.collector_arn
    PREPROCESSOR_LAMBDA_ARN   = local.preprocessor_arn
    SUMMARIZER_LAMBDA_ARN     = local.summarizer_arn
    STORE_LAMBDA_ARN          = local.store_arn
    SUMMARY_TABLE_NAME        = module.summary_table.name
    ALERT_TOPIC_ARN           = aws_sns_topic.alerts.arn
  }

  tags = merge(var.default_tags, { Service = "queue-worker" })
}

module "lambda_content_api" {
  count  = var.enable_lambda_deployment ? 1 : 0
  source = "../../modules/lambda_function"

  function_name    = "${local.project_prefix}-content-api"
  role_arn         = aws_iam_role.lambda[0].arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  filename         = var.content_api_package
  source_code_hash = var.content_api_package != null ? filebase64sha256(var.content_api_package) : null
  timeout          = 10

  environment = {
    SUMMARY_TABLE_NAME             = module.summary_table.name
    WORKER_LAMBDA_ARN              = local.queue_worker_arn
    DETAIL_TTL_SECONDS             = tostring(var.detail_ttl_seconds)
    DETAIL_PENDING_TIMEOUT_SECONDS = tostring(var.detail_pending_timeout_seconds)
    ALERT_TOPIC_ARN                = aws_sns_topic.alerts.arn
  }

  tags = merge(var.default_tags, { Service = "content-api" })
}

resource "aws_cloudwatch_log_group" "content_api_lambda" {
  count             = var.enable_lambda_deployment ? 1 : 0
  name              = "/aws/lambda/${module.lambda_content_api[0].name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "content_api_gateway" {
  name              = "/aws/apigateway/${local.project_prefix}-content"
  retention_in_days = 14
}

resource "aws_apigatewayv2_api" "content" {
  name          = "${local.project_prefix}-content-api"
  protocol_type = "HTTP"
  description   = "News summary content API"
}

resource "aws_apigatewayv2_integration" "content" {
  api_id                 = aws_apigatewayv2_api.content.id
  integration_type       = "AWS_PROXY"
  integration_uri        = local.content_api_invoke
  integration_method     = "POST"
  payload_format_version = "2.0"
  timeout_milliseconds   = 10000
}

resource "aws_apigatewayv2_route" "clusters" {
  api_id    = aws_apigatewayv2_api.content.id
  route_key = "GET /clusters"
  target    = "integrations/${aws_apigatewayv2_integration.content.id}"
}

resource "aws_apigatewayv2_route" "cluster_detail" {
  api_id    = aws_apigatewayv2_api.content.id
  route_key = "GET /clusters/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.content.id}"
}

resource "aws_apigatewayv2_route" "cluster_detail_summaries_post" {
  api_id    = aws_apigatewayv2_api.content.id
  route_key = "POST /clusters/{id}/summaries"
  target    = "integrations/${aws_apigatewayv2_integration.content.id}"
}

resource "aws_apigatewayv2_route" "cluster_detail_summaries_get" {
  api_id    = aws_apigatewayv2_api.content.id
  route_key = "GET /clusters/{id}/summaries"
  target    = "integrations/${aws_apigatewayv2_integration.content.id}"
}

resource "aws_apigatewayv2_stage" "content" {
  api_id      = aws_apigatewayv2_api.content.id
  name        = local.api_stage_name
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.content_api_gateway.arn
    format = jsonencode({
      requestId = "$context.requestId",
      routeKey  = "$context.routeKey",
      status    = "$context.status",
      ip        = "$context.identity.sourceIp"
    })
  }
}

resource "aws_lambda_permission" "content_api_gateway" {
  count         = var.enable_lambda_deployment ? 1 : 0
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda_content_api[0].name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.content.execution_arn}/*/*"
}

resource "aws_iam_role" "step_functions" {
  name               = "${local.project_prefix}-sfn"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json

  tags = merge(var.default_tags, {
    Service = "step-functions"
  })
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "sfn_invoke_lambda" {
  name   = "${local.project_prefix}-sfn-invoke"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.sfn_invoke_lambda.json
}

data "aws_iam_policy_document" "sfn_invoke_lambda" {
  statement {
    actions = ["lambda:InvokeFunction"]
    effect  = "Allow"
    resources = [
      local.collector_arn,
      local.preprocessor_arn,
      local.summarizer_arn,
      local.checker_arn,
      local.dispatcher_arn,
      local.store_arn,
      local.queue_worker_arn
    ]
  }
}

resource "aws_iam_role_policy" "sfn_eventbridge" {
  name   = "${local.project_prefix}-sfn-eventbridge"
  role   = aws_iam_role.step_functions.id
  policy = data.aws_iam_policy_document.sfn_eventbridge.json
}

data "aws_iam_policy_document" "sfn_eventbridge" {
  statement {
    actions = [
      "events:PutRule",
      "events:PutTargets",
      "events:DeleteRule",
      "events:RemoveTargets",
      "events:DescribeRule",
      "events:CreateManagedRule",
      "events:TagResource",
      "events:ListTagsForResource"
    ]
    effect    = "Allow"
    resources = ["arn:${data.aws_partition.current.partition}:events:${var.aws_region}:${var.aws_account_id}:rule/*"]
  }

  statement {
    actions   = ["iam:CreateServiceLinkedRole"]
    effect    = "Allow"
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values   = ["events.amazonaws.com"]
    }
  }
}

module "pipeline_state_machine" {
  source = "../../modules/stepfunctions"

  name     = "${local.project_prefix}-pipeline"
  role_arn = aws_iam_role.step_functions.arn
  definition = templatefile(
    "${path.module}/../../stepfunctions/pipeline.asl.json",
    {
      CollectorLambdaArn  = local.collector_arn
      CheckerLambdaArn    = local.checker_arn
      DispatcherLambdaArn = local.dispatcher_arn
      StoreLambdaArn      = local.store_arn
      WorkerLambdaArn     = local.queue_worker_arn
    }
  )

  tags = merge(var.default_tags, {
    Environment = var.environment
  })
}

resource "aws_cloudwatch_dashboard" "pipeline" {
  dashboard_name = "${local.project_prefix}-pipeline"
  dashboard_body = templatefile("${path.module}/templates/dashboard.json.tpl", {
    state_machine_name  = module.pipeline_state_machine.name
    collector_name      = var.enable_lambda_deployment ? module.lambda_collector[0].name : "collector"
    preprocessor_name   = var.enable_lambda_deployment ? module.lambda_preprocessor[0].name : "preprocessor"
    summarizer_name     = var.enable_lambda_deployment ? module.lambda_summarizer[0].name : "summarizer"
    postprocess_name    = var.enable_lambda_deployment ? module.lambda_postprocess[0].name : "postprocess"
    checker_name        = var.enable_lambda_deployment ? module.lambda_checker[0].name : "checker"
    dispatcher_name     = var.enable_lambda_deployment ? module.lambda_dispatcher[0].name : "dispatcher"
    queue_worker_name   = var.enable_lambda_deployment ? module.lambda_queue_worker[0].name : "queue-worker"
    summary_table_name  = module.summary_table.name
    raw_queue_name      = module.raw_queue.queue_name
    region              = var.aws_region
  })
}

resource "aws_cloudwatch_metric_alarm" "summarizer_errors" {
  count               = var.enable_lambda_deployment ? 1 : 0
  alarm_name          = "${local.project_prefix}-summarizer-errors"
  alarm_description   = "prod summarizer Lambda errors detected (sum >= 1 in 5 minutes)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = var.summarizer_error_alarm_threshold
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = module.lambda_summarizer[0].name
  }
}

resource "aws_cloudwatch_metric_alarm" "postprocess_errors" {
  count               = var.enable_lambda_deployment ? 1 : 0
  alarm_name          = "${local.project_prefix}-postprocess-errors"
  alarm_description   = "prod postprocess Lambda errors detected (sum >= 1 in 5 minutes)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = var.postprocess_error_alarm_threshold
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    FunctionName = module.lambda_postprocess[0].name
  }
}

resource "aws_cloudwatch_metric_alarm" "pipeline_failures" {
  alarm_name          = "${local.project_prefix}-pipeline-failures"
  alarm_description   = "prod Step Functions pipeline recorded execution failure"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = var.pipeline_failure_alarm_threshold
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    StateMachineArn = module.pipeline_state_machine.arn
  }
}

resource "aws_cloudwatch_metric_alarm" "api_gateway_5xx" {
  alarm_name          = "${local.project_prefix}-api-5xx"
  alarm_description   = "prod content API has 5xx responses (sum >= 5 in 5 minutes)"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  threshold           = var.api_gateway_5xx_alarm_threshold
  metric_name         = "5xx"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimensions = {
    ApiId = aws_apigatewayv2_api.content.id
    Stage = aws_apigatewayv2_stage.content.name
  }
}

module "ingestion_scheduler" {
  count = length(var.scheduler_sources) > 0 ? 1 : 0

  source            = "../../modules/eventbridge_scheduler"
  environment       = var.environment
  project_name      = var.project_name
  state_machine_arn = module.pipeline_state_machine.arn
  sources           = var.scheduler_sources
  tags              = var.default_tags
}

module "raw_queue" {
  source = "../../modules/sqs"

  queue_name                    = "${local.project_prefix}-raw-queue"
  dlq_enabled                   = true
  visibility_timeout_seconds    = max(300, var.queue_worker_visibility_timeout_seconds)
  dlq_max_receive_count         = 10
  message_retention_seconds     = var.raw_queue_message_retention_seconds
  dlq_message_retention_seconds = var.raw_queue_dlq_retention_seconds
  tags = merge(var.default_tags, {
    Environment = var.environment
    Service     = "raw-queue"
  })
}

resource "aws_lambda_event_source_mapping" "queue_worker" {
  count = var.enable_lambda_deployment ? 1 : 0

  event_source_arn                   = module.raw_queue.queue_arn
  function_name                      = local.queue_worker_arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 5
  enabled                            = true
}

data "aws_iam_policy_document" "amplify_service_assume" {
  count = var.enable_frontend_hosting ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["amplify.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "amplify_service" {
  count = var.enable_frontend_hosting ? 1 : 0

  name               = "${local.project_prefix}-amplify-service"
  assume_role_policy = data.aws_iam_policy_document.amplify_service_assume[0].json

  tags = merge(var.default_tags, {
    Environment = var.environment
    Service     = "frontend"
  })
}

resource "aws_iam_role_policy_attachment" "amplify_service_admin" {
  count      = var.enable_frontend_hosting ? 1 : 0
  role       = aws_iam_role.amplify_service[0].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess-Amplify"
}

resource "aws_amplify_app" "frontend" {
  count    = var.enable_frontend_hosting ? 1 : 0
  name     = "${local.project_prefix}-frontend"
  platform = "WEB_COMPUTE"

  iam_service_role_arn = aws_iam_role.amplify_service[0].arn
  repository           = trimspace(var.frontend_repository) != "" ? var.frontend_repository : null
  access_token         = trimspace(var.amplify_github_access_token) != "" ? var.amplify_github_access_token : null
  build_spec           = <<-EOT
    version: 1
    applications:
      - appRoot: frontend
        frontend:
          phases:
            preBuild:
              commands:
                - npm ci
            build:
              commands:
                - npm run build
        artifacts:
          baseDirectory: .next
          files:
            - '**/*'
        cache:
          paths:
            - node_modules/**/*
    EOT

  environment_variables = merge(
    {
      NEXT_PUBLIC_API_BASE_URL = "${aws_apigatewayv2_api.content.api_endpoint}/${local.api_stage_name}"
      NEWS_API_BASE_URL        = "${aws_apigatewayv2_api.content.api_endpoint}/${local.api_stage_name}"
    },
    length(var.frontend_revalidate_secret) > 0 ? { REVALIDATE_SECRET = var.frontend_revalidate_secret } : {},
    var.frontend_additional_environment_variables
  )

  dynamic "custom_rule" {
    for_each = local.custom_domain_name != "" ? [local.custom_domain_name] : []
    content {
      source = "https://www.${custom_rule.value}/<*>"
      target = "https://${custom_rule.value}/<*>"
      status = "301"
    }
  }

  tags = merge(var.default_tags, {
    Environment = var.environment
    Service     = "frontend"
  })
}

resource "aws_amplify_branch" "frontend" {
  count       = var.enable_frontend_hosting ? 1 : 0
  app_id      = aws_amplify_app.frontend[0].id
  branch_name = var.frontend_branch_name
  stage       = var.frontend_stage

  enable_auto_build = true
  framework         = "Next.js - SSR"

  tags = merge(var.default_tags, {
    Environment = var.environment
    Service     = "frontend"
  })
}

data "aws_route53_zone" "frontend_custom_domain" {
  count        = (local.custom_domain_name != "" && var.enable_frontend_hosting) ? 1 : 0
  name         = local.custom_domain_name
  private_zone = false
}

resource "aws_amplify_domain_association" "frontend_domain" {
  count = (local.custom_domain_name != "" && var.enable_frontend_hosting) ? 1 : 0

  app_id      = aws_amplify_app.frontend[0].id
  domain_name = local.custom_domain_name

  wait_for_verification = true

  dynamic "sub_domain" {
    for_each = var.frontend_custom_domain_subdomains
    content {
      branch_name = aws_amplify_branch.frontend[0].branch_name
      prefix      = sub_domain.value
    }
  }

  depends_on = [
    aws_amplify_branch.frontend,
    data.aws_route53_zone.frontend_custom_domain
  ]
}
