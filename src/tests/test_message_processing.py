import pytest
from main import should_message_be_processed

# ruff: noqa: ANN201, ANN001, E501

rules = {
    "console_login_without_MFA_and_SSO": {
        "description": "Notify if someone logged in without MFA but skip notification for SSO logins",
        "condition": "event['eventName'] == 'ConsoleLogin' and "
                      "event['additionalEventData.MFAUsed'] != 'Yes' and "
                      "'assumed-role/AWSReservedSSO' not in event.get('userIdentity.arn', '')",
    },
    "unauthorized_operation": {
        "description": "Check for any AWS operations that were attempted but not authorized.",
        "condition":  "event.get('errorCode', '').endswith(('UnauthorizedOperation'))"
    },
    "access_denied": {
        "description": "AWS operations that were attempted by anonymous user (or/&) denied due to insufficient permissions.",
        "condition": "event.get('errorCode', '').startswith(('AccessDenied')) "
                      "and (event.get('userIdentity.accountId', '') != 'ANONYMOUS_PRINCIPAL')",
    },
    "non_read_action_by_root": {
        "description": "Any non-read actions performed by the root user.",
        "condition": "event.get('userIdentity.type', '') == 'Root' "
                      "and not event['eventName'].startswith(('Get', 'List', 'Describe', 'Head'))"
    },
    "cloudtrail_stop_logging": {
        "description": "CloudTrail StopLogging event",
        "condition": "event.get('eventSource') == 'cloudtrail.amazonaws.com' and event['eventName'] == 'StopLogging'"
    },
    "cloudtrail_update_trail": {
        "description": "CloudTrail UpdateTrail event",
        "condition": "event.get('eventSource') == 'cloudtrail.amazonaws.com' and event['eventName'] == 'UpdateTrail'"
    },
    "cloudtrail_delete_trail": {
        "description": "CloudTrail DeleteTrail event",
        "condition": "event.get('eventSource') == 'cloudtrail.amazonaws.com' and event['eventName'] == 'DeleteTrail'"
    },
}


@pytest.fixture(
    params = [
        {
            "in": {
                "rule_name": "console_login_without_MFA_and_SSO",
                "rules": [rules["console_login_without_MFA_and_SSO"]],
                "ignore_rules": [rules["console_login_without_MFA_and_SSO"]],
                "event":{
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
                    "requestParameters": "null",
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
                },
            },
            "out": {
                "result": True,
            },
        },
        {
            "in": {
                "rule_name": "cloudtrail_stop_logging",
                "rules": [rules["cloudtrail_stop_logging"]],
                "ignore_rules": [rules["cloudtrail_stop_logging"]],
                "event": {
                    "eventVersion": "1.09",
                    "userIdentity": {
                        "type": "AssumedRole",
                        "principalId": "XXXXXXXXXXXXXXXXXXXXXX",
                        "arn": "arn:aws:sts::XXXXXXXXXXX",
                        "accountId": "XXXXXXXXXXX",
                        "accessKeyId": "XXXXXXXXXXX",
                        "sessionContext": {
                            "sessionIssuer": {
                                "type": "Role",
                                "principalId": "XXXXXXXXXXX",
                                "arn": "XXXXXXXXXXX",
                                "accountId": "XXXXXXXXXXX",
                                "userName": "XXXXXXXXXXX"
                            },
                        }
                    },
                    "eventTime": "2023-06-13T11:03:44Z",
                    "eventSource": "cloudtrail.amazonaws.com",
                    "eventName": "StopLogging",
                    "awsRegion": "eu-central-1",
                    "sourceIPAddress": "XXXXXXXXXXX",
                    "userAgent": "AWS Internal",
                    "requestParameters": {
                        "name": "XXXXXXXXXXX"
                    },
                    "responseElements": "null",
                    "requestID": "XXXXXXXXXXX",
                    "eventID": "XXXXXXXXXXX",
                    "readOnly": "false",
                    "eventType": "AwsApiCall",
                    "managementEvent": "true",
                    "recipientAccountId": "XXXXXXXXXXX",
                    "eventCategory": "Management",
                    "sessionCredentialFromConsole": "true"
                },
            },
            "out": {
                "result": True,
            },
        },
        {
            "in": {
                "rule_name": "cloudtrail_update_trail",
                "rules": [rules["cloudtrail_update_trail"]],
                "ignore_rules": [rules["cloudtrail_update_trail"]],
                "event": {
                    "eventVersion": "1.09",
                    "userIdentity": {
                        "type": "AssumedRole",
                        "principalId": "XXXXXXXXXXX",
                        "arn": "XXXXXXXXXXX",
                        "accountId": "XXXXXXXXXXX",
                        "accessKeyId": "XXXXXXXXXXX",
                        "sessionContext": {
                            "sessionIssuer": {
                                "type": "Role",
                                "principalId": "XXXXXXXXXXX",
                                "arn": "XXXXXXXXXXX",
                                "accountId": "XXXXXXXXXXX",
                                "userName": "XXXXXXXXXXX"
                            },
                            },
                        },
                    "eventTime": "2023-06-13T11:04:48Z",
                    "eventSource": "cloudtrail.amazonaws.com",
                    "eventName": "UpdateTrail",
                    "awsRegion": "XXXXXXXXXXX",
                    "sourceIPAddress": "XXXXXXXXXXX",
                    "userAgent": "AWS Internal",
                    "requestParameters": {},
                    "responseElements": {},
                    "requestID": "XXXXXXXXXXX",
                    "eventID": "XXXXXXXXXXX",
                    "readOnly": "false",
                    "eventType": "AwsApiCall",
                    "managementEvent": "true",
                    "recipientAccountId": "XXXXXXXXXXX",
                    "eventCategory": "Management",
                },
            },
            "out": {
                "result": True,
            },
        },
        {
            "in": {
                "rule_name": "cloudtrail_delete_trail",
                "rules": [rules["cloudtrail_delete_trail"]],
                "ignore_rules": [rules["cloudtrail_delete_trail"]],
                "event": {
                    "eventVersion": "1.09",
                    "userIdentity": {
                        "type": "AssumedRole",
                        "principalId": "XXXXXXXXXXX",
                        "arn": "XXXXXXXXXXX",
                        "accountId": "XXXXXXXXXXX",
                        "accessKeyId": "XXXXXXXXXXX",
                        "sessionContext": {
                            "sessionIssuer": {
                                "type": "Role",
                                "principalId": "XXXXXXXXXXX",
                                "arn": "XXXXXXXXXXX",
                                "accountId": "XXXXXXXXXXX",
                                "userName": "XXXXXXXXXXX"
                            },
                            },
                        },
                    "eventTime": "2023-06-13T11:04:59Z",
                    "eventSource": "cloudtrail.amazonaws.com",
                    "eventName": "DeleteTrail",
                    "awsRegion": "XXXXXXXXXXX",
                    "sourceIPAddress": "XXXXXXXXXXX",
                    "userAgent": "AWS Internal",
                    "requestParameters": {
                        "name": "XXXXXXXXXXX"
                    },
                    "responseElements": "null",
                    "requestID": "XXXXXXXXXXX",
                    "eventID": "XXXXXXXXXXX",
                    "readOnly": "false",
                    "eventType": "AwsApiCall",
                    "managementEvent": "true",
                    "recipientAccountId": "XXXXXXXXXXX",
                    "eventCategory": "Management",
                    "sessionCredentialFromConsole": "true"
                },
            },
            "out": {
                "result": True,
            },
        },
        {
            "in": {
                "rule_name": "non_read_action_by_root",
                "rules": [rules["non_read_action_by_root"]],
                "ignore_rules": [rules["non_read_action_by_root"]],
                "event": {
                    "eventVersion": "1.08",
                    "userIdentity": {
                        "type": "Root",
                        "principalId": "XXXXXXXXXXXXXXXXXXXX",
                        "arn": "arn:aws:iam::XXXXXXXXXXXXXXXXXXXX:root",
                        "accountId": "XXXXXXXXXXXXXXXXXXXX",
                        "accessKeyId": ""
                    },
                    "eventTime": "XXXXXXXXXXXXXXXXXXXX",
                    "eventSource": "signin.amazonaws.com",
                    "eventName": "ConsoleLogin",
                    "awsRegion": "XXXXXXXXXXXXXXXXXXXX",
                    "sourceIPAddress": "XXXXXXXXXXXXXXXXXXXX",
                    "userAgent": "XXXXXXXXXXXXXXXXXXXX",
                    "requestParameters": "null",
                    "responseElements": {
                        "ConsoleLogin": "Success"
                    },
                    "additionalEventData": {
                        "LoginTo": "XXXXXXXXXXXXXXXXXXXX",
                        "MobileVersion": "No",
                        "MFAUsed": "Yes"
                    },
                    "eventID": "XXXXXXXXXXXXXXXXXXXX",
                    "readOnly": "false",
                    "eventType": "AwsConsoleSignIn",
                    "managementEvent": "true",
                    "recipientAccountId": "XXXXXXXXXXXXXXXXXXXX",
                    "eventCategory": "Management"
                },
            },
            "out": {
                "result": True,
            },
        },
        {
            "in": {
                "rule_name": "unauthorized_operation",
                "rules": [rules["unauthorized_operation"]],
                "ignore_rules": [rules["unauthorized_operation"]],
                "event": {
                    "eventVersion": "1.08",
                    "userIdentity": {
                        "type": "AssumedRole",
                        "principalId": "XXXXXXXXXXXXX",
                        "arn": "arn:aws:sts::XXXXXXXXXXXXX:assumed-role/XXXXXXXXXXXXX/XXXXXXXXXXXXX",
                        "accountId": "XXXXXXXXXXXXX",
                        "accessKeyId": "XXXXXXXXXXXXX",
                        "sessionContext": {
                            "sessionIssuer": {
                                "type": "Role",
                                "principalId": "XXXXXXXXXXXXX",
                                "arn": "arn:aws:iam::XXXXXXXXXXXXX:role/aws-reserved/XXXXXXXXXXXXX/XXXXXXXXXXXXX/XXXXXXXXXXXXX",
                                "accountId": "XXXXXXXXXXXXX",
                                "userName": "XXXXXXXXXXXXX"
                            },
                        }
                    },
                    "eventTime": "2023-06-09T07:46:09Z",
                    "eventSource": "ec2.amazonaws.com",
                    "eventName": "DescribeInstances",
                    "awsRegion": "eu-central-1",
                    "sourceIPAddress": "XXXXXXXXXXXXX",
                    "userAgent": "XXXXXXXXXXXXX/ec2.describe-instances",
                    "errorCode": "Client.UnauthorizedOperation",
                    "errorMessage": "You are not authorized to perform this operation.",
                    "requestParameters": {
                        "instancesSet": {},
                        "filterSet": {}
                    },
                    "responseElements": "null",
                    "requestID": "XXXXXXXXXXXXX",
                    "eventID": "XXXXXXXXXXXXX",
                    "readOnly": "true",
                    "eventType": "AwsApiCall",
                    "managementEvent": "true",
                    "recipientAccountId": "XXXXXXXXXXXXX",
                    "eventCategory": "Management",
                },
            },
            "out": {
                "result": True,
            },
        },
        {
            "in": {
                "rule_name": "access_denied",
                "rules": [rules["access_denied"]],
                "ignore_rules": [rules["access_denied"]],
                "event": {
                    "eventVersion": "1.08",
                    "userIdentity": {
                        "type": "AssumedRole",
                        "principalId": "XXXXXXXXXXXXXXXXXXXX",
                        "arn": "arn:aws:sts::XXXXXXXXXXXXXX:assumed-role/XXXXXXXXXXXXXXXXX/XXXXXXXXXXXXXXXXXXXXX",
                        "accountId": "YYYYYYYYYYYYYYYYY",
                        "accessKeyId": "XXXXXXXXXXXXXXXXX",
                        "sessionContext": {
                            "sessionIssuer": {
                                "type": "Role",
                                "principalId": "XXXXXXXXXXXXXXXXXXXX",
                                "arn": "arn:aws:iam::XXXXXXXXX:role/XXXXXXXXXXXXX",
                                "accountId": "XXXXXXXXXXXXXXX",
                                "userName": "XXXXXXXXXXXXXXXXXXX",
                            },
                            "attributes": {
                                "creationDate": "XXXXXXXXXXXXX",
                                "mfaAuthenticated": "false"
                            }
                        }
                    },
                    "eventTime": "XXXXXXXXXXXXX",
                    "eventSource": "health.amazonaws.com",
                    "eventName": "DescribeEventAggregates",
                    "awsRegion": "us-east-1",
                    "sourceIPAddress": "XXXXXXXXXXXXX",
                    "userAgent": "XXXXXXXXXXXXX",
                    "errorCode": "AccessDenied",
                    "errorMessage": "User: arn:aws:sts::XXXXXXXXXXXXX:assumed-role/XXXXXXXXXXXXX/XXXXXXXXXXXXX is not authorized to perform: health:DescribeEventAggregates on resource: * because no identity-based policy allows the health:DescribeEventAggregates action", # noqa: E501
                    "requestParameters": "null",
                    "responseElements": "null",
                    "requestID": "XXXXXXXXXXXXX-0c20-4131-a6a7-XXXXXXXXXXXXX",
                    "eventID": "XXXXXXXXXXXXX-eab3-4bc7-ae06-XXXXXXXXXXXXX",
                    "readOnly": "true",
                    "eventType": "AwsApiCall",
                    "managementEvent": "true",
                    "recipientAccountId": "XXXXXXXXXXXXX",
                    "eventCategory": "Management",
                    "sessionCredentialFromConsole": "true"
                },
            },
            "out": {
                "result": True,
            },
        },
    ],
    ids= lambda t: t["in"]["rule_name"],
)
def message_should_be_processed_test_cases(request):
    return request.param


@pytest.fixture(
    params = [
        {
            "in": {
                "rule_name": "console_login_without_MFA_and_SSO",
                "rules": [rules["console_login_without_MFA_and_SSO"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event"
                },
            },
            "out": {
                "result": False,
            },
        },
        {
            "in": {
                "rule_name": "cloudtrail_stop_logging",
                "rules": [rules["cloudtrail_stop_logging"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event"
                },
            },
            "out": {
                "result": False,
            },
        },
        {
            "in": {
                "rule_name": "cloudtrail_update_trail",
                "rules": [rules["cloudtrail_update_trail"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event"
                },
            },
            "out": {
                "result": False,
            },
        },
        {
            "in": {
                "rule_name": "cloudtrail_delete_trail",
                "rules": [rules["cloudtrail_delete_trail"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event"
                },
            },
            "out": {
                "result": False,
            },
        },
        {
            "in": {
                "rule_name": "non_read_action_by_root",
                "rules": [rules["non_read_action_by_root"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event"
                },
            },
            "out": {
                "result": False,
            },
        },
        {
            "in": {
                "rule_name": "unauthorized_operation",
                "rules": [rules["unauthorized_operation"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event"
                },
            },
            "out": {
                "result": False,
            },
        },
        {
            "in": {
                "rule_name": "access_denied",
                "rules": [rules["access_denied"]],
                "event":{
                    "userIdentity": "123",
                    "eventName": "empty_event",
                },
            },
            "out": {
                "result": False,
            },
        },
    ],
    ids = lambda t: t["in"]["rule_name"],
)
def message_should_not_be_processed_test_cases(request):
    return request.param


@pytest.fixture(
    params = [
        {
            "in": {
                "rule_name": "console_login_without_MFA_and_SSO",
                "rules": ["incorrect_rule", rules["console_login_without_MFA_and_SSO"]],
                "event":{
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
                    "requestParameters": "null",
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
                },
            },
            "out": {
                "result": True,
            },
        },
    ],
    ids= lambda t: t["in"]["rule_name"],
)
def message_should_not_be_processed_with_incorrect_rule_test_case(request):
    return request.param



def test_message_should_be_processed(message_should_be_processed_test_cases) -> None:
    assert should_message_be_processed(
        event = message_should_be_processed_test_cases["in"]["event"],
        rules = [rule["condition"] for rule in message_should_be_processed_test_cases["in"]["rules"]],
        ignore_rules = []
        ) == message_should_be_processed_test_cases["out"]["result"]


def test_message_should_not_be_processed(message_should_not_be_processed_test_cases) -> None:
    assert should_message_be_processed(
        event = message_should_not_be_processed_test_cases["in"]["event"],
        rules = [rule["condition"] for rule in message_should_not_be_processed_test_cases["in"]["rules"]],
        ignore_rules = []
        ) is message_should_not_be_processed_test_cases["out"]["result"]


def test_message_should_not_be_processed_with_rules_as_ignor_rules(message_should_be_processed_test_cases) -> None:
    assert should_message_be_processed(
        event = message_should_be_processed_test_cases["in"]["event"],
        rules = [rule["condition"] for rule in message_should_be_processed_test_cases["in"]["rules"]],
        ignore_rules = [rule["condition"] for rule in message_should_be_processed_test_cases["in"]["ignore_rules"]]
        ) is False


def test_should_message_be_processed_with_ParsingEventError_handling(message_should_not_be_processed_with_incorrect_rule_test_case) -> None:
    assert should_message_be_processed(
            event = message_should_not_be_processed_with_incorrect_rule_test_case["in"]["event"],
            rules = [rule["condition"] for rule in message_should_not_be_processed_with_incorrect_rule_test_case["in"]["rules"]
                     if rule != "incorrect_rule"],
            ignore_rules = []
        ) is message_should_not_be_processed_with_incorrect_rule_test_case["out"]["result"]
