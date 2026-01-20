variable "slack_bot_token" {
  description = "The Slack bot token used for sending messages to Slack"
  type        = string
  sensitive   = true
}

variable "default_slack_channel_id" {
  description = "The default Slack channel ID to send notifications to"
  type        = string
}
