output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.lambda.lambda_function_arn
}

output "sns_topic_arn_for_notifications" {
  value       = var.use_sns_topic_notifications && var.create_sns_topic_notifications ? aws_sns_topic.s3_notifications[0].arn : null
  description = "ARN of the SNS topic created for S3 notifications (if created by this module)."
}

output "sns_topic_name_for_notifications" {
  value       = var.use_sns_topic_notifications && var.create_sns_topic_notifications ? aws_sns_topic.s3_notifications[0].name : null
  description = "Name of the SNS topic created for S3 notifications (if created by this module)."
}