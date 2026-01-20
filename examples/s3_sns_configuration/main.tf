# Example configuration for S3 to SNS to Lambda flow
# This example shows how to enable S3 notifications via SNS

module "cloudtrail_to_slack_with_sns" {
  source = "fivexl/cloudtrail-to-slack/aws"

  function_name                  = "cloudtrail-to-slack-sns-example"
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-logs-bucket"
  cloudtrail_logs_kms_key_id     = "alias/my-cloudtrail-kms-key"

  # Enable S3 to SNS to Lambda flow
  enable_s3_sns_notifications = true
  # Optional: specify custom SNS topic name (if not provided, will use function_name-s3-notifications)
  s3_sns_topic_name = "cloudtrail-s3-notifications"

  # Slack configuration
  slack_bot_token          = var.slack_bot_token
  default_slack_channel_id = var.default_slack_channel_id

  # DynamoDB configuration for thread grouping
  dynamodb_table_name   = "cloudtrail-to-slack-events"
  dynamodb_time_to_live = 900

  # Rules configuration
  use_default_rules = true
  rules             = ""
  ignore_rules      = ""

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# Alternatively, if you want to use an existing SNS topic:
# module "cloudtrail_to_slack_with_existing_sns" {
#   source                         = "fivexl/cloudtrail-to-slack/aws"
#
#   function_name                   = "cloudtrail-to-slack-sns-example"
#   cloudtrail_logs_s3_bucket_name  = "my-cloudtrail-logs-bucket"
#   cloudtrail_logs_kms_key_id      = "alias/my-cloudtrail-kms-key"
#
#   # Enable S3 to SNS to Lambda flow with existing topic
#   enable_s3_sns_notifications     = true
#   s3_sns_topic_arn                = "arn:aws:sns:us-east-1:123456789012:existing-topic"
#
#   # Slack configuration
#   slack_bot_token                 = var.slack_bot_token
#   default_slack_channel_id        = var.default_slack_channel_id
#
#   # Other configurations...
# }
