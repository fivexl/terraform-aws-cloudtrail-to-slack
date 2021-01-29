[![FivexL](https://releases.fivexl.io/fivexlbannergit.jpg)](https://fivexl.io/)

# Terraform module to deploy lambda that sends notifications about AWS CloudTrail events to Slack

## Why this module?

This module allows you to get notifications about:

- actions performed by root account (According to AWS best practices, you should use root account as little as possible and use SSO or IAM users)
- API calls that failed due to lack of permissions to do so (could be an indication of compromise or misconfiguration of your services/applications)
- console logins without MFA (Always use MFA for you IAM users or SSO)
- track a list of events that you might consider sensitive. Think IAM changes, network changes, data storage (S3, DBs) access changes. Though we recommend keeping that to a minimum to avoid alert fatigue
- define sophisticated rules to track user-defined conditions that are not covered by default rules (see examples below)

## Example message

![Example message](example_message.png)

## Delivery delays

The current implementation built upon parsing of CloudWatch log streams, and thus you should expect a 5 to 15 min lag between action and event notification in Slack.
If you do not get a notification at all - check CloudWatch logs for the lambda to see if there is any issue with provided filters.

## How to

Module deployment with the default ruleset

```hlc
# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

module "cloudtrail_to_slack" {
  source                               = "fivexl/cloudtrail-to-slack/aws"
  version                              = "1.0.0"
  slack_hook_url                       = data.aws_ssm_parameter.hook.value
  cloudtrail_cloudwatch_log_group_name = "cloudtrail"
}
```

Module deployment with the list of events to track and default rule sets

```hlc
# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

locals {
  # CloudTrail events
  cloudtrail = "DeleteTrail,StopLogging,UpdateTrail"
  # EC2 Instance connect and EC2 events
  ec2 = "SendSSHPublicKey"
  # Config
  config = "DeleteConfigRule,DeleteConfigurationRecorder,DeleteDeliveryChannel,DeleteEvaluationResults"
  # All events
  events_to_track = "${local.cloudtrail},${local.ec2},${local.config}"
}

module "cloudtrail_to_slack" {
  source                               = "fivexl/cloudtrail-to-slack/aws"
  version                              = "1.0.0"
  slack_hook_url                       = data.aws_ssm_parameter.hook.value
  cloudtrail_cloudwatch_log_group_name = aws_cloudwatch_log_group.cloudtrail.name
  events_to_track                      = local.events_to_track
}
```

Module deployment with user-defined rules, list of events to track, and default rule sets

```hlc
# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

module "cloudtrail_to_slack" {
  source                               = "fivexl/cloudtrail-to-slack/aws"
  version                              = "1.0.0"
  slack_hook_url                       = data.aws_ssm_parameter.hook.value
  cloudtrail_cloudwatch_log_group_name = "cloudtrail"
  rules                                = "'errorCode' in event and event['errorCode'] == 'UnauthorizedOperation','userIdentity.type' in event and event['userIdentity.type'] == 'Root'"
  events_to_track                      = "CreateUser,StartInstances"
}
```

## About rules and how they are applied

This module comes with a set of predefined rules (default rules) that users can take advantage of.
Rules are python strings that are evaluated in the runtime and should return the bool value.
CloudTrail event (see format [here](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference.html)) is flattened before processing and should be referenced as `event` variable
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

## Default rules

```python
# Notify if someone logged in without MFA but skip notification for SSO logins
default_rules.append('event["eventName"] == "ConsoleLogin" ' +
                     'and event["additionalEventData.MFAUsed"] != "Yes" ' +
                     'and "assumed-role/AWSReservedSSO" not in event.get("userIdentity.arn", "")')

# Notify if someone is trying to do something they not supposed to be doing but do not notify
# about not logged in actions since there are a lot of scans for open buckets that generate noise
# This is useful to discover any misconfigurations in your account. Time to time services will try
# to do something but fail due to IAM permissions and those errors are very hard to find using
# other means
default_rules.append('event.get("errorCode", "") == "UnauthorizedOperation" ' +
                     'and (event.get("userIdentity.accountId", "") != "ANONYMOUS_PRINCIPAL")')

# Notify about all non-read actions done by root
default_rules.append('event.get("userIdentity.type", "") == "Root" ' +
                     'and not event["eventName"].startswith(("Get", "List", "Describe", "Head"))')
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 0.12 |
| aws | >= 3.13.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| function_name | The name of the lambda function | `string` | `fivexl-cloudtrail-to-slack` | no |
| slack_hook_url | Slack incoming webhook URL. Read how to create it [here](https://api.slack.com/messaging/webhooks) | `string` |  | yes |
| cloudtrail_cloudwatch_log_group_name | The AWS CloudWatch log group name from where the lambda function will be reading AWS CloudTrail events. Read [here](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/send-cloudtrail-events-to-cloudwatch-logs.html) how to set it up  | `string` | | yes |
| events_to_track | Comma-separated list events to track and report | `string` |  | no |
| rules | Comma-separated list of rules to track events if just event name is not enough. See the example above for details. | `string` |  | no |
| use_default_rules | Indicates if lambda should be using default ruleset supplied with lambda code. | `bool` | true | no |
| tags | Tags to apply on created resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|

## License

Apache 2 Licensed. See LICENSE for full details.
