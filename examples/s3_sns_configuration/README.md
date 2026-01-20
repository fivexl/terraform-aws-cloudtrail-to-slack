# S3 to SNS to Lambda Configuration Example

This example demonstrates how to configure the CloudTrail to Slack module to use SNS as an intermediary between S3 and Lambda, instead of direct S3 to Lambda invocation.

## Architecture

```
S3 Bucket (CloudTrail logs) -> SNS Topic -> Lambda Function -> Slack
```

## Why use SNS?

Using SNS as an intermediary provides several benefits:

1. **Multiple Subscribers**: You can have multiple Lambda functions or other services subscribe to the same S3 events
2. **Fan-out Pattern**: Distribute S3 events to multiple destinations
3. **Better Control**: SNS provides additional filtering and routing capabilities
4. **Cross-Account**: Easier to handle cross-account scenarios
5. **Decoupling**: Better separation of concerns between S3 events and processing

## Usage

```hcl
module "cloudtrail_to_slack_with_sns" {
  source = "fivexl/cloudtrail-to-slack/aws"

  function_name                   = "cloudtrail-to-slack-sns"
  cloudtrail_logs_s3_bucket_name  = "my-cloudtrail-logs-bucket"
  cloudtrail_logs_kms_key_id      = "alias/my-cloudtrail-kms-key"

  # Enable S3 to SNS to Lambda flow
  enable_s3_sns_notifications     = true
  
  # Optional: specify custom SNS topic name
  s3_sns_topic_name               = "cloudtrail-s3-notifications"

  # Slack configuration
  slack_bot_token                 = var.slack_bot_token
  default_slack_channel_id        = var.default_slack_channel_id

  # Other configurations...
}
```

## Using an Existing SNS Topic

If you already have an SNS topic configured for S3 notifications:

```hcl
module "cloudtrail_to_slack_with_existing_sns" {
  source = "fivexl/cloudtrail-to-slack/aws"

  function_name                   = "cloudtrail-to-slack-sns"
  cloudtrail_logs_s3_bucket_name  = "my-cloudtrail-logs-bucket"
  cloudtrail_logs_kms_key_id      = "alias/my-cloudtrail-kms-key"

  # Enable S3 to SNS to Lambda flow with existing topic
  enable_s3_sns_notifications     = true
  s3_sns_topic_arn                = "arn:aws:sns:us-east-1:123456789012:existing-topic"

  # Slack configuration
  slack_bot_token                 = var.slack_bot_token
  default_slack_channel_id        = var.default_slack_channel_id

  # Other configurations...
}
```

## Important Notes

- When `enable_s3_sns_notifications` is set to `true`, the module will NOT create a direct S3 to Lambda notification
- The Lambda function is automatically updated to handle both direct S3 events and SNS-wrapped S3 events
- If `s3_sns_topic_arn` is provided, the module will use that existing topic; otherwise, it will create a new one
- The S3 bucket notification will be configured to send events to SNS instead of directly to Lambda

## Variables

| Name | Description | Type | Required |
|------|-------------|------|----------|
| `enable_s3_sns_notifications` | Whether to enable S3 to SNS to Lambda flow | `bool` | No (default: `false`) |
| `s3_sns_topic_name` | Name of the SNS topic for S3 bucket notifications | `string` | No |
| `s3_sns_topic_arn` | ARN of existing SNS topic for S3 bucket notifications | `string` | No |

## Outputs

| Name | Description |
|------|-------------|
| `lambda_function_arn` | The ARN of the Lambda Function |
| `s3_sns_topic_arn` | The ARN of the SNS topic for S3 notifications |
| `s3_sns_topic_name` | The name of the SNS topic for S3 notifications |
