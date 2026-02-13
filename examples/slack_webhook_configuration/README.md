# Complete Example of Slack Webhook Configuration

This example demonstrates how to use **Slack Incoming Webhooks** for CloudTrail notifications. This is the simpler approach that doesn't require DynamoDB or message threading.

## Webhook vs Slack App

| Feature | Webhook | Slack App (Bot Token) |
|---------|---------|----------------------|
| **Message Threading** | ❌ No | ✅ Yes - groups similar events |
| **DynamoDB Required** | ❌ No | ✅ Yes - for thread tracking |
| **Setup Complexity** | Easy | Moderate |
| **Account Routing** | `configuration` | `slack_app_configuration` |
| **Channel Configuration** | `slack_hook_url` | `slack_channel_id` |
| **Cost** | Free | Free + DynamoDB ($0.25/month) |
| **Best For** | Simple alerts | Organized, high-volume alerts |

## Prerequisites

### 1. Create Slack Incoming Webhooks

For each channel you want to send notifications to:

1. Go to your Slack workspace
2. Navigate to **Settings & administration** → **Manage apps**
3. Search for **"Incoming Webhooks"** and add to Slack
4. Click **"Add New Webhook to Workspace"**
5. Select the channel
6. Copy the **Webhook URL** (e.g., `https://hooks.slack.com/services/T00/B00/XXX`)

### 2. Store Webhook URLs in SSM Parameter Store

```bash
# Default webhook
aws ssm put-parameter \
  --name "/cloudtrail-to-slack/default-hook" \
  --value "https://hooks.slack.com/services/YOUR/DEFAULT/WEBHOOK" \
  --type "SecureString" \
  --description "Default Slack webhook for CloudTrail alerts"

# Development account webhook
aws ssm put-parameter \
  --name "/cloudtrail-to-slack/dev-hook" \
  --value "https://hooks.slack.com/services/YOUR/DEV/WEBHOOK" \
  --type "SecureString"

# Production account webhook
aws ssm put-parameter \
  --name "/cloudtrail-to-slack/prod-hook" \
  --value "https://hooks.slack.com/services/YOUR/PROD/WEBHOOK" \
  --type "SecureString"
```

## Configuration Options

### Basic Configuration

Minimal setup with a single webhook for all accounts:

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-bucket"
  
  # Slack Webhook Configuration
  default_slack_hook_url = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  
  use_default_rules = true
}
```

### Multi-Account Configuration

Route different AWS accounts to different Slack webhooks (channels) using `configuration`:

```hcl
# Retrieve webhook URLs from SSM Parameter Store
data "aws_ssm_parameter" "default_hook" {
  name = "/cloudtrail-to-slack/default-hook"
}

data "aws_ssm_parameter" "dev_hook" {
  name = "/cloudtrail-to-slack/dev-hook"
}

data "aws_ssm_parameter" "prod_hook" {
  name = "/cloudtrail-to-slack/prod-hook"
}

module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-bucket"
  
  # Default webhook (fallback)
  default_slack_hook_url = data.aws_ssm_parameter.default_hook.value
  
  # Route specific accounts to specific webhooks
  configuration = [
    {
      accounts       = ["111111111111"]  # Development account
      slack_hook_url = data.aws_ssm_parameter.dev_hook.value
    },
    {
      accounts       = ["222222222222", "333333333333"]  # Production accounts
      slack_hook_url = data.aws_ssm_parameter.prod_hook.value
    }
  ]
  
  use_default_rules = true
}
```

## Complete Example Walkthrough

This example includes:

### 1. CloudTrail Setup
```hcl
resource "aws_cloudtrail" "main" {
  name                          = "main"
  s3_bucket_name                = module.cloudtrail_bucket.s3_bucket_id
  include_global_service_events = true
  is_multi_region_trail         = true
  is_organization_trail         = true
  enable_log_file_validation    = true
  
  event_selector {
    read_write_type           = "All"
    include_management_events = true
    exclude_management_event_sources = ["kms.amazonaws.com"]
  }
}
```

### 2. CloudTrail S3 Bucket
```hcl
module "cloudtrail_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "3.7.0"
  
  bucket = "my-org-cloudtrail-logs"
  
  versioning = { enabled = true }
  
  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm = "AES256"
      }
    }
  }
  
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
```

### 3. Webhook URLs from SSM
```hcl
data "aws_ssm_parameter" "default_hook" {
  name = "/cloudtrail-to-slack/default-hook"
}

data "aws_ssm_parameter" "dev_hook" {
  name = "/cloudtrail-to-slack/dev-hook"
}

data "aws_ssm_parameter" "prod_hook" {
  name = "/cloudtrail-to-slack/prod-hook"
}
```

### 4. CloudTrail to Slack Module
```hcl
module "cloudtrail_to_slack" {
  source  = "fivexl/cloudtrail-to-slack/aws"
  version = "4.2.0"
  
  cloudtrail_logs_s3_bucket_name = module.cloudtrail_bucket.s3_bucket_id
  
  # Slack Webhook Configuration
  default_slack_hook_url = data.aws_ssm_parameter.default_hook.value
  
  # Multi-account webhook routing
  configuration = [
    {
      accounts       = ["111111111111"]
      slack_hook_url = data.aws_ssm_parameter.dev_hook.value
    },
    {
      accounts       = ["222222222222"]
      slack_hook_url = data.aws_ssm_parameter.prod_hook.value
    }
  ]
  
  # Rules
  use_default_rules               = true
  events_to_track                 = "DeleteTrail,StopLogging,UpdateTrail"
  rule_evaluation_errors_to_slack = true
  
  # Lambda settings
  lambda_memory_size                    = 128
  lambda_timeout_seconds                = 10
  log_level                             = "INFO"
  push_access_denied_cloudwatch_metrics = true
  
  # S3 removed object notifications
  s3_removed_object_notification = true
}
```

## Custom Rules Example

```hcl
locals {
  # EC2 events to track
  ec2_events = "SendSSHPublicKey,TerminateInstances"
  
  # Config events to track
  config_events = "DeleteConfigRule,DeleteConfigurationRecorder"
  
  # CloudTrail events to track
  cloudtrail_events = "DeleteTrail,StopLogging,UpdateTrail"
  
  # Combined events
  events_to_track = "${local.cloudtrail_events},${local.ec2_events},${local.config_events}"
  
  # Custom rules (no commas inside each rule!)
  rules = [
    # Alert on all root user non-read actions
    "event['userIdentity.type'] == 'Root' and not event['eventName'].startswith(('Get', 'List', 'Describe', 'Head'))",
    
    # Alert on S3 bucket policy changes
    "event['eventName'] == 'PutBucketPolicy'",
  ]
  
  # Ignore rules
  ignore_rules = [
    # Ignore specific automation user
    "event.get('userIdentity.userName', '') == 'terraform-automation'",
  ]
}

module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  # ... other configuration ...
  
  events_to_track = local.events_to_track
  use_default_rules = true
  rules             = join(",", local.rules)
  ignore_rules      = join(",", local.ignore_rules)
}
```

## Message Format

Webhook messages appear in Slack like this:

```
🔴 arn:aws:iam::123456789012:user/alice called ConsoleLogin
⚠️ Login without MFA! ⚠️

requestParameters:
{
  "userName": "alice"
}

Time: 2026-01-24 12:00:00 UTC
Id: abc-123-def-456
Account Id: 123456789012
Event location in s3:
AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/24/file.json.gz
```

## Deployment

```bash
# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the configuration
terraform apply
```

## Testing

After deployment:

1. **Trigger a test event** in AWS (e.g., console login without MFA)
2. **Check CloudWatch Logs** for the Lambda function:
   ```bash
   aws logs tail /aws/lambda/cloudtrail-to-slack --follow
   ```
3. **Verify Slack message** appears in the configured channel

## Monitoring

### CloudWatch Metrics

If enabled, the module publishes:
- `CloudTrailToSlack/AccessDeniedEvents/TotalAccessDeniedEvents`
- `CloudTrailToSlack/AccessDeniedEvents/TotalIgnoredAccessDeniedEvents`

### CloudWatch Alarms

Create alarms for high AccessDenied rates:

```hcl
resource "aws_cloudwatch_metric_alarm" "access_denied_high" {
  alarm_name          = "cloudtrail-access-denied-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "TotalAccessDeniedEvents"
  namespace           = "CloudTrailToSlack/AccessDeniedEvents"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "High number of AccessDenied events"
}
```

## Troubleshooting

### Messages not appearing in Slack

1. **Check Lambda logs** for errors:
   ```bash
   aws logs tail /aws/lambda/cloudtrail-to-slack --follow
   ```
2. **Verify webhook URL** is correct
3. **Test webhook** manually:
   ```bash
   curl -X POST -H 'Content-type: application/json' \
     --data '{"text":"Test message"}' \
     YOUR_WEBHOOK_URL
   ```
4. **Check S3 bucket notifications** are configured

### Rule evaluation errors

Enable error notifications:
```hcl
rule_evaluation_errors_to_slack = true
```

Then check Slack for error messages with rule details.

### High Lambda costs

1. **Reduce log retention**:
   ```hcl
   cloudwatch_log_retention = 7  # days
   ```
2. **Increase memory** for faster execution (might reduce costs):
   ```hcl
   lambda_memory_size = 256  # MB
   ```

## Cost Estimation

For 10,000 CloudTrail events per month:

- **Lambda**: ~$0.20/month
- **S3**: Based on log size (~$1-5/month)
- **CloudWatch Logs**: ~$0.50/month
- **Slack**: Free

**Total: ~$1-6/month**

## Upgrading to Slack App

To get message threading, upgrade to Slack App configuration:

1. Create a Slack App (see [Slack App example](../slack_app_configuration/))
2. Replace webhook configuration:
   ```hcl
   # Remove these:
   # default_slack_hook_url = "..."
   # configuration = [...]
   
   # Add these:
   slack_bot_token          = "xoxb-your-bot-token"
   default_slack_channel_id = "C123456"
   slack_app_configuration = [
     {
       accounts         = ["111111111111"]
       slack_channel_id = "C_DEV"
     }
   ]
   
   # Add DynamoDB:
   dynamodb_table_name   = "cloudtrail-threads"
   dynamodb_time_to_live = 900
   ```

## Security Best Practices

1. ✅ Store webhook URLs in SSM Parameter Store (encrypted)
2. ✅ Use IAM roles with least privilege
3. ✅ Enable CloudTrail log file validation
4. ✅ Encrypt S3 bucket with SSE
5. ✅ Enable S3 bucket versioning
6. ✅ Block public access on S3 bucket
7. ✅ Rotate webhook URLs periodically
8. ✅ Use separate webhooks for different environments
9. ✅ Limit webhook URL access to authorized personnel

## See Also

- [Main Module Documentation](../../README.md)
- [Slack App Example](../slack_app_configuration/) - For message threading
- [SNS Fan-Out Example](../sns_fanout_configuration/) - For multiple consumers
- [Default Rules Reference](../../src/rules.py)