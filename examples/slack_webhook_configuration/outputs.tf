output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.cloudtrail_to_slack.lambda_function_arn
}
