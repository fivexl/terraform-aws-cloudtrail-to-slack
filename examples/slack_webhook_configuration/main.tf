provider "aws" {
  region = "eu-central-1"

  # Make it faster by skipping certain checks
  skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_credentials_validation = true
  skip_requesting_account_id  = true
}

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
    exclude_management_event_sources = [
      "kms.amazonaws.com",
    ]

    data_resource {
      type   = "AWS::Lambda::Function"
      values = ["arn:aws:lambda"]
    }
  }
}

module "cloudtrail_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "3.7.0"

  bucket = ""

  versioning = {
    enabled = true
  }

  logging = {
    target_bucket = module.logging_bucket.s3_bucket_id
    target_prefix = ""
  }

  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm = "AES256"
      }
    }
  }

  // S3 bucket-level Public Access Block configuration
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}



# We recommend storing the bot token in the SSM Parameter Store and not committing it to the repo. 
# Only one is required, but if there are more, it allows for sending notifications to different channels 
# for different environments, e.g. dev, prod.
data "aws_ssm_parameter" "default_hook" {
  name = "/cloudtrail-to-slack/default_hook"
}
data "aws_ssm_parameter" "dev_hook" {
  name = "/cloudtrail-to-slack/dev_hook"
}
data "aws_ssm_parameter" "prod_hook" {
  name = "/cloudtrail-to-slack/prod_hook"
}

locals {
  # EC2 Instance connect and EC2 eventNames
  ec2 = "SendSSHPublicKey"
  # Config eventNames
  config = "DeleteConfigRule,DeleteConfigurationRecorder,DeleteDeliveryChannel,DeleteEvaluationResults"

  # Catch CloudTrail changes
  cloudtrail = "DeleteTrail,StopLogging,UpdateTrail"

  # All eventNames
  events_to_track = "${local.cloudtrail},${local.ec2},${local.config}"

  # This rule is already in the default rules, but we want to demonstrate how to add your own rules.
  # Important! User-defined rules should not contain commas as they are passed to Lambda as a comma-separated string.
  cloudtrail_rules = [
    # Notify about all non-read actions done by root
    "event['userIdentity.type'] == 'Root' and not event['eventName'].startswith(('Get')) and not event['eventName'].startswith(('List')) and not event['eventName'].startswith(('Describe')) and not event['eventName'].startswith(('Head'))",
  ]
  cloudtrail_ignore_rules = [
    # Ignore all non-read actions done by root
    "event['userIdentity.type'] == 'Root' and not event['eventName'].startswith(('Get')) and not event['eventName'].startswith(('List')) and not event['eventName'].startswith(('Describe')) and not event['eventName'].startswith(('Head'))",
  ]
}

module "cloudtrail_to_slack" {
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "4.2.0"
  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id

  # String of comma-separated eventNames that you want to track
  events_to_track = local.events_to_track

  lambda_memory_size                    = 128
  lambda_timeout_seconds                = 10
  log_level                             = "INFO"
  push_access_denied_cloudwatch_metrics = true # Will push metrics to CloudWatch if access denied event is detected

  default_slack_hook_url = data.aws_ssm_parameter.default_hook.value

  # Optional, allows sending notifications to different Slack channels for different accounts.
  slack_app_configuration = [
    {
      "accounts" : ["111111111111"],
      "slack_hook_url" : data.aws_ssm_parameter.dev_hook.value
    },
    {
      "accounts" : ["222222222222"],
      "slack_hook_url" : data.aws_ssm_parameter.prod_hook.value
    }
  ]

  # If set to true, sends a notification to Slack when an object is removed from the CloudTrail S3 bucket
  s3_removed_object_notification = true

  # Whether to use default rules defined in src/rules.py or not
  use_default_rules = true

  # Optional user-defined rules
  rules        = join(",", local.rules)
  ignore_rules = join(",", local.ignore_rules)

  # Use a custom separator for complex rules containing commas
  # rules           = join(local.custom_separator, local.cloudtrail_rules)
  # rules_separator = local.custom_separator

  # If set to true, sends a notification to Slack when a rule evaluation error occurs. Useful for debugging rules.
  rule_evaluation_errors_to_slack = true

  # Optional, SNS notifications about CloudTrail events.
  # If aws_sns_topic_subscriptions and default_sns_topic_arn are not set, SNS notifications will be disabled.
  aws_sns_topic_subscriptions = {
    "email1@gmail.com" = "email"
    "email2@gmail.com" = "email"
  }
  default_sns_topic_arn = ""

  sns_configuration = [
    {
      "accounts" : ["111111111111"],
      "sns_topic_arn" : "sns_topic_arn_1"
    },
    {
      "accounts" : ["222222222222"],
      "sns_topic_arn" : "sns_topic_arn_2"
    }
  ]
}
