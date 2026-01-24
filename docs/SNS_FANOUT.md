# SNS Fan-Out Pattern Support

## Overview

The CloudTrail to Slack module now supports the **SNS fan-out pattern**, which solves AWS S3's single-destination limitation while maintaining event batching.

## The Problem

AWS S3 bucket notifications can only send each event type to **ONE destination**. This means you cannot have:
- CloudTrail → Slack Lambda
- AND CloudTrail → Archive Lambda
- AND CloudTrail → Security Lambda

**You must choose only one!**

## The Solution: SNS Fan-Out

Use SNS as a fan-out hub to enable unlimited consumers:

```
CloudTrail → S3 → SNS Topic → Lambda (CloudTrail-to-Slack)
                           → Lambda (Archive)
                           → Lambda (Security)
                           → SQS Queue
                           → ... (unlimited)
```

## Key Benefits

✅ **Multiple Consumers** - Unlimited subscribers to the same S3 events  
✅ **Event Batching Maintained** - 5 files = 1 Lambda invocation (not 5)  
✅ **Low Cost** - Only ~$0.50 per million events added  
✅ **Zero Code Changes** - Lambda code works identically  
✅ **Simple Setup** - Just set `use_sns_topic_notifications = true`  

## Configuration

### Option 1: Module Creates SNS Topic (Recommended)

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"

  # Basic configuration
  function_name                  = "cloudtrail-to-slack"
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-logs"
  default_slack_hook_url         = "https://hooks.slack.com/services/..."

  # Enable SNS fan-out
  use_sns_topic_notifications      = true
  create_sns_topic_notifications   = true
  sns_topic_name_for_notifications = "cloudtrail-s3-events"

  use_default_rules = true
}

# Add more consumers to the SNS topic
resource "aws_sns_topic_subscription" "archive_lambda" {
  topic_arn            = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
  protocol             = "lambda"
  endpoint             = aws_lambda_function.archive.arn
  raw_message_delivery = true  # REQUIRED!
}

resource "aws_lambda_permission" "allow_sns_archive" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.archive.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
}
```

### Option 2: Use External SNS Topic

```hcl
# Create and manage SNS topic separately
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

  function_name                  = "cloudtrail-to-slack"
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-logs"
  default_slack_hook_url         = "https://hooks.slack.com/services/..."

  # Use external SNS topic
  use_sns_topic_notifications     = true
  create_sns_topic_notifications  = false
  sns_topic_arn_for_notifications = aws_sns_topic.cloudtrail_events.arn

  use_default_rules = true
}
```

## Important: raw_message_delivery = true

**Always set `raw_message_delivery = true` on SNS subscriptions!**

```hcl
resource "aws_sns_topic_subscription" "lambda" {
  topic_arn            = aws_sns_topic.cloudtrail_events.arn
  protocol             = "lambda"
  endpoint             = aws_lambda_function.my_lambda.arn
  raw_message_delivery = true  # ← REQUIRED!
}
```

### Why raw_message_delivery = true?

When enabled, SNS delivers the S3 notification **exactly as received** without wrapping it in an SNS envelope. This means:
- Lambda receives the same format as direct S3 notifications
- No code changes needed
- No JSON parsing overhead
- Simpler and more efficient

## Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `use_sns_topic_notifications` | Enable SNS fan-out pattern | `false` |
| `create_sns_topic_notifications` | Create SNS topic in module | `true` |
| `sns_topic_arn_for_notifications` | External SNS topic ARN (if not creating) | `null` |
| `sns_topic_name_for_notifications` | Name for created SNS topic | `"cloudtrail-s3-notifications"` |

## Outputs

| Output | Description |
|--------|-------------|
| `sns_topic_arn_for_notifications` | ARN of SNS topic (if created) |
| `sns_topic_name_for_notifications` | Name of SNS topic (if created) |

Use these outputs to subscribe additional consumers.

## Migration from Direct S3

### Before (Direct S3 → Lambda)

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  # Default: direct S3 notification
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-logs"
  default_slack_hook_url         = "https://hooks.slack.com/..."
}
```

### After (S3 → SNS → Lambda)

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-logs"
  default_slack_hook_url         = "https://hooks.slack.com/..."
  
  # Add these two lines:
  use_sns_topic_notifications    = true
  create_sns_topic_notifications = true
}

# Now add more consumers:
resource "aws_sns_topic_subscription" "another_lambda" {
  topic_arn            = module.cloudtrail_to_slack.sns_topic_arn_for_notifications
  protocol             = "lambda"
  endpoint             = aws_lambda_function.another.arn
  raw_message_delivery = true
}
```

## Event Batching Example

When CloudTrail writes 5 log files:

```
5 files created
  ↓
1 S3 notification (Records array with 5 items)
  ↓
SNS Topic (raw_message_delivery=true)
  ↓
3 Lambda subscribers
  ↓
3 Lambda invocations (1 per subscriber)
Each processes all 5 files in one invocation
```

**Result: Event batching is maintained!**

Compare to EventBridge:
- EventBridge: 15 invocations (5 files × 3 subscribers)
- SNS: 3 invocations (1 per subscriber)
- **SNS is 5x more efficient!**

## Cost Comparison

Assuming 10,000 CloudTrail files per month with 3 Lambda consumers:

| Pattern | Lambda Invocations | Monthly Cost* |
|---------|-------------------|---------------|
| Direct S3 | Impossible (1 destination only) | - |
| **SNS Fan-Out** | ~6,000 (batched) | **$1.20** |
| EventBridge | ~30,000 (1-by-1) | $6.00 |

*Assuming 128MB, 1s duration

**SNS is 5x cheaper than EventBridge!**

## Example

See complete working example in: [`examples/sns_fanout_configuration/`](examples/sns_fanout_configuration/)

## Testing

The Lambda automatically works with both direct S3 and SNS:

```bash
cd src
.venv/bin/pytest -v
```

All tests pass - no code changes required!

## References

- [AWS S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html)
- [AWS SNS Raw Message Delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [SNS Fan-Out Pattern](https://docs.aws.amazon.com/sns/latest/dg/sns-common-scenarios.html)

## Summary

**Use SNS fan-out when you need multiple consumers for CloudTrail events:**

- Set `use_sns_topic_notifications = true`
- Set `create_sns_topic_notifications = true` (or provide external topic)
- Always use `raw_message_delivery = true` on subscriptions
- Add unlimited subscribers to the SNS topic
- Enjoy event batching and low costs!
