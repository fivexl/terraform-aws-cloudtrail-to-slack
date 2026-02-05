output "lambda_function_arn" {
  description = "ARN of the CloudTrail to Slack Lambda function"
  value       = module.cloudtrail_to_slack.lambda_function_arn
}

output "s3_sns_fanout_topic_arn" {
  description = "ARN of the SNS topic for S3 fan-out (use this to add more subscribers)"
  value       = module.cloudtrail_to_slack.s3_sns_fanout_topic_arn
}

output "s3_sns_fanout_topic_name" {
  description = "Name of the SNS topic for S3 fan-out (only available when module creates the topic)"
  value       = module.cloudtrail_to_slack.s3_sns_fanout_topic_name
}
