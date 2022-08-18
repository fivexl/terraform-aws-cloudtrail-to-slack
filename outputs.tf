output "lambda_function_arn" {
  description = "The ARN of the Lambda Function"
  value       = module.lambda.lambda_function_arn
}

output "lambda_function_role_arn" {
  description = "The ARN of the Lambda Function Role"
  value       = module.lambda.lambda_role_arn
}

output "lambda_function_name" {
  description = "The Name of the Lambda Function"
  value       = module.lambda.lambda_function_name
}
