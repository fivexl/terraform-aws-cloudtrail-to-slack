
variable "function_name" {
    description = "Lambda function name"
    default     = "fivexl-cloudtrail-to-slack"
    type        = string
}

variable "slack_hook_url" {
    description = "Slack incoming webhook URL"
    type        = string
}

variable "cloudtrail_cloudwatch_log_group_name" {
    description = "Name of the CloudWatch log group that contains CloudTrail events"
    type        = string 
}

variable "rules" {
    description = "List of rules to filter events"
    default     = ""
    type        = string
}

variable "use_default_rules" {
    description = "List of rules to filter events"
    default     = true
    type        = bool
}

variable "tags" {
    description = "Tags to attach to resources"
    default     = {}
    type        = map(string)
}

