
variable "function_name" {
  description = "Lambda function name"
  default     = "fivexl-cloudtrail-to-slack"
  type        = string
}

variable "slack_hook_url" {
  description = "Slack incoming webhook URL"
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

variable "tags" {
  description = "Tags to attach to resources"
  default     = {}
  type        = map(string)
}

