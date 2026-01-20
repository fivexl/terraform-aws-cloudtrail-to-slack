output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.lambda.lambda_function_arn
}

output "s3_sns_topic_arn" {
  description = "The ARN of the SNS topic for S3 notifications (if created)"
  value       = var.enable_s3_sns_notifications && var.s3_sns_topic_arn == null ? aws_sns_topic.s3_notifications[0].arn : var.s3_sns_topic_arn
}

output "s3_sns_topic_name" {
  description = "The name of the SNS topic for S3 notifications (if created)"
  value       = var.enable_s3_sns_notifications && var.s3_sns_topic_arn == null ? aws_sns_topic.s3_notifications[0].name : null
}
