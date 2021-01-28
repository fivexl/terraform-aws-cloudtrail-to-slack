[![FivexL](https://releases.fivexl.io/fivexlbannergit.jpg)](https://fivexl.io/)

# Terraform module to deploy lambda that sends notifications about AWS CloudTrail events to Slack

Module deployment with default rule set

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

module "cloudtrail_to_slack" {
  source                               = "fivexl/cloudtrail-to-slack/aws"
  version                              = "1.0.0"
  slack_hook_url                       = data.aws_ssm_parameter.hook.value
  cloudtrail_cloudwatch_log_group_name = "cloudtrail"
  events_to_track                      = "CreateUser,StartInstances"
}
```

Module deployment with user defined rules, list of events to track and default rule sets

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

This module comes with a set of predefined rules (default rules) that user can take advantage of.
Rules are python strings that are evaluated in the runtime and should return bool value.
CloudTrail event (see format [here](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference.html)) is flattened before processing and should be referenced as `event` variable
So for instance, in order to access arn from the event below

```json
{ "eventVersion": "1.05", "userIdentity": { "type": "IAMUser", "principalId": "XXXXXXXXXXX", "arn": "arn:aws:iam::XXXXXXXXXXX:user/xxxxxxxx", "accountId": "XXXXXXXXXXX", "userName": "xxxxxxxx" }, "eventTime": "2019-07-03T16:14:51Z", "eventSource": "signin.amazonaws.com", "eventName": "ConsoleLogin", "awsRegion": "us-east-1", "sourceIPAddress": "83.41.208.104", "userAgent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0", "requestParameters": null, "responseElements": { "ConsoleLogin": "Success" }, "additionalEventData": { "LoginTo": "https://console.aws.amazon.com/ec2/v2/home?XXXXXXXXXXX", "MobileVersion": "No", "MFAUsed": "No" }, "eventID": "0e4d136e-25d4-4d92-b2b2-8a9fe1e3f1af", "eventType": "AwsConsoleSignIn", "recipientAccountId": "XXXXXXXXXXX" }```
```

You should use notation `userIdentity.arn`

Default rules

```python
# Notify if someone logged in without MFA but skip notification for SSO logins
"eventName" in event and event["eventName"] == "ConsoleLogin" and event["additionalEventData.MFAUsed"] != "Yes" and "assumed-role/AWSReservedSSO" not in event["userIdentity.arn"]
# Notify if someone is trying to do something they not supposed to be doing
"errorCode" in event and event["errorCode"] == "UnauthorizedOperation"
# Notify about all non-read actions done by root
"userIdentity.type" in event and event["userIdentity.type"] == "Root" and not event["eventName"].startswith(("Get", "List", "Describe", "Head"))
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 0.13 |
| aws | >= 3.13.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| function_name | The name of the lambda function | `string` | `fivexl-cloudtrail-to-slack` | no |
| slack_hook_url | Slack incoming webhook URL. Read how to create it [here](https://api.slack.com/messaging/webhooks) | `string` |  | yes |
| cloudtrail_cloudwatch_log_group_name | The AWS CloudWatch log group name from where the lambda function will be reading AWS CloudTrail events. Read [here](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/send-cloudtrail-events-to-cloudwatch-logs.html) how to set it up  | `string` | | yes |
| events_to_track | Comma-separated list events to track and report | `string` |  | no |
| rules | Comma-separated list of rules to track events if just event name is not enough. See example above for details. | `string` |  | no |
| use_default_rules | Indicates if lambda should be using default rule set supplied with lambda code. If `rules` is also provided then will use both default rules and user defined rules if set to true. | `bool` | true | no |
| tags | Tags to apply on created resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|

## License

Apache 2 Licensed. See LICENSE for full details.
