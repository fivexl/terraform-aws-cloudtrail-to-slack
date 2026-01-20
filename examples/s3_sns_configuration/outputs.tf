output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.cloudtrail_to_slack_with_sns.lambda_function_arn
}

output "s3_sns_topic_arn" {
  description = "The ARN of the SNS topic for S3 notifications"
  value       = module.cloudtrail_to_slack_with_sns.s3_sns_topic_arn
}

output "s3_sns_topic_name" {
  description = "The name of the SNS topic for S3 notifications"
  value       = module.cloudtrail_to_slack_with_sns.s3_sns_topic_name
}
