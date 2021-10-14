module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "2.22.0"

  function_name = var.function_name
  description   = "Send CloudTrail Events to Slack"
  handler       = "main.lambda_handler"
  runtime       = "python3.8"
  publish       = true

  source_path = "${path.module}/src/"

  environment_variables = merge(
    {
      HOOK_URL        = var.slack_hook_url
      RULES           = var.rules
      EVENTS_TO_TRACK = var.events_to_track
    },
    var.use_default_rules ? { USE_DEFAULT_RULES = "True" } : {}
  )

  cloudwatch_logs_retention_in_days = 30

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
}

data "aws_s3_bucket" "cloudtrail" {
  bucket = var.cloudtrail_logs_s3_bucket_name
}

resource "aws_lambda_permission" "s3" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  principal     = "s3.amazonaws.com"
  source_arn    = data.aws_s3_bucket.cloudtrail.arn
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = data.aws_s3_bucket.cloudtrail.id

  lambda_function {
    lambda_function_arn = module.lambda.lambda_function_arn
    events              = ["s3:ObjectCreated:*","s3:ObjectRemoved:*"]
    filter_prefix       = "AWSLogs/"
    filter_suffix       = ".json.gz"
  }

  depends_on = [aws_lambda_permission.s3]
}