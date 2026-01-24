output "lambda_function_arn" {
  description = "ARN of the CloudTrail to Slack Lambda function"
  value       = module.cloudtrail_to_slack.lambda_function_arn
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for S3 notifications (use this to add more subscribers)"
  value       = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
}

output "sns_topic_name" {
  description = "Name of the SNS topic for S3 notifications"
  value       = module.cloudtrail_to_slack.sns_topic_name_for_notifications
}
