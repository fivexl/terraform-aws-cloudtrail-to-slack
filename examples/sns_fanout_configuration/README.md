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
  use_sns_topic_notifications    = true  # Enable SNS fan-out
  create_sns_topic_notifications = true  # Create SNS topic
  sns_topic_name_for_notifications = "cloudtrail-s3-events"

  # Other configuration...
}
```

### Adding More Consumers

```hcl
# Subscribe additional Lambda to the SNS topic
resource "aws_sns_topic_subscription" "another_consumer" {
  topic_arn            = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
  protocol             = "lambda"
  endpoint             = aws_lambda_function.another_lambda.arn
  raw_message_delivery = true  # REQUIRED!
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

  use_sns_topic_notifications    = true   # Enable SNS
  create_sns_topic_notifications = false  # Don't create, use existing
  sns_topic_arn_for_notifications = aws_sns_topic.cloudtrail_events.arn

  # Other configuration...
}
```

## Benefits

| Feature | Direct S3 | SNS Fan-Out |
|---------|-----------|-------------|
| **Multiple Consumers** | ❌ No (1 only) | ✅ Yes (unlimited) |
| **Event Batching** | ✅ Yes | ✅ Yes (maintained!) |
| **Lambda Invocations** | Low | Low (same as direct) |
| **Cost** | Lowest | +$0.50 per 1M events |
| **Code Changes** | None | None |

## Cost Example

With 10,000 CloudTrail files per month and 3 Lambda consumers:

**SNS Fan-Out:**
- ~2,000 batched S3 notifications
- 6,000 Lambda invocations (2,000 × 3 consumers)
- Cost: ~$1.20 Lambda + $0.005 SNS = **$1.205/month**

**Alternative (EventBridge):**
- 10,000 individual events
- 30,000 Lambda invocations (10,000 × 3 consumers)
- Cost: ~**$6.00/month**

**SNS is 5x cheaper!**

## Usage

```bash
terraform init
terraform plan
terraform apply
```

## Outputs

- `sns_topic_arn_for_notifications` - ARN of the created SNS topic (if created)
- `sns_topic_name_for_notifications` - Name of the created SNS topic (if created)

Use these outputs to subscribe additional consumers.

## See Also

- [Detailed SNS Documentation](../../src/docs/sns-support.md)
- [Main Module README](../../README.md)
