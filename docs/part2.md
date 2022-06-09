## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 0.12.31 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 3.43 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | >= 3.43 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_lambda"></a> [lambda](#module\_lambda) | registry.terraform.io/terraform-aws-modules/lambda/aws | 2.35.0 |

## Resources

| Name | Type |
|------|------|
| [aws_cloudwatch_log_subscription_filter.cloudwatch_logs_to_slack](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudwatch_log_subscription_filter) | resource |
| [aws_lambda_permission.cloudwatch_logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_cloudwatch_log_group.logs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/cloudwatch_log_group) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cloudtrail_cw_log_group"></a> [cloudtrail\_cw\_log\_group](#input\_cloudtrail\_cw\_log\_group) | Name of the CloudWatch log group that contains CloudTrail events | `string` | n/a | yes |
| <a name="input_configuration"></a> [configuration](#input\_configuration) | Allows to configure slack web hook url per account(s) so you can separate events from different accounts to different channels. Useful in context of AWS organization | <pre>list(object({<br>    accounts       = list(string)<br>    slack_hook_url = string<br>  }))</pre> | `null` | no |
| <a name="input_dead_letter_target_arn"></a> [dead\_letter\_target\_arn](#input\_dead\_letter\_target\_arn) | The ARN of an SNS topic or SQS queue to notify when an invocation fails. | `string` | `null` | no |
| <a name="input_default_slack_hook_url"></a> [default\_slack\_hook\_url](#input\_default\_slack\_hook\_url) | Slack incoming webhook URL to be used if AWS account id does not match any account id from configuration variable | `string` | n/a | yes |
| <a name="input_events_to_track"></a> [events\_to\_track](#input\_events\_to\_track) | Comma-separated list events to track and report | `string` | `""` | no |
| <a name="input_function_name"></a> [function\_name](#input\_function\_name) | Lambda function name | `string` | `"fivexl-cloudtrail-to-slack"` | no |
| <a name="input_ignore_rules"></a> [ignore\_rules](#input\_ignore\_rules) | Comma-separated list of rules to ignore events if you need to suppress something. Will be applied before rules and default\_rules | `string` | `""` | no |
| <a name="input_lambda_logs_retention_in_days"></a> [lambda\_logs\_retention\_in\_days](#input\_lambda\_logs\_retention\_in\_days) | Controls for how long to keep lambda logs. | `number` | `30` | no |
| <a name="input_lambda_timeout_seconds"></a> [lambda\_timeout\_seconds](#input\_lambda\_timeout\_seconds) | Controls lambda timeout setting. | `number` | `60` | no |
| <a name="input_rules"></a> [rules](#input\_rules) | Comma-separated list of rules to track events if just event name is not enough | `string` | `""` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to attach to resources | `map(string)` | `{}` | no |
| <a name="input_use_default_rules"></a> [use\_default\_rules](#input\_use\_default\_rules) | Should default rules be used | `bool` | `true` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | The ARN of the Lambda Function |
