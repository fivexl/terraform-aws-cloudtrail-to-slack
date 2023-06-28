module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "4.18.0"

  function_name = var.function_name
  description   = "Send CloudTrail Events to Slack"
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  timeout       = var.lambda_timeout_seconds
  publish       = true

  source_path = "${path.module}/src/"

  recreate_missing_package = var.lambda_recreate_missing_package

  environment_variables = merge(
    {
      HOOK_URL                        = var.default_slack_hook_url
      CONFIGURATION                   = var.configuration != null ? jsonencode(var.configuration) : ""

      SLACK_BOT_TOKEN                = var.slack_bot_token
      SLACK_APP_CONFIGURATION        = var.slack_app_configuration != null ? jsonencode(var.slack_app_configuration) : ""
      DEFAULT_SLACK_CHANNEL_ID       = var.default_slack_channel_id

      RULES_SEPARATOR                 = var.rules_separator
      RULES                           = var.rules
      IGNORE_RULES                    = var.ignore_rules
      EVENTS_TO_TRACK                 = var.events_to_track
      LOG_LEVEL                       = var.log_level
      RULE_EVALUATION_ERRORS_TO_SLACK = var.rule_evaluation_errors_to_slack
    },
    var.use_default_rules ? { USE_DEFAULT_RULES = "True" } : {}
  )

  memory_size = var.lambda_memory_size

  cloudwatch_logs_retention_in_days = var.lambda_logs_retention_in_days

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.s3.json

  dead_letter_target_arn    = var.dead_letter_target_arn
  attach_dead_letter_policy = var.dead_letter_target_arn != null ? true : false

  tags = var.tags
}

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

resource "aws_lambda_permission" "s3" {
  statement_id   = "AllowExecutionFromS3Bucket"
  action         = "lambda:InvokeFunction"
  function_name  = module.lambda.lambda_function_name
  principal      = "s3.amazonaws.com"
  source_arn     = data.aws_s3_bucket.cloudtrail.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = data.aws_s3_bucket.cloudtrail.id

  lambda_function {
    lambda_function_arn = module.lambda.lambda_function_arn
    events              = var.s3_removed_object_notification ? ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"] : ["s3:ObjectCreated:*"]
    filter_prefix       = var.s3_notification_filter_prefix
    filter_suffix       = ".json.gz"
  }

  depends_on = [aws_lambda_permission.s3]
}
