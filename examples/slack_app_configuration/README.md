# Complete Example of Slack App Configuration

This example demonstrates how to use the **Slack App** (bot token) configuration instead of webhooks. The Slack App approach provides advanced features like message threading for better organization.

## Slack App vs Webhook

| Feature | Webhook | Slack App (Bot Token) |
|---------|---------|----------------------|
| **Message Threading** | ❌ No | ✅ Yes - groups similar events |
| **DynamoDB Required** | ❌ No | ✅ Yes - for thread tracking |
| **Setup Complexity** | Easy | Moderate |
| **Account Routing** | `configuration` | `slack_app_configuration` |
| **Channel Configuration** | `slack_hook_url` | `slack_channel_id` |
| **Cost** | Free | Free + DynamoDB ($0.25/month) |

## Prerequisites

### 1. Create a Slack App

1. Go to [Slack API](https://api.slack.com/apps)
2. Click **"Create New App"** → **"From scratch"**
3. Name it (e.g., "CloudTrail Alerts")
4. Select your workspace

### 2. Configure Permissions

Add these **Bot Token Scopes** under "OAuth & Permissions":
- `chat:write` - Post messages to channels
- `chat:write.public` - Post to public channels without joining

### 3. Install App to Workspace

1. Click **"Install to Workspace"**
2. Authorize the app
3. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### 4. Get Channel IDs

For each Slack channel you want to use:
1. Right-click the channel → "View channel details"
2. Scroll down to copy the **Channel ID** (e.g., `C059WBL1MEX`)

### 5. Store Bot Token in SSM Parameter Store

```bash
aws ssm put-parameter \
  --name "/cloudtrail-to-slack/slack-bot-token" \
  --value "xoxb-YOUR-BOT-TOKEN" \
  --type "SecureString" \
  --description "Slack bot token for CloudTrail alerts"
```

## Configuration Options

### Basic Configuration

Minimal setup with a single channel for all accounts:

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-bucket"
  
  # Slack App Configuration
  slack_bot_token          = data.aws_ssm_parameter.slack_bot_token.value
  default_slack_channel_id = "C059WBL1MEX"  # Your default channel ID
  
  # DynamoDB for threading (required for Slack App)
  dynamodb_table_name   = "cloudtrail-to-slack-threads"
  dynamodb_time_to_live = 900  # 15 minutes
  
  use_default_rules = true
}
```

### Multi-Account Configuration

Route different AWS accounts to different Slack channels using `slack_app_configuration`:

```hcl
module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  cloudtrail_logs_s3_bucket_name = "my-cloudtrail-bucket"
  
  # Slack App Configuration
  slack_bot_token          = data.aws_ssm_parameter.slack_bot_token.value
  default_slack_channel_id = "C_DEFAULT"  # Fallback channel
  
  # Route specific accounts to specific channels
  slack_app_configuration = [
    {
      accounts         = ["111111111111", "222222222222"]  # Production accounts
      slack_channel_id = "C_PROD_ALERTS"
    },
    {
      accounts         = ["333333333333"]  # Development account
      slack_channel_id = "C_DEV_ALERTS"
    },
    {
      accounts         = ["444444444444"]  # Security account
      slack_channel_id = "C_SECURITY"
    }
  ]
  
  # DynamoDB for threading
  dynamodb_table_name   = "cloudtrail-to-slack-threads"
  dynamodb_time_to_live = 900
  
  use_default_rules = true
}
```

## Message Threading

The Slack App configuration uses DynamoDB to track similar events and group them in threads:

```
Channel: #prod-alerts
├─ 🔴 user@example.com called ConsoleLogin (without MFA)
│  └─ 🔁 user@example.com called ConsoleLogin (without MFA)  [in thread]
│  └─ 🔁 user@example.com called ConsoleLogin (without MFA)  [in thread]
└─ ⚠️  admin@example.com called DeleteBucket but failed (AccessDenied)
```

### How Threading Works

1. **Event Occurs**: CloudTrail logs an event
2. **Hash Calculation**: Lambda creates a hash from `userIdentity` + `eventName`
3. **DynamoDB Lookup**: Checks if similar event exists (within TTL)
4. **Thread Decision**:
   - **New Event**: Posts to channel, stores `thread_ts` in DynamoDB
   - **Similar Event**: Posts as reply in existing thread
5. **TTL Expiration**: After TTL (default 15 min), new thread is created

### DynamoDB Table Structure

The module automatically creates a DynamoDB table with:
- **Hash Key**: `principal_structure_and_action_hash` (SHA256)
- **Attributes**: `thread_ts`, `ttl`
- **TTL**: Automatically deletes expired entries
- **Cost**: ~$0.25/month for typical usage

## Complete Example Walkthrough

This example includes:

### 1. CloudTrail Setup
```hcl
resource "aws_cloudtrail" "main" {
  name                          = "main"
  s3_bucket_name                = module.cloudtrail_bucket.s3_bucket_id
  include_global_service_events = true
  is_multi_region_trail         = true
  is_organization_trail         = true  # For AWS Organizations
  enable_log_file_validation    = true
  
  event_selector {
    read_write_type           = "All"
    include_management_events = true
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

### 3. Slack Bot Token from SSM
```hcl
data "aws_ssm_parameter" "slack_bot_token" {
  name = "/cloudtrail-to-slack/slack-bot-token"
}
```

### 4. CloudTrail to Slack Module
```hcl
module "cloudtrail_to_slack" {
  source  = "fivexl/cloudtrail-to-slack/aws"
  version = "4.2.0"
  
  cloudtrail_logs_s3_bucket_name = module.cloudtrail_bucket.s3_bucket_id
  
  # Slack App Configuration
  slack_bot_token          = data.aws_ssm_parameter.slack_bot_token.value
  default_slack_channel_id = "C059WBL1MEX"
  
  # Multi-account routing
  slack_app_configuration = [
    {
      accounts         = ["111111111111"]
      slack_channel_id = "C_ACCOUNT_1"
    },
    {
      accounts         = ["222222222222"]
      slack_channel_id = "C_ACCOUNT_2"
    }
  ]
  
  # DynamoDB for threading
  dynamodb_table_name   = "fivexl-cloudtrail-to-slack-table"
  dynamodb_time_to_live = 900  # 15 minutes
  
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
  
  # Optional: SNS fan-out for other consumers
  aws_sns_topic_subscriptions = {
    "security@example.com" = "email"
  }
  
  sns_configuration = [
    {
      accounts       = ["111111111111"]
      sns_topic_arn  = "arn:aws:sns:us-east-1:111111111111:security-alerts"
    }
  ]
}
```

## Custom Rules Example

```hcl
locals {
  # Define custom rules
  rules = [
    # Alert on EC2 instance terminations
    "event['eventName'] == 'TerminateInstances'",
    
    # Alert on RDS database deletions
    "event['eventName'] == 'DeleteDBInstance'",
    
    # Alert on S3 bucket deletions
    "event['eventName'] == 'DeleteBucket'",
  ]
  
  # Define ignore rules
  ignore_rules = [
    # Ignore read-only actions by automation role
    "event.get('userIdentity.sessionContext.sessionIssuer.userName', '') == 'AutomationRole'",
  ]
}

module "cloudtrail_to_slack" {
  source = "fivexl/cloudtrail-to-slack/aws"
  
  # ... other configuration ...
  
  use_default_rules = true
  rules             = join(",", local.rules)
  ignore_rules      = join(",", local.ignore_rules)
}
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

After deployment, test the integration:

1. **Trigger a test event** in AWS (e.g., describe EC2 instances as root user)
2. **Check CloudWatch Logs** for the Lambda function
3. **Verify Slack message** appears in the configured channel
4. **Test threading** by triggering the same event multiple times within 15 minutes

## Monitoring

### CloudWatch Metrics

The module publishes custom metrics:
- `CloudTrailToSlack/AccessDeniedEvents/TotalAccessDeniedEvents`
- `CloudTrailToSlack/AccessDeniedEvents/TotalIgnoredAccessDeniedEvents`

### CloudWatch Logs

Check Lambda logs:
```bash
aws logs tail /aws/lambda/cloudtrail-to-slack --follow
```

## Troubleshooting

### Messages not appearing in Slack

1. **Check Lambda logs** for errors
2. **Verify bot token** is correct
3. **Check channel ID** is correct
4. **Verify bot permissions** (`chat:write`, `chat:write.public`)
5. **Ensure bot is added** to private channels (or use public channels)

### Threading not working

1. **Check DynamoDB table** exists
2. **Verify TTL** is configured correctly
3. **Check Lambda logs** for DynamoDB errors
4. **Verify IAM permissions** for DynamoDB access

### Rule evaluation errors

1. **Enable** `rule_evaluation_errors_to_slack = true`
2. **Check Slack** for error messages
3. **Review rule syntax** in CloudWatch Logs
4. **Test rules** locally with sample events

## Cost Estimation

For a typical setup with 10,000 CloudTrail events per month:

- **Lambda**: ~$0.20/month
- **DynamoDB**: ~$0.25/month (1GB storage, 1M reads)
- **S3**: Based on CloudTrail log size
- **Slack**: Free

**Total: ~$0.45/month** (excluding S3)

## Security Best Practices

1. ✅ Store bot token in SSM Parameter Store (encrypted)
2. ✅ Use IAM roles with least privilege
3. ✅ Enable CloudTrail log file validation
4. ✅ Encrypt S3 bucket with SSE
5. ✅ Enable S3 bucket versioning
6. ✅ Block public access on S3 bucket
7. ✅ Use DynamoDB encryption at rest
8. ✅ Review Slack channel permissions

## See Also

- [Main Module Documentation](../../README.md)
- [Slack Webhook Example](../slack_webhook_configuration/)
- [SNS Fan-Out Example](../sns_fanout_configuration/)
- [Default Rules Reference](../../src/rules.py)