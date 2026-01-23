provider "aws" {
  region = "us-east-1"
}

# Example: Using SNS fan-out pattern for multiple Lambda consumers
# This allows multiple services to consume the same CloudTrail S3 events

module "cloudtrail_to_slack" {
  source = "../../"

  function_name                  = "cloudtrail-to-slack"
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-logs-bucket"

  # SNS Configuration - Enable SNS fan-out pattern
  use_sns_topic_notifications      = true # Use SNS instead of direct S3 notification
  create_sns_topic_notifications   = true # Create SNS topic in this module
  sns_topic_name_for_notifications = "cloudtrail-s3-events"

  # Slack Configuration
  default_slack_hook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

  # Rules
  use_default_rules = true

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# Example: Add another Lambda consumer to the same SNS topic
resource "aws_lambda_function" "archive_to_glacier" {
  function_name = "cloudtrail-archive"
  role          = aws_iam_role.archive_lambda.arn
  handler       = "index.handler"
  runtime       = "python3.10"
  filename      = "archive_lambda.zip"
}

resource "aws_iam_role" "archive_lambda" {
  name = "cloudtrail-archive-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Subscribe the archive Lambda to the same SNS topic
resource "aws_sns_topic_subscription" "archive_lambda" {
  topic_arn = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
  protocol  = "lambda"
  endpoint  = aws_lambda_function.archive_to_glacier.arn
  # Note: raw_message_delivery is NOT supported for Lambda protocol
  # Your Lambda must unwrap the SNS envelope (see cloudtrail-to-slack code for example)
}

resource "aws_lambda_permission" "allow_sns_archive" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.archive_to_glacier.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
}

# You can add more subscribers as needed...
# resource "aws_sns_topic_subscription" "security_analysis" {
#   topic_arn            = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
#   protocol             = "lambda"
#   endpoint             = aws_lambda_function.security_analysis.arn
#   raw_message_delivery = true
# }
