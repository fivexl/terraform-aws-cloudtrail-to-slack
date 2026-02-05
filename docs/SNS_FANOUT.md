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
✅ **Low Cost** - SNS to Lambda delivery is free; only pay for API requests ($0.50/million after free tier)  
✅ **Simple Setup** - Just set `enable_s3_sns_fanout = true`  

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
  enable_s3_sns_fanout      = true
  create_s3_sns_fanout_topic = true
  s3_sns_fanout_topic_name  = "cloudtrail-s3-events"

  use_default_rules = true
}

# Add more consumers to the SNS topic
resource "aws_sns_topic_subscription" "archive_lambda" {
  topic_arn = module.cloudtrail_to_slack.s3_sns_fanout_topic_arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.archive.arn
  # Note: raw_message_delivery is NOT supported for Lambda protocol.
  # Lambda always receives SNS envelope and must unwrap it.
}

resource "aws_lambda_permission" "allow_sns_archive" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.archive.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = module.cloudtrail_to_slack.s3_sns_fanout_topic_arn
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
  enable_s3_sns_fanout       = true
  create_s3_sns_fanout_topic = false
  s3_sns_fanout_topic_arn    = aws_sns_topic.cloudtrail_events.arn

  use_default_rules = true
}
```

## Important: Understanding SNS Message Delivery

### Lambda Endpoints (No raw_message_delivery)

**AWS SNS does NOT support `raw_message_delivery` for Lambda endpoints.** Lambda always receives messages wrapped in an SNS envelope. The CloudTrail-to-Slack Lambda automatically detects and unwraps SNS messages, so this works transparently.

```hcl
resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = aws_sns_topic.cloudtrail_events.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.my_lambda.arn
  # raw_message_delivery is NOT supported for Lambda protocol
}
```

### SQS, HTTP/HTTPS Endpoints (raw_message_delivery available)

For **SQS** and **HTTP/HTTPS** endpoints, you can optionally set `raw_message_delivery = true` to receive the S3 notification without the SNS envelope:

```hcl
resource "aws_sns_topic_subscription" "sqs" {
  topic_arn            = aws_sns_topic.cloudtrail_events.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.my_queue.arn
  raw_message_delivery = true  # Supported for SQS
}
```

## Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `enable_s3_sns_fanout` | Enable SNS fan-out pattern | `false` |
| `create_s3_sns_fanout_topic` | Create SNS topic in module | `true` |
| `s3_sns_fanout_topic_arn` | External SNS topic ARN (if not creating) | `null` |
| `s3_sns_fanout_topic_name` | Name for created SNS topic | `"cloudtrail-s3-notifications"` |

## Outputs

| Output | Description |
|--------|-------------|
| `s3_sns_fanout_topic_arn` | ARN of the SNS topic (created or external) |
| `s3_sns_fanout_topic_name` | Name of SNS topic (only if created by module) |

Use `s3_sns_fanout_topic_arn` to subscribe additional consumers - it works for both created and external topics.


## Event Batching Example

When CloudTrail writes 5 log files:

```
5 files created
  ↓
1 S3 notification (Records array with 5 items)
  ↓
SNS Topic
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

With 3 Lambda consumers processing the same CloudTrail events:

| Pattern | Lambda Invocations | Relative Cost |
|---------|-------------------|---------------|
| Direct S3 | Impossible (1 destination only) | - |
| **SNS Fan-Out** | ~N (batched) | **Lowest** |
| EventBridge | ~5N (1-by-1 per file) | ~5x higher Lambda cost |

**SNS maintains event batching, resulting in significantly fewer Lambda invocations than EventBridge.**

### SNS Pricing Summary

- **API Requests**: First 1 million free, then $0.50 per million
- **Lambda Delivery**: Free (no per-notification charge)
- **Data Transfer**: $0.09/GB (negligible for small S3 notifications)

> For current pricing, see [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/) and [AWS SNS Pricing](https://aws.amazon.com/sns/pricing/).

## Example

See complete working example in: [`examples/sns_fanout_configuration/`](../examples/sns_fanout_configuration/)

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

- Set `enable_s3_sns_fanout = true`
- Set `create_s3_sns_fanout_topic = true` (or provide external topic ARN)
- For Lambda subscribers: code must unwrap SNS envelope (CloudTrail-to-Slack does this automatically)
- For SQS/HTTP subscribers: optionally use `raw_message_delivery = true`
- Add unlimited subscribers to the SNS topic
- Enjoy event batching and low costs!
