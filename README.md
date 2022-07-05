[![FivexL](https://releases.fivexl.io/fivexlbannergit.jpg)](https://fivexl.io/)

<!--- Use Markdown All In One Visual Studio Code extension to refresh TOC -->
- [Terraform module to deploy lambda that sends notifications about AWS CloudTrail events to Slack](#terraform-module-to-deploy-lambda-that-sends-notifications-about-aws-cloudtrail-events-to-slack)
  - [Why this module?](#why-this-module)
  - [Example message](#example-message)
  - [Delivery delays](#delivery-delays)
- [Examples](#examples)
  - [Module deployment with the default ruleset](#module-deployment-with-the-default-ruleset)
  - [Separating notifications to different Slack channels](#separating-notifications-to-different-slack-channels)
    - [Module deployment with the default ruleset and different slack channels for different accounts](#module-deployment-with-the-default-ruleset-and-different-slack-channels-for-different-accounts)
  - [Tracking certain event types](#tracking-certain-event-types)
  - [User defined rules to match events](#user-defined-rules-to-match-events)
    - [Module deployment with user-defined rules, list of events to track, and default rule sets](#module-deployment-with-user-defined-rules-list-of-events-to-track-and-default-rule-sets)
    - [Catch SSM Session events for the "111111111" account](#catch-ssm-session-events-for-the-111111111-account)
  - [Ignore rules.](#ignore-rules)
    - [Ignore events from the account "111111111".](#ignore-events-from-the-account-111111111)
- [About rules and how they are applied](#about-rules-and-how-they-are-applied)
  - [Default rules](#default-rules)
  - [Ignore rules](#ignore-rules-1)
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

## Example message

![Example message](https://releases.fivexl.io/example_message.png)

## Delivery delays

The current implementation built upon parsing of S3 notifications, and thus you should expect a 5 to 10 min lag between action and event notification in Slack.
If you do not get a notification at all - check CloudWatch logs for the lambda to see if there is any issue with provided filters.

# Examples

## Module deployment with the default ruleset

```hlc
# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

module "cloudtrail_to_slack" {
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "2.0.0"
  default_slack_hook_url         = data.aws_ssm_parameter.hook.value
  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id
}

resource "aws_cloudtrail" "main" {
  name           = "main"
  s3_bucket_name = aws_s3_bucket.cloudtrail.id
  ...
}

resource "aws_s3_bucket" "cloudtrail" {
  ....
}
```

## Separating notifications to different Slack channels

### Module deployment with the default ruleset and different slack channels for different accounts

```hlc
# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "default_hook" {
  name = "/cloudtrail-to-slack/default_hook"
}

data "aws_ssm_parameter" "dev_hook" {
  name = "/cloudtrail-to-slack/dev_hook"
}

data "aws_ssm_parameter" "prod_hook" {
  name = "/cloudtrail-to-slack/prod_hook"
}

module "cloudtrail_to_slack" {
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "2.0.0"
  default_slack_hook_url         = data.aws_ssm_parameter.default_hook.value

  configuration = [
    {
      "accounts": ["123456789"],
      "slack_hook_url": data.aws_ssm_parameter.dev_hook.value
    },
    {
      "accounts": ["987654321"],
      "slack_hook_url": data.aws_ssm_parameter.prod_hook.value
    }
  ]

  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id
}

resource "aws_cloudtrail" "main" {
  name           = "main"
  s3_bucket_name = aws_s3_bucket.cloudtrail.id
  ...
}

resource "aws_s3_bucket" "cloudtrail" {
  ....
}
```

## Tracking certain event types

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
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "2.0.0"
  default_slack_hook_url         = data.aws_ssm_parameter.hook.value
  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id
  events_to_track                = local.events_to_track
}

resource "aws_cloudtrail" "main" {
  name           = "main"
  s3_bucket_name = aws_s3_bucket.cloudtrail.id
  ...
}

resource "aws_s3_bucket" "cloudtrail" {
  ....
}
```

## User defined rules to match events

### Module deployment with user-defined rules, list of events to track, and default rule sets

```hlc
# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

module "cloudtrail_to_slack" {
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "2.0.0"
  default_slack_hook_url         = data.aws_ssm_parameter.hook.value
  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id
  rules                          = "'errorCode' in event and event['errorCode'] == 'UnauthorizedOperation','userIdentity.type' in event and event['userIdentity.type'] == 'Root'"
  events_to_track                = "CreateUser,StartInstances"
}
```

### Catch SSM Session events for the "111111111" account

```hcl
# Important! User defined rules should not contain comas since they are passed to lambda as coma separated string
locals {
  cloudtrail_rules = [
      "'userIdentity.accountId' in event and event['userIdentity.accountId'] == '11111111111' and event['eventSource'] == 'ssm.amazonaws.com' and event['eventName'].endswith(('Session'))",
    ]
}

# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

module "cloudtrail_to_slack" {
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "2.0.0"
  default_slack_hook_url         = data.aws_ssm_parameter.hook.value
  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id
  rules                          = join(",", local.cloudtrail_rules)
}
```
### Using a custom separator for complex rules containing commas

```hcl
locals {
  cloudtrail_rules = [
      ...
    ]
  custom_separator = "%"
}

module "cloudtrail_to_slack" {
      ...
  rules           = join(local.custom_separator, local.cloudtrail_rules)
  rules_separator = local.custom_separator
}
```

## Ignore rules.

### Ignore events from the account "111111111".

Note! We do recomend fixing alerts instead of ignoring them. But if there is no way you can fix it then there is a way to suppress events by providing ignore rules

```hcl
# Important! User defined rules should not contain comas since they are passed to lambda as coma separated string
locals {
  cloudtrail_ignore_rules = [
      "'userIdentity.accountId' in event and event['userIdentity.accountId'] == '11111111111'",
    ]
}

# we recomend storing hook url in SSM Parameter store and not commit it to the repo
data "aws_ssm_parameter" "hook" {
  name = "/cloudtrail-to-slack/hook"
}

module "cloudtrail_to_slack" {
  source                         = "fivexl/cloudtrail-to-slack/aws"
  version                        = "2.3.0"
  default_slack_hook_url         = data.aws_ssm_parameter.hook.value
  cloudtrail_logs_s3_bucket_name = aws_s3_bucket.cloudtrail.id
  ignore_rules                   = join(",", local.cloudtrail_ignore_rules)
}
```

# About rules and how they are applied

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
default_rules.append('event.get("errorCode", "") == "UnauthorizedOperation"')
default_rules.append('event.get("errorCode", "") == "AccessDenied" ' +
                     'and (event.get("userIdentity.accountId", "") != "ANONYMOUS_PRINCIPAL")')

# Notify about all non-read actions done by root
default_rules.append('event.get("userIdentity.type", "") == "Root" ' +
                     'and not event["eventName"].startswith(("Get", "List", "Describe", "Head"))')
```

## Ignore rules

User can also provide ignore rules. Ignore rules have the same syntax as a default and user defined rules mentioned above.
But instead of generating message to Slack on match those rules will cause lambda to ignore an event.
Ignore rules tested before default and user defined rules which means that if even is ignored by ignore rules it will not be
tested with any other rules.

# Terraform specs

<!-- BEGINNING OF PRE-COMMIT-TERRAFORM DOCS HOOK -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 0.12.31 |
| <a name="requirement_aws"></a> [aws](#requirement\_aws) | >= 3.43 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_aws"></a> [aws](#provider\_aws) | 3.62.0 |

## Modules

| Name | Source | Version |
|------|--------|---------|
| <a name="module_lambda"></a> [lambda](#module\_lambda) | terraform-aws-modules/lambda/aws | 2.25.0 |

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
| <a name="input_lambda_timeout_seconds"></a> [lambda\_timeout\_seconds](#input\_lambda\_timeout\_seconds) | Controls lambda timeout setting. | `number` | `30` | no |
| <a name="input_rules"></a> [rules](#input\_rules) | Comma-separated list of rules to track events if just event name is not enough | `string` | `""` | no |
| <a name="input_tags"></a> [tags](#input\_tags) | Tags to attach to resources | `map(string)` | `{}` | no |
| <a name="input_use_default_rules"></a> [use\_default\_rules](#input\_use\_default\_rules) | Should default rules be used | `bool` | `true` | no |
| <a name="input_rules_separator"></a> [rules\_separator](#input\rules\_separator) | Custom rules separator. Must be defined if there are commas in the rules | `string` | `","` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_lambda_function_arn"></a> [lambda\_function\_arn](#output\_lambda\_function\_arn) | The ARN of the Lambda Function |
<!-- END OF PRE-COMMIT-TERRAFORM DOCS HOOK -->

## License

Apache 2 Licensed. See LICENSE for full details.
