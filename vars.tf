
variable "function_name" {
  description = "Lambda function name"
  default     = "fivexl-cloudtrail-to-slack"
  type        = string
}

variable "configuration" {
  description = "Allows to configure slack web hook url per account(s) so you can separate events from different accounts to different channels. Useful in context of AWS organization"
  type = list(object({
    accounts       = list(string)
    slack_hook_url = string
  }))
  default = null
}

variable "default_slack_hook_url" {
  description = "Slack incoming webhook URL to be used if AWS account id does not match any account id from configuration variable"
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