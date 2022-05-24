module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "3.2.0"

  function_name = var.function_name
  description   = "Send CloudTrail Events to Slack"
  handler       = "main.lambda_handler"
  runtime       = "python3.8"
  timeout       = var.lambda_timeout_seconds
  publish       = true

  source_path = "${path.module}/src/"

  environment_variables = merge(
    {
      HOOK_URL        = var.default_slack_hook_url
      RULES           = var.rules
      IGNORE_RULES    = var.ignore_rules
      EVENTS_TO_TRACK = var.events_to_track
      CONFIGURATION   = var.configuration != null ? jsonencode(var.configuration) : ""
    },
    var.use_default_rules ? { USE_DEFAULT_RULES = "True" } : {}
  )

  cloudwatch_logs_retention_in_days = var.lambda_logs_retention_in_days

  attach_policy_json = true
  policy_json        = data.aws_iam_policy_document.s3.json

  dead_letter_target_arn    = var.dead_letter_target_arn
  attach_dead_letter_policy = var.dead_letter_target_arn != null ? true : false

  memory_size = var.lambda_memory_size
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
    events              = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
    filter_prefix       = var.filter_prefix
    filter_suffix       = ".json.gz"
  }

  depends_on = [aws_lambda_permission.s3]
}
