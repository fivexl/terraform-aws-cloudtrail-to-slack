"""From S3 notification to Slack post: lambda_handler and handle_event with AWS and Slack faked at the client boundary."""

import gzip
import io
import json
from unittest.mock import MagicMock

import pytest

import main
from config import SlackAppConfig, SlackWebhookConfig

# ruff: noqa: ANN201, ANN001, E501

HOOK_URL = "https://hooks.slack.com/services/T/B/DEFAULT"
TOPIC = "arn:aws:sns:us-east-1:000000000000:events"
LOG_KEY = "AWSLogs/111111111111/CloudTrail/us-east-1/2026/01/24/file with spaces.json.gz"

CREATE_USER = {
    "eventName": "CreateUser",
    "eventTime": "2026-01-24T12:00:00Z",
    "eventID": "event-1",
    "userIdentity": {
        "type": "IAMUser",
        "principalId": "AIDAEXAMPLE",
        "arn": "arn:aws:iam::111111111111:user/alice",
        "accountId": "111111111111",
    },
}
ACCESS_DENIED = CREATE_USER | {"eventName": "GetObject", "errorCode": "AccessDenied"}


class FakeS3:
    def __init__(self, objects):  # noqa: ANN204
        self.objects = objects

    def get_object(self, Bucket, Key):  # noqa: ANN001, ANN201, N803
        return {"Body": io.BytesIO(gzip.compress(json.dumps(self.objects[(Bucket, Key)]).encode()))}


def s3_notification(*keys: str, event_name="ObjectCreated:Put"):
    return {
        "Records": [
            {
                "eventName": event_name,
                "eventTime": "2026-01-24T12:00:00Z",
                "userIdentity": {"principalId": "AWS:AIDAEXAMPLE"},
                "s3": {"bucket": {"name": "trail-bucket"}, "object": {"key": key}},
            }
            for key in keys
        ]
    }


@pytest.fixture
def slack_posts(monkeypatch, fake_sns, fake_dynamodb):
    """Isolate main's module-level config and clients; return the webhook posts as (hook_url, message)."""
    for name, value in {
        "rules": ['event["eventName"] == "CreateUser"'],
        "ignore_rules": [],
        "rule_evaluation_errors_to_slack": False,
        "push_access_denied_cloudwatch_metrics": False,
        "default_sns_topic_arn": None,
        "sns_configuration": [],
        "dynamodb_table_name": "threads",
    }.items():
        monkeypatch.setattr(main.cfg, name, value)
    monkeypatch.setattr(main, "slack_config", SlackWebhookConfig(default_hook_url=HOOK_URL, configuration=[]))
    monkeypatch.setattr(main, "sns_client", fake_sns)
    monkeypatch.setattr(main, "dynamodb_client", fake_dynamodb)
    monkeypatch.setattr(main, "cloudwatch_client", MagicMock())
    posts = []
    monkeypatch.setattr("slack_helpers.webhook_post_message", lambda message, hook_url: posts.append((hook_url, message)))
    return posts


def posted_text(posts):
    return [json.dumps(message) for _, message in posts]


def test_log_file_events_are_posted(monkeypatch, slack_posts):
    other = CREATE_USER | {"eventName": "ListUsers", "eventID": "event-2"}
    monkeypatch.setattr(main, "s3_client", FakeS3({("trail-bucket", LOG_KEY): {"Records": [other, CREATE_USER]}}))

    # S3 notifications URL-encode the object key.
    assert main.lambda_handler(s3_notification(LOG_KEY.replace(" ", "%20")), None) == 200  # noqa: PLR2004

    (text,) = posted_text(slack_posts)
    assert "event-1" in text
    assert LOG_KEY in text


def test_failure_to_read_log_file_is_reported_to_slack(monkeypatch, slack_posts):
    monkeypatch.setattr(main, "s3_client", FakeS3({}))
    assert main.lambda_handler(s3_notification("AWSLogs/missing.json.gz"), None) == 200  # noqa: PLR2004
    (text,) = posted_text(slack_posts)
    assert "Failed to process event" in text
    assert "AWSLogs/missing.json.gz" in text


def test_removed_log_file_is_reported_to_slack(slack_posts):
    main.lambda_handler(s3_notification(LOG_KEY, event_name="ObjectRemoved:Delete"), None)
    (text,) = posted_text(slack_posts)
    assert "ObjectRemoved:Delete" in text
    assert LOG_KEY in text


def test_digest_file_does_not_stop_other_records(monkeypatch, slack_posts):
    monkeypatch.setattr(main, "s3_client", FakeS3({("trail-bucket", "AWSLogs/log.json.gz"): {"Records": [CREATE_USER]}}))
    main.lambda_handler(s3_notification("AWSLogs/CloudTrail-Digest/digest.json.gz", "AWSLogs/log.json.gz"), None)
    assert len(slack_posts) == 1


def test_matched_event_is_posted_and_forwarded_to_sns(monkeypatch, slack_posts, fake_sns):
    monkeypatch.setattr(main.cfg, "default_sns_topic_arn", TOPIC)
    main.handle_event(CREATE_USER, LOG_KEY, main.cfg.rules, [])
    assert [hook_url for hook_url, _ in slack_posts] == [HOOK_URL]
    assert [p["TopicArn"] for p in fake_sns.published] == [TOPIC]


@pytest.mark.parametrize(
    ("rules", "ignore_rules"),
    [(['event["eventName"] == "DeleteUser"'], []), (['event["eventName"] == "CreateUser"'], ['event["userIdentity.type"] == "IAMUser"'])],
    ids=["not_matched", "ignored"],
)
def test_unmatched_or_ignored_event_is_dropped(monkeypatch, slack_posts, fake_sns, rules, ignore_rules):
    monkeypatch.setattr(main.cfg, "default_sns_topic_arn", TOPIC)
    main.handle_event(CREATE_USER, LOG_KEY, rules, ignore_rules)
    assert slack_posts == []
    assert fake_sns.published == []


@pytest.mark.parametrize("enabled", [True, False])
def test_rule_evaluation_errors_go_to_slack_only_when_enabled(monkeypatch, slack_posts, enabled):
    monkeypatch.setattr(main.cfg, "rule_evaluation_errors_to_slack", enabled)
    main.handle_event(CREATE_USER, LOG_KEY, ["undefined_name"], [])
    texts = posted_text(slack_posts)
    assert len(texts) == int(enabled)
    if enabled:
        assert "Failed to evaluate rule" in texts[0]
        assert "undefined_name" in texts[0]


@pytest.mark.parametrize(
    ("enabled", "ignore_rules", "metrics"),
    [
        (False, [], []),
        (True, [], ["TotalAccessDeniedEvents"]),
        (True, ['event["errorCode"] == "AccessDenied"'], ["TotalAccessDeniedEvents", "TotalIgnoredAccessDeniedEvents"]),
    ],
    ids=["disabled", "reported", "ignored"],
)
def test_access_denied_metrics(monkeypatch, slack_posts, enabled, ignore_rules, metrics):  # noqa: ARG001
    monkeypatch.setattr(main.cfg, "push_access_denied_cloudwatch_metrics", enabled)
    main.handle_event(ACCESS_DENIED, LOG_KEY, ['event["errorCode"] == "AccessDenied"'], ignore_rules)
    calls = main.cloudwatch_client.put_metric_data.call_args_list
    assert [c.kwargs["MetricData"][0]["MetricName"] for c in calls] == metrics
    assert all(c.kwargs["Namespace"] == "CloudTrailToSlack/AccessDeniedEvents" for c in calls)


def test_metric_failure_does_not_block_slack_post(monkeypatch, slack_posts):
    monkeypatch.setattr(main.cfg, "push_access_denied_cloudwatch_metrics", True)
    main.cloudwatch_client.put_metric_data.side_effect = Exception("throttled")
    main.handle_event(ACCESS_DENIED, LOG_KEY, ['event["errorCode"] == "AccessDenied"'], [])
    assert len(slack_posts) == 1


def test_slack_app_threads_repeated_events(monkeypatch, slack_posts):  # noqa: ARG001
    monkeypatch.setattr(main, "slack_config", SlackAppConfig(bot_token="xoxb-test", default_channel_id="C_DEFAULT", configuration=[]))
    web_client = MagicMock()
    web_client.return_value.chat_postMessage.return_value = {"ok": True, "ts": "1700000000.000100"}
    monkeypatch.setattr("slack_helpers.WebClient", web_client)

    main.handle_event(CREATE_USER, LOG_KEY, main.cfg.rules, [])
    main.handle_event(CREATE_USER | {"eventID": "event-2"}, LOG_KEY, main.cfg.rules, [])

    calls = web_client.return_value.chat_postMessage.call_args_list
    assert [c.kwargs["thread_ts"] for c in calls] == [None, "1700000000.000100"]
