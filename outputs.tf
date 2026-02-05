output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.lambda.lambda_function_arn
}

output "s3_sns_fanout_topic_arn" {
  value = var.enable_s3_sns_fanout ? (
    var.create_s3_sns_fanout_topic ? aws_sns_topic.s3_notifications[0].arn : var.s3_sns_fanout_topic_arn
  ) : null
  description = "ARN of the SNS topic for S3 fan-out. Returns the created topic ARN, the provided external topic ARN, or null if fan-out is disabled."
}

output "s3_sns_fanout_topic_name" {
  value       = var.enable_s3_sns_fanout && var.create_s3_sns_fanout_topic ? aws_sns_topic.s3_notifications[0].name : null
  description = "Name of the SNS topic for S3 fan-out (only available when module creates the topic)."
}