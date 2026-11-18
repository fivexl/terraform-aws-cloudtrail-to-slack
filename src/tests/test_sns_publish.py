"""Forwarding matched events to SNS (default_sns_topic_arn / sns_configuration)."""

import json
from types import SimpleNamespace

import pytest

from config import Config
from sns import event_to_sns_message, send_message_to_sns

# ruff: noqa: ANN201, ANN001

DEFAULT_TOPIC = "arn:aws:sns:us-east-1:000000000000:default"
PROD_TOPIC = "arn:aws:sns:us-east-1:000000000000:prod"

EVENT = {
    "eventName": "DeleteBucket",
    "eventTime": "2026-01-24T12:00:00Z",
    "eventID": "abc-123",
    "errorCode": "AccessDenied",
    "errorMessage": "User is not authorized",
    "requestParameters": {"bucketName": "my-bucket"},
    "responseElements": None,
    "additionalEventData": {"SignatureVersion": "SigV4"},
    "userIdentity": {"arn": "arn:aws:iam::111111111111:user/alice", "accountId": "111111111111"},
}


# Subscribers parse this payload, so its shape is a public contract.
def test_sns_message_payload():
    assert event_to_sns_message(EVENT, "AWSLogs/file.json.gz", "111111111111") == {
        "title": "arn:aws:iam::111111111111:user/alice called DeleteBucket but failed due to AccessDenied",
        "error_message": "User is not authorized",
        "request_parameters": {"bucketName": "my-bucket"},
        "response_elements": None,
        "additional_details": {"SignatureVersion": "SigV4"},
        "account_id": "111111111111",
        "event_time": "2026-01-24 12:00:00+00:00",
        "event_id": "abc-123",
        "actor": "arn:aws:iam::111111111111:user/alice",
        "source_file": "AWSLogs/file.json.gz",
    }


def test_sns_message_without_identity():
    event = {"eventName": "CreateUser", "eventTime": "2026-01-24T12:00:00Z"}
    message = event_to_sns_message(event, "f", None)
    assert message["title"] == "Unknown Identity called CreateUser"
    assert message["account_id"] == "N/A"
    assert message["event_id"] == "N/A"


def test_nothing_published_without_default_topic(fake_sns):
    cfg = SimpleNamespace(default_sns_topic_arn=None, sns_configuration=[{"accounts": ["111111111111"], "sns_topic_arn": PROD_TOPIC}])
    send_message_to_sns(event=EVENT, source_file="f", account_id="111111111111", cfg=cfg, sns_client=fake_sns)
    assert fake_sns.published == []


@pytest.mark.parametrize(
    ("account_id", "topic"),
    [
        ("111111111111", PROD_TOPIC),
        ("222222222222", PROD_TOPIC),
        ("333333333333", DEFAULT_TOPIC),
        ("", DEFAULT_TOPIC),
        (None, DEFAULT_TOPIC),
    ],
)
def test_topic_routing_by_account(fake_sns, account_id, topic):
    cfg = SimpleNamespace(
        default_sns_topic_arn=DEFAULT_TOPIC,
        sns_configuration=[{"accounts": ["111111111111", "222222222222"], "sns_topic_arn": PROD_TOPIC}],
    )
    send_message_to_sns(event=EVENT, source_file="f", account_id=account_id, cfg=cfg, sns_client=fake_sns)
    (published,) = fake_sns.published
    assert published["TopicArn"] == topic
    assert json.loads(published["Message"])["event_id"] == "abc-123"


def test_default_topic_without_sns_configuration(rules_env, fake_sns):
    rules_env.setenv("RULES", 'event["eventName"] == "DeleteBucket"')
    rules_env.setenv("DEFAULT_SNS_TOPIC_ARN", DEFAULT_TOPIC)
    rules_env.setenv("SNS_CONFIGURATION", "null")
    send_message_to_sns(event=EVENT, source_file="f", account_id="111111111111", cfg=Config(), sns_client=fake_sns)
    assert fake_sns.published[0]["TopicArn"] == DEFAULT_TOPIC
