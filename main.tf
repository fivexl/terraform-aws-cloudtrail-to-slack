module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "2.7.0"

  function_name = var.function_name
  description   = "Send CloudTrail Events to Slack"
  handler       = "main.lambda_handler"
  runtime       = "python3.8"
  publish       = true

  source_path = "${path.module}/src/"

  environment_variables = {
    HOOK_URL           = var.slack_hook_url
    TEST_MODE          = var.enable_test_mode ? "Enable" : ""
    HOOK_URL_TEST_MODE = var.slack_hook_url_test_mode
    RULES              = var.rules
    EVENTS_TO_TRACK    = var.events_to_track
    USE_DEFAULT_RULES  = var.use_default_rules
  }

  cloudwatch_logs_retention_in_days = 30

  tags = var.tags
}

data "aws_region" "r" {
}

data "aws_cloudwatch_log_group" "cloudtrail" {
  name = var.cloudtrail_cloudwatch_log_group_name
}

resource "aws_lambda_permission" "permission" {
  statement_id  = "AllowExecutionFromCloudWatchLogs"
  action        = "lambda:InvokeFunction"
  function_name = module.lambda.lambda_function_name
  source_arn    = data.aws_cloudwatch_log_group.cloudtrail.arn
  principal     = "logs.${data.aws_region.r.name}.amazonaws.com"
}

resource "aws_cloudwatch_log_subscription_filter" "logfilter" {
  name            = var.function_name
  log_group_name  = data.aws_cloudwatch_log_group.cloudtrail.name
  filter_pattern  = ""
  destination_arn = module.lambda.lambda_function_arn
}
