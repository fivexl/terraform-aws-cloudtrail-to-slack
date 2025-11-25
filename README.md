[![FivexL](https://releases.fivexl.io/fivexlbannergit_new.png)](https://fivexl.io/#email-subscription)

### Want practical AWS infrastructure insights?

👉 [Subscribe to our newsletter](https://fivexl.io/#email-subscription) to get:

- Real stories from real AWS projects  
- No-nonsense DevOps tactics  
- Cost, security & compliance patterns that actually work  
- Expert guidance from engineers in the field

===========================================================================================

<!--- Use Markdown All In One Visual Studio Code extension to refresh TOC -->
- [Terraform module to deploy lambda that sends notifications about AWS CloudTrail events to Slack](#terraform-module-to-deploy-lambda-that-sends-notifications-about-aws-cloudtrail-events-to-slack)
  - [Why this module?](#why-this-module)
    - [Example message](#example-message)
- [Configurations](#configurations)
  - [Slack App (Recommended)](#slack-app-recommended)
  - [Slack Webhook](#slack-webhook)
  - [AWS SNS](#aws-sns)
- [Rules](#rules)
  - [Default rules:](#default-rules)
- [Cloudwatch metrics](#cloudwatch-metrics)
  - [User defined rules to match events](#user-defined-rules-to-match-events)
  - [Events to track](#events-to-track)
  - [Custom Separator for Rules](#custom-separator-for-rules)
  - [Ignore Rules](#ignore-rules)
- [About processing Cloudtrail events](#about-processing-cloudtrail-events)
- [Slack App configuration:](#slack-app-configuration)
- [Terraform specs](#terraform-specs)
  - [Requirements](#requirements)
  - [Providers](#providers)
  - [Modules](#modules)
  - [Resources](#resources)
  - [Inputs](#inputs)
  - [Outputs](#outputs)
  - [License](#license)
  - [Weekly review link](#weekly-review-link)

# Terraform module to deploy lambda that sends notifications about AWS CloudTrail events to Slack

## Why this module?

This module allows you to get notifications about:

- actions performed by root account (According to AWS best practices, you should use root account as little as possible and use SSO or IAM users)
- API calls that failed due to lack of permissions to do so (could be an indication of compromise or misconfiguration of your services/applications)
- console logins without MFA (Always use MFA for you IAM users or SSO)
- track a list of events that you might consider sensitive. Think IAM changes, network changes, data storage (S3, DBs) access changes. Though we recommend keeping that to a minimum to avoid alert fatigue
- define sophisticated rules to track user-defined conditions that are not covered by default rules (see examples below)
- send notifications to different Slack channels based on event account id

This module also allows you to gain insights into how many access-denied events are occurring in your AWS Organization by pushing metrics to CloudWatch.



### Example message

![Example message](https://releases.fivexl.io/example_message.png)


# Configurations

The module has three variants of notification delivery:

## Slack App (Recommended)

- Offers additional features, such as consolidating duplicate events into a single message thread. More features may be added in the future.
- The Slack app must have the `chat:write` permission.
- [Terraform configuration example](https://github.com/fivexl/terraform-aws-cloudtrail-to-slack/blob/master/examples/slack_app_configuration/main.tf)

## Slack Webhook

- Provides all the basic functionality of the module, but does not offer additional features and is not recommended by Slack.
- [Terraform configuration example](https://github.com/fivexl/terraform-aws-cloudtrail-to-slack/blob/master/examples/slack_webhook_configuration/main.tf)

## AWS SNS

- An optional feature that allows sending notifications to an AWS SNS topic. It can be used alongside either the Slack App or Slack Webhook.

All three variants of notification delivery support separating notifications into different Slack channels or SNS topics based on event account ID.

# Rules

Rules are python strings that are evaluated in the runtime and should return the bool value, if rule returns True, then notification will be sent to Slack.

This module comes with a set of predefined rules (default rules) that users can take advantage of:

## Default rules:

```python
# Notify if someone logged in without MFA but skip notification for SSO logins
default_rules.append('event["eventName"] == "ConsoleLogin" '
                     'and event.get("additionalEventData.MFAUsed", "") != "Yes" '
                     'and "assumed-role/AWSReservedSSO" not in event.get("userIdentity.arn", "")')
# Notify if someone is trying to do something they not supposed to be doing but do not notify
# about not logged in actions since there are a lot of scans for open buckets that generate noise
default_rules.append('event.get("errorCode", "").endswith(("UnauthorizedOperation"))')
default_rules.append('event.get("errorCode", "").startswith(("AccessDenied"))'
                     'and (event.get("userIdentity.accountId", "") != "ANONYMOUS_PRINCIPAL")')
# Notify about all non-read actions done by root
default_rules.append('event.get("userIdentity.type", "") == "Root" '
                     'and not event["eventName"].startswith(("Get", "List", "Describe", "Head"))')

# Catch CloudTrail disable events
default_rules.append('event["eventSource"] == "cloudtrail.amazonaws.com" '
                     'and event["eventName"] == "StopLogging"')
default_rules.append('event["eventSource"] == "cloudtrail.amazonaws.com" '
                     'and event["eventName"] == "UpdateTrail"')
default_rules.append('event["eventSource"] == "cloudtrail.amazonaws.com" '
                     'and event["eventName"] == "DeleteTrail"')
# Catch cloudtrail to slack lambda changes
default_rules.append('event["eventSource"] == "lambda.amazonaws.com" '
                     'and "responseElements.functionName" in event '
                     f'and event["responseElements.functionName"] == "{function_name}" '
                     'and event["eventName"].startswith(("UpdateFunctionConfiguration"))')
default_rules.append('event["eventSource"] == "lambda.amazonaws.com" '
                     'and "responseElements.functionName" in event '
                     f'and event["responseElements.functionName"] == "{function_name}" '
                     'and event["eventName"].startswith(("UpdateFunctionCode"))')
```

# Cloudwatch metrics
By default, every time Lambda receives an AccessDenied event, it pushes a `TotalAccessDeniedEvents` metric to CloudWatch. This metric is pushed for all access-denied events, including events ignored by rules. To separate ignored events from the total, the module also pushes a `TotalIgnoredAccessDeniedEvents` metric to CloudWatch. Both metrics are placed in the `CloudTrailToSlack/AccessDeniedEvents` namespace. This feature allows you to gain more insights into the number and dynamics of access-denied events in your AWS Organization.

This functionality can be disabled by setting push_access_denied_cloudwatch_metrics to false.

## User defined rules to match events
Rules must be provided as a list of strings, each separated by a comma or a custom separator. Each string is a Python expression that will be evaluated at runtime. By default, the module will send rule evaluation errors to Slack, but you can disable this by setting 'rule_evaluation_errors_to_slack' to 'false'.

Example of user-defined rules:
```hcl
locals = {
  rules = [
    # Catch CloudTrail disable events
    "event['eventSource'] == 'cloudtrail.amazonaws.com' and event['eventName'] == 'StopLogging'"
    "event['eventSource'] == 'cloudtrail.amazonaws.com' and event['eventName'] == 'UpdateTrail'"
    "event['eventSource'] == 'cloudtrail.amazonaws.com' and event['eventName'] == 'DeleteTrail'"
  ]
    rules = join(",", local.rules)
}
```

## Events to track
This is much simpler than rules. You just need a list of `eventNames` that you want to track. They will be evaluated as follows:
```python
f'"eventName" in event and event["eventName"] in {json.dumps(events_list)}'
```
Terraform example:
```hcl
local{
  # EC2 Instance connect and EC2 events
  ec2 = "SendSSHPublicKey"
  # Config
  config = "DeleteConfigRule,DeleteConfigurationRecorder,DeleteDeliveryChannel,DeleteEvaluationResults"
  # All events
  events_to_track = "${local.ec2},${local.config}"
}

events_to_track = local.events_to_track
```

## Custom Separator for Rules

By default, the module expects rules to be separated by commas. However, if you have complex rules that contain commas, you can use a custom separator by providing the `rules_separator` variable. Here's how:

```hcl
locals {
  cloudtrail_rules = [
      ...
    ]
  custom_separator = "%"
}

module "cloudtrail_to_slack" {
  ...
  rules = join(local.custom_separator, local.cloudtrail_rules)
  rules_separator = local.custom_separator
}
```

## Ignore Rules

**Note:** We recommend addressing alerts rather than ignoring them. However, if it's impossible to resolve an alert, you can suppress events by providing ignore rules.

Ignore rules have the same format as the rules, but they are evaluated before them. So, if an ignore rule returns `True`, then the event will be ignored and no further processing will be done.

```hcl
locals {
  ignore_rules = [
    # Ignore events from the account "111111111".
    "'userIdentity.accountId' in event and event['userIdentity.accountId'] == '11111111111'",
  ]
  ignore_rules = join(",", local.ignore_rules)
}
```

# About processing Cloudtrail events

CloudTrail event (see format [here](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference.html), or find more examples in [src/tests/test_events.json](https://github.com/fivexl/terraform-aws-cloudtrail-to-slack/blob/master/src/tests/test_events.json)) is flattened before processing and should be referenced as `event` variable
So, for instance, to access ARN from the event below, you should use the notation `userIdentity.arn`

```json
{
  "eventVersion": "1.05",
  "userIdentity": {
    "type": "IAMUser",
    "principalId": "XXXXXXXXXXX",
    "arn": "arn:aws:iam::XXXXXXXXXXX:user/xxxxxxxx",
    "accountId": "XXXXXXXXXXX",
    "userName": "xxxxxxxx"
  },
  "eventTime": "2019-07-03T16:14:51Z",
  "eventSource": "signin.amazonaws.com",
  "eventName": "ConsoleLogin",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "83.41.208.104",
  "userAgent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0",
  "requestParameters": null,
  "responseElements": {
    "ConsoleLogin": "Success"
  },
  "additionalEventData": {
    "LoginTo": "https://console.aws.amazon.com/ec2/v2/home?XXXXXXXXXXX",
    "MobileVersion": "No",
    "MFAUsed": "No"
  },
  "eventID": "0e4d136e-25d4-4d92-b2b2-8a9fe1e3f1af",
  "eventType": "AwsConsoleSignIn",
  "recipientAccountId": "XXXXXXXXXXX"
}
```
# Slack App configuration:
1. Go to https://api.slack.com/
2. Click create an app
3. Click From an app manifest
4. Select workspace, click next
5. Choose yaml for app manifest format
```
display_information:
  name: CloudtrailToSlack
  description: Notifications about Cloudtrail events to Slack.
  background_color: "#3d3d0e"
features:
  bot_user:
    display_name: Cloudtrail to Slack
    always_online: false
oauth_config:
  scopes:
    bot:
      - chat:write
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```
6. Check permissions and click create
7. Click install to workspace
8. Copy Signing Secret # for slack_signing_secret module input
9. Copy Bot User OAuth Token # for slack_bot_token module input


# Terraform specs

<!-- BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 0.13.1 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 4.8 |
| <a name="requirement_external"></a> [external](#requirement\_external) | >= 1.0 |
| <a name="requirement_local"></a> [local](#requirement\_local) | >= 1.0 |
| <a name="requirement_null"></a> [null](#requirement\_null) | >= 2.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | 5.8.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_cloudtrail_to_slack_dynamodb_table"></a> [cloudtrail\_to\_slack\_dynamodb\_table](#module\_cloudtrail\_to\_slack\_dynamodb\_table) | terraform-aws-modules/dynamodb-table/aws | 3.3.0 |
| <a name="module_lambda"></a> [lambda](#module\_lambda) | terraform-aws-modules/lambda/aws | 4.18.0 |

## Resources

| Name | Type |
|------|------|
| [aws_lambda_permission.s3](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_s3_bucket_notification.bucket_notification](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_notification) | resource |
| [aws_sns_topic.events_to_sns](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic) | resource |
| [aws_sns_topic_subscription.events_to_sns](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sns_topic_subscription) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_iam_policy_document.s3](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_kms_key.cloudtrail](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/kms_key) | data source |
| [aws_partition.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/partition) | data source |
| [aws_region.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/region) | data source |
| [aws_s3_bucket.cloudtrail](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/s3_bucket) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_aws_sns_topic_subscriptions"></a> [aws\_sns\_topic\_subscriptions](#input\_aws\_sns\_topic\_subscriptions) | Map of endpoints to protocols for SNS topic subscriptions. If not set, sns notifications will not be sent. | `map(string)` | `{}` | no |
| <a name="input_cloudtrail_logs_kms_key_id"></a> [cloudtrail\_logs\_kms\_key\_id](#input\_cloudtrail\_logs\_kms\_key\_id) | Alias, key id or key arn of the KMS Key that used for CloudTrail events | `string` | `""` | no |
| <a name="input_cloudtrail_logs_s3_bucket_name"></a> [cloudtrail\_logs\_s3\_bucket\_name](#input\_cloudtrail\_logs\_s3\_bucket\_name) | Name of the CloudWatch log s3 bucket that contains CloudTrail events | `string` | n/a | yes |
| <a name="input_configuration"></a> [configuration](#input\_configuration) | Allows the configuration of the Slack webhook URL per account(s). This enables the separation of events from different accounts into different channels, which is useful in the context of an AWS organization. | <pre>list(object({<br>    accounts       = list(string)<br>    slack_hook_url = string<br>  }))</pre> | `null` | no |
| <a name="input_dead_letter_target_arn"></a> [dead\_letter\_target\_arn](#input\_dead\_letter\_target\_arn) | The ARN of an SNS topic or SQS queue to notify when an invocation fails. | `string` | `null` | no |
| <a name="input_default_slack_channel_id"></a> [default\_slack\_channel\_id](#input\_default\_slack\_channel\_id) | The Slack channel ID to be used if the AWS account ID does not match any account ID in the configuration variable. | `string` | `null` | no |
| <a name="input_default_slack_hook_url"></a> [default\_slack\_hook\_url](#input\_default\_slack\_hook\_url) | The Slack incoming webhook URL to be used if the AWS account ID does not match any account ID in the configuration variable. | `string` | `null` | no |
| <a name="input_default_sns_topic_arn"></a> [default\_sns\_topic\_arn](#input\_default\_sns\_topic\_arn) | Default topic for all notifications. If not set, sns notifications will not be sent. | `string` | `null` | no |
| <a name="input_dynamodb_table_name"></a> [dynamodb\_table\_name](#input\_dynamodb\_table\_name) | Name of the dynamodb table, it would not be created if slack\_bot\_token is not set. | `string` | `"fivexl-cloudtrail-to-slack-table"` | no |
| <a name="input_dynamodb_time_to_live"></a> [dynamodb\_time\_to\_live](#input\_dynamodb\_time\_to\_live) | How long to keep cloudtrail events in dynamodb table, for collecting similar events in thread of one message | `number` | `900` | no |
| <a name="input_events_to_track"></a> [events\_to\_track](#input\_events\_to\_track) | Comma-separated list events to track and report | `string` | `""` | no |
| <a name="input_function_name"></a> [function\_name](#input\_function\_name) | Lambda function name | `string` | `"fivexl-cloudtrail-to-slack"` | no |
| <a name="input_ignore_rules"></a> [ignore\_rules](#input\_ignore\_rules) | Comma-separated list of rules to ignore events if you need to suppress something. Will be applied before rules and default\_rules | `string` | `""` | no |
| <a name="input_lambda_build_in_docker"></a> [lambda\_build\_in\_docker](#input\_lambda\_build\_in\_docker) | Whether to build dependencies in Docker | `bool` | `false` | no |
| <a name="input_lambda_logs_retention_in_days"></a> [lambda\_logs\_retention\_in\_days](#input\_lambda\_logs\_retention\_in\_days) | Controls for how long to keep lambda logs. | `number` | `30` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | Amount of memory in MB your Lambda Function can use at runtime. Valid value between 128 MB to 10,240 MB (10 GB), in 64 MB increments. | `number` | `256` | no |
| <a name="input_lambda_recreate_missing_package"></a> [lambda\_recreate\_missing\_package](#input\_lambda\_recreate\_missing\_package) | Description: Whether to recreate missing Lambda package if it is missing locally or not | `bool` | `true` | no |
| <a name="input_lambda_timeout_seconds"></a> [lambda\_timeout\_seconds](#input\_lambda\_timeout\_seconds) | Controls lambda timeout setting. | `number` | `30` | no |
| <a name="input_log_level"></a> [log\_level](#input\_log\_level) | Log level for lambda function | `string` | `"INFO"` | no |
| <a name="input_push_access_denied_cloudwatch_metrics"></a> [push\_access\_denied\_cloudwatch\_metrics](#input\_push\_access\_denied\_cloudwatch\_metrics) | If true, CloudWatch metrics will be pushed for all access denied events, including events ignored by rules. | `bool` | `true` | no |
| <a name="input_rule_evaluation_errors_to_slack"></a> [rule\_evaluation\_errors\_to\_slack](#input\_rule\_evaluation\_errors\_to\_slack) | If rule evaluation error occurs, send notification to slack | `bool` | `true` | no |
| <a name="input_rules"></a> [rules](#input\_rules) | Comma-separated list of rules to track events if just event name is not enough | `string` | `""` | no |
| <a name="input_rules_separator"></a> [rules\_separator](#input\_rules\_separator) | Custom rules separator. Can be used if there are commas in the rules | `string` | `","` | no |
| <a name="input_s3_notification_filter_prefix"></a> [s3\_notification\_filter\_prefix](#input\_s3\_notification\_filter\_prefix) | S3 notification filter prefix | `string` | `"AWSLogs/"` | no |
| <a name="input_s3_removed_object_notification"></a> [s3\_removed\_object\_notification](#input\_s3\_removed\_object\_notification) | If object was removed from cloudtrail bucket, send notification to slack | `bool` | `true` | no |
| <a name="input_slack_app_configuration"></a> [slack\_app\_configuration](#input\_slack\_app\_configuration) | Allows the configuration of the Slack app per account(s). This enables the separation of events from different accounts into different channels, which is useful in the context of an AWS organization. | <pre>list(object({<br>    accounts         = list(string)<br>    slack_channel_id = string<br>  }))</pre> | `null` | no |
| <a name="input_slack_bot_token"></a> [slack\_bot\_token](#input\_slack\_bot\_token) | The Slack bot token used for sending messages to Slack. | `string` | `null` | no |
| <a name="input_sns_configuration"></a> [sns\_configuration](#input\_sns\_configuration) | Allows the configuration of the SNS topic per account(s). | <pre>list(object({<br>    accounts      = list(string)<br>    sns_topic_arn = string<br>  }))</pre> | `null` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to attach to resources | `map(string)` | `{}` | no |
| <a name="input_use_default_rules"></a> [use\_default\_rules](#input\_use\_default\_rules) | Should default rules be used | `bool` | `true` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | The ARN of the Lambda Function |
<!-- END OF PRE-COMMIT-TERRAFORM DOCS HOOK -->

## License

Apache 2 Licensed. See LICENSE for full details.

## Weekly review link

- [Review](https://github.com/fivexl/terraform-aws-cloudtrail-to-slack/compare/main@%7B7day%7D...main)
- [Review branch-based review](https://github.com/fivexl/terraform-aws-cloudtrail-to-slack/compare/review...main)
