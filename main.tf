module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "4.18.0"

  function_name = var.function_name
  description   = "Send CloudTrail Events to Slack"
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  timeout       = var.lambda_timeout_seconds
  publish       = true

  source_path = [
    {
      path             = "${path.module}/src/"
      pip_requirements = "${path.module}/src/deploy_requirements.txt"
      artifacts_dir    = "${path.root}/builds/"
      patterns = [
        "!.venv/.*",
        "!.vscode/.*",
        "!__pycache__/.*",
        "!tests/.*",
        "!tools/.*",
        "!.pytest_cache/.*",
      ]
    }
  ]

  docker_image             = "lambda/python:3.10"
  docker_file              = "${path.module}/src/docker/Dockerfile"
  recreate_missing_package = var.lambda_recreate_missing_package
  build_in_docker          = var.lambda_build_in_docker

  environment_variables = merge(
    {
      FUNCTION_NAME = var.function_name

      HOOK_URL      = var.default_slack_hook_url
      CONFIGURATION = try(jsonencode(var.configuration), "")

      SLACK_BOT_TOKEN          = try(var.slack_bot_token, "")
      SLACK_APP_CONFIGURATION  = try(jsonencode(var.slack_app_configuration), "")
      DEFAULT_SLACK_CHANNEL_ID = try(var.default_slack_channel_id, "")

      DEFAULT_SNS_TOPIC_ARN = try(aws_sns_topic.events_to_sns[0].arn, var.default_sns_topic_arn, "")
      SNS_CONFIGURATION     = try(jsonencode(var.sns_configuration), "")

      RULES_SEPARATOR                 = var.rules_separator
      RULES                           = var.rules
      IGNORE_RULES                    = var.ignore_rules
      EVENTS_TO_TRACK                 = var.events_to_track
      LOG_LEVEL                       = var.log_level
      RULE_EVALUATION_ERRORS_TO_SLACK = var.rule_evaluation_errors_to_slack

      DYNAMODB_TIME_TO_LIVE = var.dynamodb_time_to_live
      DYNAMODB_TABLE_NAME   = try(module.cloudtrail_to_slack_dynamodb_table[0].dynamodb_table_id, "")

      USE_DEFAULT_RULES                     = var.use_default_rules
      PUSH_ACCESS_DENIED_CLOUDWATCH_METRICS = var.push_access_denied_cloudwatch_metrics
    },
  )

  memory_size = var.lambda_memory_size

  cloudwatch_logs_retention_in_days = var.lambda_logs_retention_in_days

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.s3.json

  dead_letter_target_arn    = var.dead_letter_target_arn
  attach_dead_letter_policy = var.dead_letter_target_arn != null ? true : false

  tags = var.tags
}

data "aws_partition" "current" {}

data "aws_iam_policy_document" "s3" {
  statement {
    sid = "AllowLambdaToGetObjects"

    actions = [
      "s3:GetObject",
    ]

    resources = [
      "${data.aws_s3_bucket.cloudtrail.arn}/*",
    ]
  }
  statement {
    sid = "AllowLambdaToInteractWithDynamoDB"

    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
    ]
    resources = [
      "arn:${data.aws_partition.current.partition}:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_table_name}"
    ]
  }
  statement {
    sid = "AllowLambdaToPushCloudWatchMetrics"

    actions = [
      "cloudwatch:PutMetricData",
    ]
    resources = [
      "*"
    ]
  }
  dynamic "statement" {
    for_each = length(aws_sns_topic.events_to_sns) > 0 ? [1] : []
    content {
      sid = "AllowLambdaToPushToSNSTopic"

      actions = [
        "sns:Publish",
      ]

      resources = [
        aws_sns_topic.events_to_sns[0].arn,
      ]
    }
  }

  dynamic "statement" {
    for_each = var.default_sns_topic_arn != null ? [1] : []
    content {
      sid = "AllowLambdaToPushToDefaultSNSTopic"

      actions = [
        "sns:Publish",
      ]

      resources = [
        var.default_sns_topic_arn,
      ]
    }
  }

  dynamic "statement" {
    for_each = var.cloudtrail_logs_kms_key_id != "" ? { create = true } : {}
    content {
      sid = "AllowLambdaToUseKMSKey"

      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
      ]

      resources = [
        data.aws_kms_key.cloudtrail[0].arn,
      ]
    }
  }

}

data "aws_kms_key" "cloudtrail" {
  count  = var.cloudtrail_logs_kms_key_id != "" ? 1 : 0
  key_id = var.cloudtrail_logs_kms_key_id
}

data "aws_s3_bucket" "cloudtrail" {
  bucket = var.cloudtrail_logs_s3_bucket_name
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# SNS Topic for S3 notifications (optional - for fan-out pattern)
resource "aws_sns_topic" "s3_notifications" {
  count = var.use_sns_topic_notifications && var.create_sns_topic_notifications ? 1 : 0
  name  = var.sns_topic_name_for_notifications
  tags  = var.tags
}

# SNS Topic Policy - Allow S3 to publish
resource "aws_sns_topic_policy" "s3_notifications" {
  count = var.use_sns_topic_notifications && var.create_sns_topic_notifications ? 1 : 0
  arn   = aws_sns_topic.s3_notifications[0].arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "s3.amazonaws.com"
      }
      Action   = "SNS:Publish"
      Resource = aws_sns_topic.s3_notifications[0].arn
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
        ArnLike = {
          "aws:SourceArn" = data.aws_s3_bucket.cloudtrail.arn
        }
      }
    }]
  })
}

# Lambda permission for direct S3 invocation
resource "aws_lambda_permission" "s3" {
  count          = var.use_sns_topic_notifications ? 0 : 1
  statement_id   = "AllowExecutionFromS3Bucket"
  action         = "lambda:InvokeFunction"
  function_name  = module.lambda.lambda_function_name
  principal      = "s3.amazonaws.com"
  source_arn     = data.aws_s3_bucket.cloudtrail.arn
  source_account = data.aws_caller_identity.current.account_id
}

# Lambda permission for SNS invocation
resource "aws_lambda_permission" "sns" {
  count         = var.use_sns_topic_notifications ? 1 : 0
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "sns.amazonaws.com"
  source_arn    = var.create_sns_topic_notifications ? aws_sns_topic.s3_notifications[0].arn : var.sns_topic_arn_for_notifications
}

# SNS Subscription - Subscribe Lambda to SNS topic
resource "aws_sns_topic_subscription" "lambda" {
  count     = var.use_sns_topic_notifications ? 1 : 0
  topic_arn = var.create_sns_topic_notifications ? aws_sns_topic.s3_notifications[0].arn : var.sns_topic_arn_for_notifications
  protocol  = "lambda"
  endpoint  = module.lambda.lambda_function_arn
  # Note: raw_message_delivery is NOT supported for Lambda endpoints
  # Lambda will receive SNS envelope and automatically unwrap it
}

# S3 Bucket Notification
resource "aws_s3_bucket_notification" "bucket_notification" {
  count  = var.create_bucket_notification ? 1 : 0
  bucket = data.aws_s3_bucket.cloudtrail.id

  # Direct Lambda notification (when NOT using SNS)
  dynamic "lambda_function" {
    for_each = var.use_sns_topic_notifications ? [] : [1]
    content {
      lambda_function_arn = module.lambda.lambda_function_arn
      events              = var.s3_removed_object_notification ? ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"] : ["s3:ObjectCreated:*"]
      filter_prefix       = var.s3_notification_filter_prefix
      filter_suffix       = ".json.gz"
    }
  }

  # SNS topic notification (when using SNS)
  dynamic "topic" {
    for_each = var.use_sns_topic_notifications ? [1] : []
    content {
      topic_arn     = var.create_sns_topic_notifications ? aws_sns_topic.s3_notifications[0].arn : var.sns_topic_arn_for_notifications
      events        = var.s3_removed_object_notification ? ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"] : ["s3:ObjectCreated:*"]
      filter_prefix = var.s3_notification_filter_prefix
      filter_suffix = ".json.gz"
    }
  }

  eventbridge = var.enable_eventbridge_notificaitons

  depends_on = [
    aws_lambda_permission.s3,
    aws_lambda_permission.sns,
    aws_sns_topic_policy.s3_notifications
  ]
}

moved {
  from = aws_s3_bucket_notification.bucket_notification
  to   = aws_s3_bucket_notification.bucket_notification[0]
}
