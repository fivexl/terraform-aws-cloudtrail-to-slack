import json

import pytest

from config import Config, SlackAppConfig, SlackWebhookConfig, get_slack_config
from rule_evaluator import evaluate_rule
from rules import default_rules

# ruff: noqa: ANN201, ANN001


# Terraform passes booleans to the Lambda as the strings "true" and "false".
@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("True", True), ("1", True), ("false", False), ("0", False), ("yes", False), ("", False)],
)
@pytest.mark.parametrize(
    ("env_var", "attribute"),
    [
        ("RULE_EVALUATION_ERRORS_TO_SLACK", "rule_evaluation_errors_to_slack"),
        ("USE_DEFAULT_RULES", "use_default_rules"),
        ("PUSH_ACCESS_DENIED_CLOUDWATCH_METRICS", "push_access_denied_cloudwatch_metrics"),
    ],
)
def test_boolean_env_vars(rules_env, env_var, attribute, value, expected):
    rules_env.setenv("RULES", 'event["eventName"] == "CreateUser"')
    rules_env.setenv(env_var, value)
    assert getattr(Config(), attribute) is expected


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


def test_optional_settings_defaults(rules_env):
    rules_env.setenv("RULES", 'event["eventName"] == "CreateUser"')
    for name in ("DEFAULT_SNS_TOPIC_ARN", "SNS_CONFIGURATION", "DYNAMODB_TABLE_NAME", "DYNAMODB_TIME_TO_LIVE"):
        rules_env.delenv(name, raising=False)
    cfg = Config()
    assert cfg.default_sns_topic_arn is None
    assert cfg.sns_configuration == []
    assert cfg.dynamodb_table_name is None
    assert cfg.dynamodb_time_to_live == 900  # noqa: PLR2004


def test_optional_settings_parsed(rules_env):
    rules_env.setenv("RULES", 'event["eventName"] == "CreateUser"')
    sns_configuration = [{"accounts": ["111111111111"], "sns_topic_arn": "arn:aws:sns:us-east-1:111111111111:t"}]
    rules_env.setenv("SNS_CONFIGURATION", json.dumps(sns_configuration))
    rules_env.setenv("DYNAMODB_TIME_TO_LIVE", "1800")
    cfg = Config()
    assert cfg.sns_configuration == sns_configuration
    assert cfg.dynamodb_time_to_live == 1800  # noqa: PLR2004


@pytest.fixture
def slack_env(monkeypatch):
    for name in ("HOOK_URL", "CONFIGURATION", "SLACK_BOT_TOKEN", "DEFAULT_SLACK_CHANNEL_ID", "SLACK_APP_CONFIGURATION"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


LIST_CONFIGURATIONS = pytest.mark.parametrize(
    ("env_var", "read_configuration"),
    [
        ("CONFIGURATION", lambda: get_slack_config().configuration),
        ("SLACK_APP_CONFIGURATION", lambda: get_slack_config().configuration),
        ("SNS_CONFIGURATION", lambda: Config().sns_configuration),
    ],
    ids=["CONFIGURATION", "SLACK_APP_CONFIGURATION", "SNS_CONFIGURATION"],
)


def set_list_configuration(env, env_var, raw_value):
    env.setenv("RULES", 'event["eventName"] == "CreateUser"')
    if env_var == "SLACK_APP_CONFIGURATION":
        env.setenv("SLACK_BOT_TOKEN", "xoxb-test")
        env.setenv("DEFAULT_SLACK_CHANNEL_ID", "C_DEFAULT")
    else:
        env.setenv("HOOK_URL", "https://hooks.slack.com/services/T/B/X")
    env.delenv(env_var, raising=False)
    if raw_value is not None:
        env.setenv(env_var, raw_value)


# Terraform renders an unset list input as jsonencode(null), the string "null".
@pytest.mark.parametrize("raw_value", [None, "", "null", "[]"], ids=["unset", "empty", "null", "empty_list"])
@LIST_CONFIGURATIONS
@pytest.mark.usefixtures("rules_env")
def test_unset_list_configuration_is_empty(slack_env, env_var, read_configuration, raw_value):
    set_list_configuration(slack_env, env_var, raw_value)
    assert read_configuration() == []


@LIST_CONFIGURATIONS
@pytest.mark.usefixtures("rules_env")
def test_other_configuration_values_are_kept(slack_env, env_var, read_configuration):
    set_list_configuration(slack_env, env_var, "{}")
    assert read_configuration() == {}


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
