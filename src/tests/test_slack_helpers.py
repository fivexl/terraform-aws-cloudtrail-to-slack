import json
from unittest.mock import patch

import pytest

from config import SlackAppConfig, SlackWebhookConfig
from slack_helpers import (
    event_to_slack_message,
    message_for_rule_evaluation_error_notification,
    message_for_slack_error_notification,
    post_message,
    webhook_post_message,
)

# ruff: noqa: ANN201, ANN001, E501

MESSAGE = {"blocks": [{"type": "divider"}]}


@pytest.mark.parametrize(
    ("account_id", "hook_url"),
    [
        ("111111111111", "https://hooks.slack.com/services/PROD"),
        ("999999999999", "https://hooks.slack.com/services/DEFAULT"),
        (None, "https://hooks.slack.com/services/DEFAULT"),
    ],
)
def test_webhook_routing_by_account(account_id, hook_url):
    slack_config = SlackWebhookConfig(
        default_hook_url="https://hooks.slack.com/services/DEFAULT",
        configuration=[{"accounts": ["111111111111"], "slack_hook_url": "https://hooks.slack.com/services/PROD"}],
    )
    with patch("slack_helpers.webhook_post_message") as webhook:
        post_message(slack_config=slack_config, message=MESSAGE, account_id=account_id)
    webhook.assert_called_once_with(message=MESSAGE, hook_url=hook_url)


@pytest.mark.parametrize(
    ("account_id", "channel_id"),
    [("111111111111", "C_PROD"), ("999999999999", "C_DEFAULT"), (None, "C_DEFAULT")],
)
def test_slack_app_routing_by_account(account_id, channel_id):
    slack_config = SlackAppConfig(
        bot_token="xoxb-test",
        default_channel_id="C_DEFAULT",
        configuration=[{"accounts": ["111111111111"], "slack_channel_id": "C_PROD"}],
    )
    with patch("slack_helpers.WebClient") as web_client:
        post_message(slack_config=slack_config, message=MESSAGE, account_id=account_id, thread_ts="1700000000.000100")
    web_client.assert_called_once_with(token="xoxb-test")
    kwargs = web_client.return_value.chat_postMessage.call_args.kwargs
    assert kwargs["channel"] == channel_id
    assert kwargs["thread_ts"] == "1700000000.000100"
    assert kwargs["blocks"] == MESSAGE["blocks"]


def test_webhook_posts_to_hook_path():
    with patch("http.client.HTTPSConnection") as connection:
        connection.return_value.getresponse.return_value.status = 200
        connection.return_value.getresponse.return_value.read.return_value = b"ok"
        assert webhook_post_message(MESSAGE, "https://hooks.slack.com/services/T1/B2/X3") == 200  # noqa: PLR2004
    connection.assert_called_once_with("hooks.slack.com")
    method, path, body, _headers = connection.return_value.request.call_args.args
    assert (method, path, json.loads(body)) == ("POST", "/services/T1/B2/X3", MESSAGE)


def slack_text(message):
    return json.dumps(message["blocks"])


def make_event(**fields: object):
    return {
        "eventName": "CreateUser",
        "eventTime": "2026-01-24T12:00:00Z",
        "eventID": "event-id-123",
        "userIdentity": {"arn": "arn:aws:iam::111111111111:user/alice", "accountId": "111111111111"},
    } | fields


def test_slack_message_content():
    message = event_to_slack_message(
        make_event(requestParameters={"userName": "bob"}, responseElements={"user": {"userId": "AIDABOB"}}),
        "AWSLogs/111111111111/CloudTrail/file.json.gz",
        "222222222222",
    )
    assert message["blocks"][0]["text"]["text"] == "*arn:aws:iam::111111111111:user/alice* called *CreateUser*"
    assert message["blocks"][-1] == {"type": "divider"}
    text = slack_text(message)
    for expected in ("bob", "AIDABOB", "event-id-123", "Account Id: 222222222222", "AWSLogs/111111111111/CloudTrail/file.json.gz"):
        assert expected in text


def test_slack_message_for_failed_call():
    message = event_to_slack_message(make_event(errorCode="AccessDenied", errorMessage="not authorized"), "f", "111111111111")
    assert message["blocks"][0]["text"]["text"].startswith(":warning:")
    assert "AccessDenied" in message["blocks"][0]["text"]["text"]
    assert "not authorized" in slack_text(message)


@pytest.mark.parametrize(("mfa_used", "warned"), [("No", True), ("Yes", False)])
def test_console_login_without_mfa_is_flagged(mfa_used, warned):
    event = make_event(eventName="ConsoleLogin", additionalEventData={"MFAUsed": mfa_used})
    assert ("Login without MFA" in slack_text(event_to_slack_message(event, "f", "111111111111"))) is warned


@pytest.mark.parametrize(("keys", "expected"), [(["a.json.gz"], "a.json.gz"), (["a.json.gz", "b.json.gz"], "a.json.gz\n b.json.gz")])
def test_processing_error_message_lists_objects(keys, expected):
    s3_event = {"Records": [{"s3": {"object": {"key": key}}} for key in keys]}
    message = message_for_slack_error_notification(Exception("boom"), s3_event)
    assert "boom" in slack_text(message)
    assert message["blocks"][-1]["elements"][0]["text"] == expected


def test_rule_evaluation_error_message():
    message = message_for_rule_evaluation_error_notification(NameError("name 'x' is not defined"), "AWSLogs/f.json.gz", "x == 1")
    text = slack_text(message)
    for expected in ("Failed to evaluate rule", "x == 1", "name 'x' is not defined", "AWSLogs/f.json.gz"):
        assert expected in text
