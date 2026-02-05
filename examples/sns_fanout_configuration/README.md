# SNS Fan-Out Configuration Example

This example demonstrates how to use the SNS fan-out pattern to allow multiple Lambda functions to consume the same CloudTrail S3 events.

## Problem

AWS S3 bucket notifications can only send events to **ONE destination** per event type. If you need multiple services to process CloudTrail logs, you're stuck.

## Solution

Use SNS as a fan-out hub:

```
CloudTrail → S3 → SNS Topic → Lambda (CloudTrail-to-Slack)
                           → Lambda (Archive)
                           → Lambda (Security)
                           → ... (unlimited)
```

## Architecture

```
┌─────────────┐
│  CloudTrail │
└──────┬──────┘
       │ Logs
       ↓
┌─────────────┐
│  S3 Bucket  │
└──────┬──────┘
       │ S3 Notification
       ↓
┌─────────────┐
│  SNS Topic  │ (Fan-out hub)
└──────┬──────┘
       ├─→ Lambda: CloudTrail-to-Slack
       ├─→ Lambda: Archive to Glacier
       └─→ Lambda: Security Analysis
```

## Key Configuration

### Module Configuration

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"

  # SNS Configuration
  enable_s3_sns_fanout       = true  # Enable SNS fan-out
  create_s3_sns_fanout_topic = true  # Create SNS topic
  s3_sns_fanout_topic_name   = "cloudtrail-s3-events"

  # Other configuration...
}
```

### Adding More Consumers

```hcl
# Subscribe additional Lambda to the SNS topic
resource "aws_sns_topic_subscription" "another_consumer" {
  topic_arn = module.cloudtrail_to_slack.s3_sns_fanout_topic_arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.another_lambda.arn
  # Note: raw_message_delivery is NOT supported for Lambda protocol
  # Cloudtrail to Slack Lambda will unwrap the SNS envelope automatically.
}
```

## Important: Lambda and raw_message_delivery

**AWS SNS does NOT support `raw_message_delivery` for Lambda endpoints.**

According to AWS documentation, `raw_message_delivery` only works for:
- Amazon SQS
- HTTP/HTTPS endpoints
- Amazon Data Firehose

For Lambda endpoints, SNS **always wraps messages in an envelope**. The CloudTrail-to-Slack Lambda automatically detects and unwraps SNS messages, so this works transparently.

## Using External SNS Topic

If you want to manage the SNS topic separately:

```hcl
# Create SNS topic outside the module
resource "aws_sns_topic" "cloudtrail_events" {
  name = "cloudtrail-s3-events"
}

resource "aws_sns_topic_policy" "cloudtrail_events" {
  arn = aws_sns_topic.cloudtrail_events.arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "s3.amazonaws.com"
      }
      Action   = "SNS:Publish"
      Resource = aws_sns_topic.cloudtrail_events.arn
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })
}

# Use external SNS topic
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"

  enable_s3_sns_fanout       = true   # Enable SNS
  create_s3_sns_fanout_topic = false  # Don't create, use existing
  s3_sns_fanout_topic_arn    = aws_sns_topic.cloudtrail_events.arn

  # Other configuration...
}

# Use s3_sns_fanout_topic_arn to add more subscribers (should work for both created and external topics)
# module.cloudtrail_to_slack.s3_sns_fanout_topic_arn
```

## Benefits

| Feature | Direct S3 | SNS Fan-Out |
|---------|-----------|-------------|
| **Multiple Consumers** | ❌ No (1 only) | ✅ Yes (unlimited) |
| **Event Batching** | ✅ Yes | ✅ Yes (maintained!) |
| **Lambda Invocations** | Low | Low (same as direct) |
| **Cost** | Lowest | SNS -> Lambda delivery free; S3 ->SNS API requests $0.50/million |

- ~2,000 batched S3 notifications
- 6,000 Lambda invocations (2,000 × 3 consumers)
- Cost: ~$1.20 Lambda + $0.005 SNS = **$1.205/

> For current pricing, see [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/) and [AWS SNS Pricing](https://aws.amazon.com/sns/pricing/).

## Usage

```bash
terraform init
terraform plan
terraform apply
```

## Outputs

- `s3_sns_fanout_topic_arn` - ARN of the SNS topic (use this to add more subscribers)
- `s3_sns_fanout_topic_name` - Name of the SNS topic (only when module creates the topic)


## See Also

- [SNS Fan-Out Documentation](../../docs/SNS_FANOUT.md)
- [Main Module README](../../README.md)
