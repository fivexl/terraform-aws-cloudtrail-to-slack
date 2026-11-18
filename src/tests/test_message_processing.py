import json

import pytest
from main import ProcessingResult, flatten_json, should_message_be_processed
from rules import default_rules

# ruff: noqa: ANN201, ANN001
# for CI testing purposes, path to test_events.json was changed to tests/test_events.json, so to run tests locally
# you need to change it back to src/tests/test_events.json, or run command from src directory:

# Tests can be run by : pytest --log-disable=main tests/test_message_processing.py -v

with open("tests/test_events.json") as f:
    data = json.load(f)


@pytest.fixture(params=data["test_events"], ids=[event["test_event_name"] for event in data["test_events"]])
def message_should_be_processed_test_cases(request):
    return request.param


@pytest.fixture(
    params=[
        {
            "in": {
                "event": {"userIdentity": "123", "eventName": "empty_event", "eventSource": "imagination"},
            },
            "out": {
                "result": ProcessingResult(False, []),
            },
        },
    ],
    ids=["empty_event"],
)
def message_should_not_be_processed_test_cases(request):
    return request.param


@pytest.fixture(
    params=[
        {
            "in": {
                "incorrect_rule": "incorrect_rule",
                "event": {
                    "eventVersion": "1.05",
                    "userIdentity": {
                        "type": "IAMUser",
                        "principalId": "XXXXXXXXXXX",
                        "arn": "arn:aws:iam::XXXXXXXXXXX:user/xxxxxxxx",
                        "accountId": "XXXXXXXXXXX",
                        "userName": "xxxxxxxx",
                    },
                    "eventTime": "2019-07-03T16:14:51Z",
                    "eventSource": "signin.amazonaws.com",
                    "eventName": "ConsoleLogin",
                    "awsRegion": "us-east-1",
                    "sourceIPAddress": "83.41.208.104",
                    "userAgent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:67.0) Gecko/20100101 Firefox/67.0",
                    "requestParameters": "null",
                    "responseElements": {"ConsoleLogin": "Success"},
                    "additionalEventData": {
                        "LoginTo": "https://console.aws.amazon.com/ec2/v2/home?XXXXXXXXXXX",
                        "MobileVersion": "No",
                        "MFAUsed": "No",
                    },
                    "eventID": "0e4d136e-25d4-4d92-b2b2-8a9fe1e3f1af",
                    "eventType": "AwsConsoleSignIn",
                    "recipientAccountId": "XXXXXXXXXXX",
                },
            },
            "out": {
                "result": ProcessingResult(
                    should_be_processed=True,
                    errors=[{"error": NameError("name 'incorrect_rule' is not defined"), "rule": "incorrect_rule"}],
                ),
            },
        },
    ],
    ids=["incorrect_rule"],
)
def message_should_be_processed_with_incorrect_rule_test_case(request):
    return request.param


def test_message_should_be_processed(message_should_be_processed_test_cases) -> None:
    assert should_message_be_processed(
        event=message_should_be_processed_test_cases["event"], rules=default_rules, ignore_rules=[]
    ) == ProcessingResult(should_be_processed=True, errors=[])


def test_message_should_not_be_processed(message_should_not_be_processed_test_cases) -> None:
    assert (
        should_message_be_processed(event=message_should_not_be_processed_test_cases["in"]["event"], rules=default_rules, ignore_rules=[])
        == message_should_not_be_processed_test_cases["out"]["result"]
    )


def test_message_should_not_be_processed_with_rules_as_ignor_rules(message_should_be_processed_test_cases) -> None:
    assert should_message_be_processed(
        event=message_should_be_processed_test_cases["event"], rules=default_rules, ignore_rules=default_rules
    ) == ProcessingResult(should_be_processed=False, errors=[], is_ignored=True)


def test_should_message_be_processed_with_ParsingEventError_handling(message_should_be_processed_with_incorrect_rule_test_case) -> None:
    almost_default_rules = default_rules.copy()
    almost_default_rules.insert(0, message_should_be_processed_with_incorrect_rule_test_case["in"]["incorrect_rule"])
    result = should_message_be_processed(
        event=message_should_be_processed_with_incorrect_rule_test_case["in"]["event"],
        rules=almost_default_rules,  # type: ignore[arg-type]
        ignore_rules=[],
    )

    # check that the result without considering errors is correct
    assert result.should_be_processed == message_should_be_processed_with_incorrect_rule_test_case["out"]["result"].should_be_processed

    # compare error messages in the result
    assert str(result.errors[0]["error"]) == str(
        message_should_be_processed_with_incorrect_rule_test_case["out"]["result"].errors[0]["error"]
    )
    assert result.errors[0]["rule"] == message_should_be_processed_with_incorrect_rule_test_case["out"]["result"].errors[0]["rule"]


# Events close to a default rule that the rule must not match. Positive cases are in test_events.json.
@pytest.mark.parametrize(
    "event",
    [
        {
            "eventName": "ConsoleLogin",
            "eventSource": "signin.amazonaws.com",
            "additionalEventData": {"MFAUsed": "Yes"},
            "userIdentity": {"arn": "arn:aws:iam::111111111111:user/alice"},
        },
        {
            "eventName": "ConsoleLogin",
            "eventSource": "signin.amazonaws.com",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {"arn": "arn:aws:sts::111111111111:assumed-role/AWSReservedSSO_Admin_0123456789abcdef/alice"},
        },
        {
            "eventName": "GetObject",
            "eventSource": "s3.amazonaws.com",
            "errorCode": "AccessDenied",
            "userIdentity": {"accountId": "ANONYMOUS_PRINCIPAL"},
        },
        *(
            {"eventName": name, "eventSource": "iam.amazonaws.com", "userIdentity": {"type": "Root"}}
            for name in ("GetUser", "ListUsers", "DescribeInstances", "HeadBucket")
        ),
        {
            "eventName": "UpdateFunctionCode20150331v2",
            "eventSource": "lambda.amazonaws.com",
            "responseElements": {"functionName": "some-other-function"},
        },
        {"eventName": "StartLogging", "eventSource": "cloudtrail.amazonaws.com"},
    ],
    ids=[
        "console_login_with_mfa",
        "sso_login",
        "anonymous_access_denied",
        "root_get",
        "root_list",
        "root_describe",
        "root_head",
        "other_lambda_updated",
        "cloudtrail_start_logging",
    ],
)
def test_default_rules_do_not_match(event) -> None:
    assert should_message_be_processed(event=event, rules=default_rules, ignore_rules=[]) == ProcessingResult(False, [])


def test_non_matching_ignore_rule_does_not_suppress() -> None:
    event = {"eventName": "StopLogging", "eventSource": "cloudtrail.amazonaws.com"}
    ignore_rules = ['event.get("userIdentity.arn", "").endswith("/automation")']
    assert should_message_be_processed(event=event, rules=default_rules, ignore_rules=ignore_rules) == ProcessingResult(True, [])


# Rules address nested fields by dotted path, with list items by index.
def test_flatten_json_paths() -> None:
    event = {
        "eventName": "RunInstances",
        "errorCode": None,
        "userIdentity": {"sessionContext": {"sessionIssuer": {"type": "Role"}}},
        "requestParameters": {"tagSpecificationSet": {"items": [{"tags": [{"key": "env", "value": "prod"}]}, {"count": 2}]}},
        "responseElements": {},
    }
    assert flatten_json(event) == {
        "eventName": "RunInstances",
        "errorCode": None,
        "userIdentity.sessionContext.sessionIssuer.type": "Role",
        "requestParameters.tagSpecificationSet.items.0.tags.0.key": "env",
        "requestParameters.tagSpecificationSet.items.0.tags.0.value": "prod",
        "requestParameters.tagSpecificationSet.items.1.count": 2,
    }
