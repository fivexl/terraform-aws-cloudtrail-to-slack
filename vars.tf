# SLACK CONFIGURATION:
# Either the slack_bot_token or slack_hook_url can be used. If using slack_bot_token, the default_slack_channel_id must be provided.
# If both slack_bot_token and slack_hook_url are passed, the slack_bot_token will take precedence.
# The slack_bot_token offers additional features, such as consolidating duplicate events into a single message thread.

# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# Slack Webhook URL configuration:
variable "configuration" {
  description = "Allows the configuration of the Slack webhook URL per account(s). This enables the separation of events from different accounts into different channels, which is useful in the context of an AWS organization."
  type = list(object({
    accounts       = list(string)
    slack_hook_url = string
  }))
  default = null
}

variable "default_slack_hook_url" {
  description = "The Slack incoming webhook URL to be used if the AWS account ID does not match any account ID in the configuration variable."
  type        = string
  default     = null
}

# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------
# Slack App Configuration:

variable "slack_bot_token" {
  description = "The Slack bot token used for sending messages to Slack."
  type        = string
  default     = null
}

variable "slack_app_configuration" {
  description = "Allows the configuration of the Slack app per account(s). This enables the separation of events from different accounts into different channels, which is useful in the context of an AWS organization."
  type = list(object({
    accounts         = list(string)
    slack_channel_id = string
  }))
  default = null
}

variable "default_slack_channel_id" {
  description = "The Slack channel ID to be used if the AWS account ID does not match any account ID in the configuration variable."
  type        = string
  default     = null
}

# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------

# SNS Notification Configuration:

# If both `aws_sns_topic_subscription_email` and `default_sns_topic_arn` are null, no SNS notifications will be sent.
# If `default_sns_topic_arn` or `aws_sns_topic_subscription_email` is set, the module will either use the specified value or create a new SNS topic for notifications.
# Messages will be published to this topic, and all associated subscriptions will receive these notifications.
# If both `default_sns_topic_arn` and `aws_sns_topic_subscription_email` are provided, the module will not create a new SNS topic, but use the existing one.

variable "aws_sns_topic_subscription_emails" {
  description = "If set, a topic will be created and placed in the default_sns_topic_arn, and all emails in this list will be subscribed to this topic."
  type        = list(string)
  default     = []
}

variable "default_sns_topic_arn" {
  description = "Default topic for all notifications. If not set, sns notifications will not be sent."
  type        = string
  default     = null
}

variable "sns_configuration" {
  description = "Allows the configuration of the SNS topic per account(s)."
  type = list(object({
    accounts      = list(string)
    sns_topic_arn = string
  }))
  default = null
}

# -------------------------------------------------------------------------------------------------------------------------
# -------------------------------------------------------------------------------------------------------------------------

variable "function_name" {
  description = "Lambda function name"
  default     = "fivexl-cloudtrail-to-slack"
  type        = string
}

variable "cloudtrail_logs_s3_bucket_name" {
  description = "Name of the CloudWatch log s3 bucket that contains CloudTrail events"
  type        = string
}

variable "cloudtrail_logs_kms_key_id" {
  description = "Alias, key id or key arn of the KMS Key that used for CloudTrail events"
  type        = string
  default     = ""
}

variable "events_to_track" {
  description = "Comma-separated list events to track and report"
  default     = ""
  type        = string
}

variable "rules" {
  description = "Comma-separated list of rules to track events if just event name is not enough"
  default     = ""
  type        = string
}

variable "ignore_rules" {
  description = "Comma-separated list of rules to ignore events if you need to suppress something. Will be applied before rules and default_rules"
  default     = ""
  type        = string
}

variable "use_default_rules" {
  description = "Should default rules be used"
  default     = true
  type        = bool
}

variable "dead_letter_target_arn" {
  description = "The ARN of an SNS topic or SQS queue to notify when an invocation fails."
  type        = string
  default     = null
}

variable "lambda_timeout_seconds" {
  description = "Controls lambda timeout setting."
  type        = number
  default     = 30
}

variable "lambda_memory_size" {
  description = "Amount of memory in MB your Lambda Function can use at runtime. Valid value between 128 MB to 10,240 MB (10 GB), in 64 MB increments."
  type        = number
  default     = 256
}

variable "lambda_logs_retention_in_days" {
  description = "Controls for how long to keep lambda logs."
  type        = number
  default     = 30
}

variable "lambda_recreate_missing_package" {
  description = "Description: Whether to recreate missing Lambda package if it is missing locally or not"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to attach to resources"
  default     = {}
  type        = map(string)
}

variable "rules_separator" {
  description = "Custom rules separator. Can be used if there are commas in the rules"
  default     = ","
  type        = string
}

variable "log_level" {
  description = "Log level for lambda function"
  default     = "INFO"
  type        = string
}

variable "s3_removed_object_notification" {
  description = "If object was removed from cloudtrail bucket, send notification to slack"
  default     = true
  type        = bool
}

variable "rule_evaluation_errors_to_slack" {
  description = "If rule evaluation error occurs, send notification to slack"
  default     = true
  type        = bool
}

variable "s3_notification_filter_prefix" {
  description = "S3 notification filter prefix"
  default     = "AWSLogs/"
  type        = string
}

variable "dynamodb_table_name" {
  description = "Name of the dynamodb table, it would not be created if slack_bot_token is not set."
  default     = "fivexl-cloudtrail-to-slack-table"
  type        = string
}

variable "dynamodb_time_to_live" {
  description = "How long to keep cloudtrail events in dynamodb table, for collecting similar events in thread of one message"
  default     = 900
  type        = number
}
