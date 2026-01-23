# EventBridge Support for CloudTrail to Slack

## Overview

This document explains the EventBridge support added to the CloudTrail to Slack Lambda function and the rationale behind this enhancement.

## The Problem: S3 Notification Limitations

### Single Destination Constraint

AWS S3 bucket notifications have a significant limitation: **each S3 event can only be sent to ONE destination** per event type. This creates a problem when you need multiple services to react to the same S3 events.

For example, if CloudTrail writes logs to an S3 bucket:
- You might want to send notifications to this Lambda (CloudTrail → Slack)
- You might also want to trigger another Lambda for log archival
- You might want to send events to EventBridge for other integrations

**With S3 notifications alone, you can only choose ONE of these destinations.**

### Traditional Architecture (Limited)

```
CloudTrail Logs → S3 Bucket → S3 Notification → Lambda (CloudTrail-to-Slack)
                              ❌ Can't add more destinations
```

## The Solution: EventBridge Integration

AWS EventBridge removes this limitation by allowing S3 events to be sent to EventBridge, which can then fan out to multiple destinations.

### New Architecture (Flexible)

```
CloudTrail Logs → S3 Bucket → EventBridge → Lambda (CloudTrail-to-Slack)
                                          → Lambda (Archive)
                                          → Lambda (Security Analysis)
                                          → SNS Topic
                                          → ... (unlimited targets)
```

## What We Added

### 1. Dual Event Format Support

The Lambda now supports **two event formats**:

#### S3 Notification Format (Original)
```json
{
  "Records": [{
    "eventName": "ObjectCreated:Put",
    "s3": {
      "bucket": {"name": "cloudtrail-bucket"},
      "object": {"key": "AWSLogs/.../log.json.gz"}
    },
    "userIdentity": {"accountId": "123456789012"}
  }]
}
```

#### EventBridge Format (New)
```json
{
  "version": "0",
  "detail-type": "Object Created",
  "source": "aws.s3",
  "account": "123456789012",
  "detail": {
    "bucket": {"name": "cloudtrail-bucket"},
    "object": {"key": "AWSLogs/.../log.json.gz"},
    "reason": "PutObject"
  }
}
```

### 2. Format Detection and Extraction

Added `extract_s3_info()` function that:
- Automatically detects the event format
- Extracts bucket name, object key, and account ID
- Maps EventBridge `detail-type` to S3 event names
- Raises errors for unrecognized formats (no silent failures)

### 3. Supported EventBridge detail-types

Per [AWS EventBridge S3 Events documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ev-events.html):

| EventBridge detail-type | Mapped to S3 event_name |
|------------------------|-------------------------|
| `"Object Created"`     | `"ObjectCreated:Put"`   |
| `"Object Deleted"`     | `"ObjectRemoved:Delete"` |

### 4. Unified Processing Pipeline

After format detection, both event types follow the same processing path:
1. Extract S3 bucket and key
2. Skip digest files
3. Fetch CloudTrail log from S3
4. Decompress and parse
5. Process CloudTrail events through rules
6. Send alerts to Slack

## Trade-offs: Invocation Frequency

### Important Consideration

⚠️ **EventBridge processes events ONE BY ONE**, while S3 notifications can batch multiple events into a single Lambda invocation.

#### S3 Notification Behavior
```
3 CloudTrail logs uploaded → 1 S3 Notification with Records array → 1 Lambda invocation
{
  "Records": [
    { "s3": {"object": {"key": "log1.json.gz"}} },
    { "s3": {"object": {"key": "log2.json.gz"}} },
    { "s3": {"object": {"key": "log3.json.gz"}} }
  ]
}
```
**Result: 1 Lambda invocation processes 3 files**

#### EventBridge Behavior
```
3 CloudTrail logs uploaded → 3 separate EventBridge events → 3 Lambda invocations

Event 1: { "detail": {"object": {"key": "log1.json.gz"}} }
Event 2: { "detail": {"object": {"key": "log2.json.gz"}} }
Event 3: { "detail": {"object": {"key": "log3.json.gz"}} }
```
**Result: 3 Lambda invocations, each processes 1 file**

### Cost and Performance Implications

| Aspect | S3 Notifications | EventBridge |
|--------|-----------------|-------------|
| **Lambda Invocations** | Fewer (batched) | More (1 per event) |
| **Lambda Costs** | Lower | Higher |
| **Processing Latency** | Slightly higher (batched) | Lower (immediate) |
| **Flexibility** | Single destination | Multiple destinations |
| **Event Filtering** | Limited | Advanced (EventBridge rules) |

### When to Use Each

**Use S3 Notifications when:**
- This is your ONLY consumer of S3 events
- You want to minimize Lambda invocations
- You don't need event filtering or routing

**Use EventBridge when:**
- You need multiple consumers for the same S3 events
- You want advanced event filtering
- You need event routing to multiple AWS services
- You want better event observability and auditing
- The increased Lambda invocations are acceptable

## Implementation Details

### Code Changes

1. **`src/main.py`**:
   - Added `extract_s3_info()` for format detection
   - Updated `lambda_handler()` to handle both formats
   - Refactored handlers to accept extracted info

2. **`src/slack_helpers.py`**:
   - Updated error notification handler for both formats

3. **`src/tests/test_event_formats.py`**:
   - Comprehensive tests for both formats
   - Tests for unknown format handling

### Backward Compatibility

✅ **100% backward compatible** - existing S3 notification integrations continue to work unchanged.

## Configuration Examples

### Option 1: S3 Notifications (Original)
```hcl
resource "aws_s3_bucket_notification" "cloudtrail" {
  bucket = aws_s3_bucket.cloudtrail.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.cloudtrail_to_slack.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "AWSLogs/"
    filter_suffix       = ".json.gz"
  }
}
```

### Option 2: EventBridge (New)
```hcl
# Enable EventBridge notifications on the bucket
resource "aws_s3_bucket_notification" "cloudtrail" {
  bucket      = aws_s3_bucket.cloudtrail.id
  eventbridge = true
}

# EventBridge rule to trigger Lambda
resource "aws_eventbridge_rule" "cloudtrail_logs" {
  name = "cloudtrail-logs-created"
  
  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.cloudtrail.id]
      }
      object = {
        key = [{
          prefix = "AWSLogs/"
          suffix = ".json.gz"
        }]
      }
    }
  })
}

resource "aws_eventbridge_target" "lambda" {
  rule = aws_eventbridge_rule.cloudtrail_logs.name
  arn  = aws_lambda_function.cloudtrail_to_slack.arn
}
```

## Testing

Run tests to verify both formats work:

```bash
cd src
.venv/bin/pytest -v

# Test specific format support
.venv/bin/pytest tests/test_event_formats.py -v
```

All tests validate:
- S3 notification format extraction
- EventBridge format extraction
- Unknown format error handling
- CloudTrail event processing

## References

- [AWS S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html)
- [AWS EventBridge S3 Events](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ev-events.html)
- [EventBridge Event Patterns](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-patterns.html)

## Summary

EventBridge support enables flexible event routing at the cost of increased Lambda invocations. Choose the approach that best fits your architecture:
- **S3 Notifications**: Simple, cost-effective, single destination
- **EventBridge**: Flexible, multiple destinations, higher invocation count

Both are fully supported and can be used interchangeably without code changes.
