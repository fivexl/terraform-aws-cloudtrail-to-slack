module "lambda" {
  source  = "registry.terraform.io/terraform-aws-modules/lambda/aws"
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

  dead_letter_target_arn    = var.dead_letter_target_arn
  attach_dead_letter_policy = var.dead_letter_target_arn != null ? true : false

  tags = var.tags
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
