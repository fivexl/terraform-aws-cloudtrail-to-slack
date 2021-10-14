
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

variable "tags" {
  description = "Tags to attach to resources"
  default     = {}
  type        = map(string)
}

