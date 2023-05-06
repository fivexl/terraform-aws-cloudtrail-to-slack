locals {
  placeholder = "ACCOUNT_ID"
}
module "lambda" {
  source  = "registry.terraform.io/terraform-aws-modules/lambda/aws"
  version = "3.2.0"

  function_name = var.function_name
  description   = "Send CloudTrail Events to Slack"
  handler       = "main.lambda_handler"
  runtime       = "python3.9"
  timeout       = var.lambda_timeout_seconds
  architectures = ["x86_64"]
  publish       = true

  source_path = "${path.module}/src/"

  environment_variables = merge(
    {
      HOOK_URL                               = var.default_slack_hook_url
      RULES_SEPARATOR                        = var.rules_separator
      RULES                                  = var.rules
      IGNORE_RULES                           = var.ignore_rules
      EVENTS_TO_TRACK                        = var.events_to_track
      CONFIG_SSM_PARAMETER_NAME              = aws_ssm_parameter.config.name
      SNS_PATTERN                            = var.sns_topic_pattern
      SNS_PATTERN_PLACEHOLDER                = local.placeholder
      PARAMETERS_SECRETS_EXTENSION_HTTP_PORT = "2273"
    },
    var.use_default_rules ? { USE_DEFAULT_RULES = "True" } : {}
  )
  layers = [
    "arn:aws:lambda:eu-west-1:015030872274:layer:AWS-Parameters-and-Secrets-Lambda-Extension:4"
  ]

  cloudwatch_logs_retention_in_days = var.lambda_logs_retention_in_days

  dead_letter_target_arn    = var.dead_letter_target_arn
  attach_dead_letter_policy = var.dead_letter_target_arn != null ? true : false

  tags = var.tags
}

resource "aws_ssm_parameter" "config" {
  name  = "/internal/lambda/cloudtrail-to-slack/config"
  type  = "String"
  value = jsonencode(var.configuration)
}

resource "aws_lambda_permission" "cloudwatch_logs" {
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_arn
  principal     = "logs.amazonaws.com"
  source_arn    = "${data.aws_cloudwatch_log_group.logs.arn}:*"
}

resource "aws_cloudwatch_log_subscription_filter" "cloudwatch_logs_to_slack" {
  depends_on = [aws_lambda_permission.cloudwatch_logs]

  name            = "chief-wiggum-subscription-filter"
  log_group_name  = data.aws_cloudwatch_log_group.logs.name
  filter_pattern  = ""
  destination_arn = module.lambda.lambda_function_arn
}


resource "aws_iam_role_policy_attachment" "sns" {
  policy_arn = aws_iam_policy.sns.arn
  role       = module.lambda.lambda_role_name
}

resource "aws_iam_policy" "sns" {
  policy = data.aws_iam_policy_document.sns.json
}

data "aws_iam_policy_document" "sns" {
  statement {
    actions   = ["sns:Publish"]
    resources = [replace(var.sns_topic_pattern, "ACCOUNT_ID", "*")]
  }

  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.config.arn]
  }
}
