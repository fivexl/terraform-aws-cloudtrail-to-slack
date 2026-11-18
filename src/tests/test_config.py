import json

import pytest

from config import Config, SlackAppConfig, SlackWebhookConfig, get_slack_config
from rule_evaluator import evaluate_rule
from rules import default_rules

# ruff: noqa: ANN201, ANN001, E501


# Terraform passes booleans to the Lambda as the strings "true" and "false".
@pytest.mark.parametrize(("value", "expected"), [("true", True), ("false", False), ("", False)])
def test_rule_evaluation_errors_to_slack(monkeypatch, value, expected):  # noqa: ANN001, ANN201
    monkeypatch.setenv("RULE_EVALUATION_ERRORS_TO_SLACK", value)
    assert Config().rule_evaluation_errors_to_slack is expected


@pytest.mark.parametrize(
    ("value", "expected"), [("true", True), ("True", True), ("1", True), ("false", False), ("0", False), ("yes", False)]
)
def test_boolean_env_vars(monkeypatch, value, expected):
    monkeypatch.setenv("USE_DEFAULT_RULES", value)
    monkeypatch.setenv("PUSH_ACCESS_DENIED_CLOUDWATCH_METRICS", value)
    cfg = Config()
    assert cfg.use_default_rules is expected
    assert cfg.push_access_denied_cloudwatch_metrics is expected


@pytest.fixture
def rules_env(monkeypatch):
    """Start every rules test from 'no rules configured'."""
    monkeypatch.setenv("USE_DEFAULT_RULES", "false")
    monkeypatch.setenv("RULES", "")
    monkeypatch.setenv("IGNORE_RULES", "")
    monkeypatch.setenv("EVENTS_TO_TRACK", "")
    monkeypatch.setenv("RULES_SEPARATOR", ",")
    return monkeypatch


@pytest.mark.usefixtures("rules_env")
def test_no_rules_raises():
    with pytest.raises(Exception, match="Have no rules to apply"):
        Config()


def test_rules_combine_default_user_and_events_to_track(rules_env):
    rules_env.setenv("USE_DEFAULT_RULES", "true")
    rules_env.setenv("RULES", 'event["eventName"] == "CreateUser"')
    rules_env.setenv("EVENTS_TO_TRACK", "DeleteUser")
    cfg = Config()
    assert cfg.rules[: len(default_rules)] == default_rules
    assert cfg.rules[len(default_rules)] == 'event["eventName"] == "CreateUser"'
    assert len(cfg.rules) == len(default_rules) + 2


def test_rules_split_on_custom_separator_and_drop_empty(rules_env):
    rules_env.setenv("RULES_SEPARATOR", "|")
    rules_env.setenv("RULES", 'event["eventName"] == "A"||event["eventName"] == "B, C"|')
    rules_env.setenv("IGNORE_RULES", 'event["eventName"] == "D"|')
    cfg = Config()
    assert cfg.rules == ['event["eventName"] == "A"', 'event["eventName"] == "B, C"']
    assert cfg.ignore_rules == ['event["eventName"] == "D"']


@pytest.mark.parametrize(("event_name", "expected"), [("CreateUser", True), ("CreateRole", True), ("DeleteRole", False)])
def test_events_to_track_rule_matches_listed_events(rules_env, event_name, expected):
    rules_env.setenv("EVENTS_TO_TRACK", "CreateUser, CreateRole")
    (rule,) = Config().rules
    assert evaluate_rule(rule, {"eventName": event_name}) is expected


def test_optional_settings_defaults(monkeypatch):
    for name in ("DEFAULT_SNS_TOPIC_ARN", "SNS_CONFIGURATION", "DYNAMODB_TABLE_NAME", "DYNAMODB_TIME_TO_LIVE"):
        monkeypatch.delenv(name, raising=False)
    cfg = Config()
    assert cfg.default_sns_topic_arn is None
    assert cfg.sns_configuration == []
    assert cfg.dynamodb_table_name is None
    assert cfg.dynamodb_time_to_live == 900  # noqa: PLR2004


def test_optional_settings_parsed(monkeypatch):
    sns_configuration = [{"accounts": ["111111111111"], "sns_topic_arn": "arn:aws:sns:us-east-1:111111111111:t"}]
    monkeypatch.setenv("SNS_CONFIGURATION", json.dumps(sns_configuration))
    monkeypatch.setenv("DYNAMODB_TIME_TO_LIVE", "1800")
    cfg = Config()
    assert cfg.sns_configuration == sns_configuration
    assert cfg.dynamodb_time_to_live == 1800  # noqa: PLR2004


@pytest.fixture
def slack_env(monkeypatch):
    for name in ("HOOK_URL", "CONFIGURATION", "SLACK_BOT_TOKEN", "DEFAULT_SLACK_CHANNEL_ID", "SLACK_APP_CONFIGURATION"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("raw_configuration", ["", "[]"])
def test_webhook_config(slack_env, raw_configuration):
    slack_env.setenv("HOOK_URL", "https://hooks.slack.com/services/T/B/X")
    slack_env.setenv("CONFIGURATION", raw_configuration)
    assert get_slack_config() == SlackWebhookConfig(default_hook_url="https://hooks.slack.com/services/T/B/X", configuration=[])


def test_webhook_config_with_account_routing(slack_env):
    configuration = [{"accounts": ["111111111111"], "slack_hook_url": "https://hooks.slack.com/services/T/B/PROD"}]
    slack_env.setenv("HOOK_URL", "https://hooks.slack.com/services/T/B/X")
    slack_env.setenv("CONFIGURATION", json.dumps(configuration))
    assert get_slack_config().configuration == configuration


def test_slack_app_config(slack_env):
    configuration = [{"accounts": ["111111111111"], "slack_channel_id": "C_PROD"}]
    slack_env.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    slack_env.setenv("DEFAULT_SLACK_CHANNEL_ID", "C_DEFAULT")
    slack_env.setenv("SLACK_APP_CONFIGURATION", json.dumps(configuration))
    assert get_slack_config() == SlackAppConfig(bot_token="xoxb-test", default_channel_id="C_DEFAULT", configuration=configuration)


def test_slack_app_takes_precedence_over_webhook(slack_env):
    slack_env.setenv("HOOK_URL", "https://hooks.slack.com/services/T/B/X")
    slack_env.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    slack_env.setenv("DEFAULT_SLACK_CHANNEL_ID", "C_DEFAULT")
    assert isinstance(get_slack_config(), SlackAppConfig)


# Terraform sets SLACK_BOT_TOKEN to "" when slack_bot_token is not set.
def test_empty_bot_token_falls_back_to_webhook(slack_env):
    slack_env.setenv("HOOK_URL", "https://hooks.slack.com/services/T/B/X")
    slack_env.setenv("SLACK_BOT_TOKEN", "")
    assert isinstance(get_slack_config(), SlackWebhookConfig)


def test_slack_app_without_channel_raises(slack_env):
    slack_env.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    with pytest.raises(Exception, match="DEFAULT_SLACK_CHANNEL_ID"):
        get_slack_config()


@pytest.mark.usefixtures("slack_env")
def test_no_slack_destination_raises():
    with pytest.raises(Exception, match="HOOK_URL or SLACK_BOT_TOKEN"):
        get_slack_config()
