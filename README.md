[![FivexL](https://releases.fivexl.io/fivexlbannergit.jpg)](https://fivexl.io/)

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
  - [User defined rules to match events](#user-defined-rules-to-match-events)
  - [Events to track](#events-to-track)
  - [Custom Separator for Rules](#custom-separator-for-rules)
  - [Ignore Rules](#ignore-rules)
- [About processing Cloudtrail events](#about-processing-cloudtrail-events)
- [Terraform specs](#terraform-specs)
  - [Requirements](#requirements)
  - [Providers](#providers)
  - [Modules](#modules)
  - [Resources](#resources)
  - [Inputs](#inputs)
  - [Outputs](#outputs)
  - [License](#license)

# Terraform module to deploy lambda that sends notifications about AWS CloudTrail events to Slack

## Why this module?

This module allows you to get notifications about:

- actions performed by root account (According to AWS best practices, you should use root account as little as possible and use SSO or IAM users)
- API calls that failed due to lack of permissions to do so (could be an indication of compromise or misconfiguration of your services/applications)
- console logins without MFA (Always use MFA for you IAM users or SSO)
- track a list of events that you might consider sensitive. Think IAM changes, network changes, data storage (S3, DBs) access changes. Though we recommend keeping that to a minimum to avoid alert fatigue
- define sophisticated rules to track user-defined conditions that are not covered by default rules (see examples below)
- send notifications to different Slack channels based on event account id

### Example message

![Example message](https://releases.fivexl.io/example_message.png)


# Configurations

The module has three variants of notification delivery:

## Slack App (Recommended)

- Offers additional features, such as consolidating duplicate events into a single message thread. More features may be added in the future.
- The Slack app must have the `chat:write` permission.

## Slack Webhook

- Provides all the basic functionality of the module, but does not offer additional features and is not recommended by Slack.

## AWS SNS

- An optional feature that allows sending notifications to an AWS SNS topic. It can be used alongside either the Slack App or Slack Webhook.

All three variants of notification delivery support separating notifications into different Slack channels or SNS topics based on event account ID.

Complete Terraform examples can be found in the examples directory of this repository.


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

CloudTrail event (see format [here](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference.html), or find more examples in src/tests/test_events.json) is flattened before processing and should be referenced as `event` variable
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
| <a name="provider_aws"></a> [aws](#provider\_aws) | 4.55.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_lambda"></a> [lambda](#module\_lambda) | terraform-aws-modules/lambda/aws | 4.10.1 |

## Resources

| Name | Type |
|------|------|
| [aws_lambda_permission.s3](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_permission) | resource |
| [aws_s3_bucket_notification.bucket_notification](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_notification) | resource |
| [aws_caller_identity.current](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity) | data source |
| [aws_iam_policy_document.s3](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/iam_policy_document) | data source |
| [aws_kms_key.cloudtrail](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/kms_key) | data source |
| [aws_s3_bucket.cloudtrail](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/s3_bucket) | data source |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_cloudtrail_logs_kms_key_id"></a> [cloudtrail\_logs\_kms\_key\_id](#input\_cloudtrail\_logs\_kms\_key\_id) | Alias, key id or key arn of the KMS Key that used for CloudTrail events | `string` | `""` | no |
| <a name="input_cloudtrail_logs_s3_bucket_name"></a> [cloudtrail\_logs\_s3\_bucket\_name](#input\_cloudtrail\_logs\_s3\_bucket\_name) | Name of the CloudWatch log s3 bucket that contains CloudTrail events | `string` | n/a | yes |
| <a name="input_configuration"></a> [configuration](#input\_configuration) | Allows to configure slack web hook url per account(s) so you can separate events from different accounts to different channels. Useful in context of AWS organization | <pre>list(object({<br>    accounts       = list(string)<br>    slack_hook_url = string<br>  }))</pre> | `null` | no |
| <a name="input_dead_letter_target_arn"></a> [dead\_letter\_target\_arn](#input\_dead\_letter\_target\_arn) | The ARN of an SNS topic or SQS queue to notify when an invocation fails. | `string` | `null` | no |
| <a name="input_default_slack_hook_url"></a> [default\_slack\_hook\_url](#input\_default\_slack\_hook\_url) | Slack incoming webhook URL to be used if AWS account id does not match any account id from configuration variable | `string` | n/a | yes |
| <a name="input_events_to_track"></a> [events\_to\_track](#input\_events\_to\_track) | Comma-separated list events to track and report | `string` | `""` | no |
| <a name="input_function_name"></a> [function\_name](#input\_function\_name) | Lambda function name | `string` | `"fivexl-cloudtrail-to-slack"` | no |
| <a name="input_ignore_rules"></a> [ignore\_rules](#input\_ignore\_rules) | Comma-separated list of rules to ignore events if you need to suppress something. Will be applied before rules and default\_rules | `string` | `""` | no |
| <a name="input_lambda_logs_retention_in_days"></a> [lambda\_logs\_retention\_in\_days](#input\_lambda\_logs\_retention\_in\_days) | Controls for how long to keep lambda logs. | `number` | `30` | no |
| <a name="input_lambda_memory_size"></a> [lambda\_memory\_size](#input\_lambda\_memory\_size) | Amount of memory in MB your Lambda Function can use at runtime. Valid value between 128 MB to 10,240 MB (10 GB), in 64 MB increments. | `number` | `256` | no |
| <a name="input_lambda_recreate_missing_package"></a> [lambda\_recreate\_missing\_package](#input\_lambda\_recreate\_missing\_package) | Description: Whether to recreate missing Lambda package if it is missing locally or not | `bool` | `true` | no |
| <a name="input_lambda_timeout_seconds"></a> [lambda\_timeout\_seconds](#input\_lambda\_timeout\_seconds) | Controls lambda timeout setting. | `number` | `30` | no |
| <a name="input_rules"></a> [rules](#input\_rules) | Comma-separated list of rules to track events if just event name is not enough | `string` | `""` | no |
| <a name="input_rules_separator"></a> [rules\_separator](#input\_rules\_separator) | Custom rules separator. Can be used if there are commas in the rules | `string` | `","` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to attach to resources | `map(string)` | `{}` | no |
| <a name="input_use_default_rules"></a> [use\_default\_rules](#input\_use\_default\_rules) | Should default rules be used | `bool` | `true` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | The ARN of the Lambda Function |
<!-- END OF PRE-COMMIT-TERRAFORM DOCS HOOK -->

## License

Apache 2 Licensed. See LICENSE for full details.
