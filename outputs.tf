output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.lambda.lambda_function_arn
}

output "placeholder" {
  value       = local.placeholder
  description = "Placeholder to be used in var.sns_pattern."
}
