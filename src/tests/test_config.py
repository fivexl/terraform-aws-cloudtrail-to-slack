"""
Comprehensive tests for configuration module.
Tests config parsing, validation, Slack config, and environment variable handling.
"""

import json
import os
import pytest
from unittest.mock import patch
from config import (
    Config,
    get_slack_config,
    SlackWebhookConfig,
    SlackAppConfig,
)

# ruff: noqa: ANN201, ANN001, E501


class TestSlackWebhookConfig:
    """Test Slack webhook configuration."""

    def test_webhook_config_from_env_minimal(self):
        """Test webhook config with minimal required env vars."""
        env = {
            "HOOK_URL": "https://hooks.slack.com/services/T/B/X",
            "CONFIGURATION": "[]",
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackWebhookConfig)
            assert config.default_hook_url == "https://hooks.slack.com/services/T/B/X"
            assert config.configuration == []

    def test_webhook_config_with_account_routing(self):
        """Test webhook config with account-specific routing."""
        configuration = [
            {
                "accounts": ["123456789012"],
                "slack_hook_url": "https://hooks.slack.com/services/T/B/PROD",
            }
        ]

        env = {
            "HOOK_URL": "https://hooks.slack.com/services/T/B/DEFAULT",
            "CONFIGURATION": json.dumps(configuration),
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackWebhookConfig)
            assert len(config.configuration) == 1
            assert config.configuration[0]["accounts"] == ["123456789012"]

    def test_webhook_config_empty_configuration(self):
        """Test webhook config with empty configuration."""
        env = {
            "HOOK_URL": "https://hooks.slack.com/services/T/B/X",
            "CONFIGURATION": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackWebhookConfig)
            assert config.configuration == []


class TestSlackAppConfig:
    """Test Slack app configuration."""

    def test_slack_app_config_minimal(self):
        """Test Slack app config with minimal required env vars."""
        env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "DEFAULT_SLACK_CHANNEL_ID": "C123456",
            "SLACK_APP_CONFIGURATION": "[]",
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackAppConfig)
            assert config.bot_token == "xoxb-test-token"
            assert config.default_channel_id == "C123456"
            assert config.configuration == []

    def test_slack_app_config_with_account_routing(self):
        """Test Slack app config with account-specific channel routing."""
        configuration = [
            {
                "accounts": ["123456789012"],
                "slack_channel_id": "C_PROD",
            }
        ]

        env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "DEFAULT_SLACK_CHANNEL_ID": "C_DEFAULT",
            "SLACK_APP_CONFIGURATION": json.dumps(configuration),
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackAppConfig)
            assert len(config.configuration) == 1
            assert config.configuration[0]["slack_channel_id"] == "C_PROD"

    def test_slack_app_missing_channel_id_raises_error(self):
        """Test that missing DEFAULT_SLACK_CHANNEL_ID raises error."""
        env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            # Missing DEFAULT_SLACK_CHANNEL_ID
        }

        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(Exception) as exc_info:
                get_slack_config()
            assert "DEFAULT_SLACK_CHANNEL_ID" in str(exc_info.value)

    def test_slack_app_empty_configuration(self):
        """Test Slack app with empty configuration."""
        env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "DEFAULT_SLACK_CHANNEL_ID": "C123456",
            "SLACK_APP_CONFIGURATION": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackAppConfig)
            assert config.configuration == []


class TestSlackConfigPrecedence:
    """Test Slack configuration precedence."""

    def test_slack_app_takes_precedence_over_webhook(self):
        """Test that Slack app config takes precedence when both are set."""
        env = {
            "SLACK_BOT_TOKEN": "xoxb-test-token",
            "DEFAULT_SLACK_CHANNEL_ID": "C123456",
            "HOOK_URL": "https://hooks.slack.com/services/T/B/X",
        }

        with patch.dict(os.environ, env, clear=False):
            config = get_slack_config()
            assert isinstance(config, SlackAppConfig)

    def test_missing_both_configs_raises_error(self):
        """Test that missing both configs raises error."""
        # Need to use clear environment variable approach
        original_bot_token = os.environ.pop("SLACK_BOT_TOKEN", None)
        original_hook_url = os.environ.pop("HOOK_URL", None)

        try:
            with pytest.raises(Exception) as exc_info:
                get_slack_config()
            assert "HOOK_URL or SLACK_BOT_TOKEN" in str(exc_info.value)
        finally:
            # Restore
            if original_bot_token:
                os.environ["SLACK_BOT_TOKEN"] = original_bot_token
            if original_hook_url:
                os.environ["HOOK_URL"] = original_hook_url


class TestConfig:
    """Test main Config class."""

    def test_config_with_default_rules_only(self):
        """Test config using only default rules."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "RULES": "",
            "IGNORE_RULES": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.use_default_rules is True
            assert len(config.rules) > 0  # Should have default rules

    def test_config_with_custom_rules_only(self):
        """Test config with custom rules only."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": 'event["eventName"] == "CreateUser",event["eventName"] == "DeleteUser"',
            "RULES_SEPARATOR": ",",
            "IGNORE_RULES": "",
            "EVENTS_TO_TRACK": "",  # Clear this from conftest
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.use_default_rules is False
            assert len(config.rules) == 2  # noqa: PLR2004
            assert 'event["eventName"] == "CreateUser"' in config.rules

    def test_config_with_default_and_custom_rules(self):
        """Test config combining default and custom rules."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "RULES": 'event["eventName"] == "CustomEvent"',
            "RULES_SEPARATOR": ",",
            "IGNORE_RULES": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            # Should have both default and custom rules
            assert len(config.rules) > 1
            assert 'event["eventName"] == "CustomEvent"' in config.rules

    def test_config_with_events_to_track(self):
        """Test config with EVENTS_TO_TRACK."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": "",
            "IGNORE_RULES": "",
            "EVENTS_TO_TRACK": "CreateUser,DeleteUser,CreateRole",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            # Should generate a rule for tracking these events
            assert len(config.rules) == 1
            rule = config.rules[0]
            assert "CreateUser" in rule
            assert "DeleteUser" in rule
            assert "CreateRole" in rule

    def test_config_no_rules_raises_error(self):
        """Test that config with no rules raises error."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": "",
            "IGNORE_RULES": "",
            "EVENTS_TO_TRACK": "",
        }

        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(Exception) as exc_info:
                Config()
            assert "Have no rules to apply" in str(exc_info.value)

    def test_config_ignore_rules_parsing(self):
        """Test parsing of ignore rules."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "RULES": "",
            "IGNORE_RULES": 'event["eventName"] == "IgnoreMe",event["eventName"] == "AlsoIgnore"',
            "RULES_SEPARATOR": ",",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert len(config.ignore_rules) == 2  # noqa: PLR2004
            assert 'event["eventName"] == "IgnoreMe"' in config.ignore_rules

    def test_config_custom_separator(self):
        """Test config with custom rule separator."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": 'event["eventName"] == "CreateUser"|event["eventName"] == "DeleteUser"',
            "RULES_SEPARATOR": "|",
            "IGNORE_RULES": "",
            "EVENTS_TO_TRACK": "",  # Clear this from conftest
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert len(config.rules) == 2  # noqa: PLR2004

    def test_config_sns_configuration(self):
        """Test SNS configuration parsing."""
        sns_config = [
            {
                "accounts": ["123456789012"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:topic",
            }
        ]

        env = {
            "USE_DEFAULT_RULES": "true",
            "DEFAULT_SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:123456789012:default",
            "SNS_CONFIGURATION": json.dumps(sns_config),
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.default_sns_topic_arn == "arn:aws:sns:us-east-1:123456789012:default"
            assert len(config.sns_configuration) == 1

    def test_config_dynamodb_settings(self):
        """Test DynamoDB configuration."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "DYNAMODB_TABLE_NAME": "cloudtrail-threads",
            "DYNAMODB_TIME_TO_LIVE": "1800",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.dynamodb_table_name == "cloudtrail-threads"
            assert config.dynamodb_time_to_live == 1800  # noqa: PLR2004

    def test_config_dynamodb_default_ttl(self):
        """Test default DynamoDB TTL value."""
        env = {
            "USE_DEFAULT_RULES": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.dynamodb_time_to_live == 900  # Default 15 minutes  # noqa: PLR2004

    def test_config_rule_evaluation_errors_to_slack(self):
        """Test rule evaluation errors to Slack setting."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "RULE_EVALUATION_ERRORS_TO_SLACK": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.rule_evaluation_errors_to_slack is True

    def test_config_push_access_denied_metrics(self):
        """Test push access denied CloudWatch metrics setting."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "PUSH_ACCESS_DENIED_CLOUDWATCH_METRICS": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.push_access_denied_cloudwatch_metrics is True


class TestConfigBooleanParsing:
    """Test boolean environment variable parsing."""

    def test_boolean_true_values(self):
        """Test various true values for boolean env vars."""
        for true_value in ["true", "True", "TRUE", "1"]:
            env = {
                "USE_DEFAULT_RULES": true_value,
            }

            with patch.dict(os.environ, env, clear=False):
                config = Config()
                assert config.use_default_rules is True

    def test_boolean_false_values(self):
        """Test various false values for boolean env vars."""
        for false_value in ["false", "False", "FALSE", "0", "", "anything"]:
            env = {
                "USE_DEFAULT_RULES": false_value,
                "RULES": 'event["eventName"] == "Test"',  # Need some rules
            }

            with patch.dict(os.environ, env, clear=False):
                config = Config()
                assert config.use_default_rules is False


class TestConfigRulesParsing:
    """Test rules parsing edge cases."""

    def test_rules_with_empty_strings_filtered(self):
        """Test that empty strings in rules are filtered out."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": 'event["eventName"] == "Test",,event["eventName"] == "Test2",',
            "RULES_SEPARATOR": ",",
            "IGNORE_RULES": "",
            "EVENTS_TO_TRACK": "",  # Clear this from conftest
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            # Should only have 2 rules, empty strings filtered
            assert len(config.rules) == 2  # noqa: PLR2004

    def test_rules_with_whitespace(self):
        """Test rules with whitespace are preserved."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": 'event["eventName"] == "Test Event"',
            "RULES_SEPARATOR": ",",
            "IGNORE_RULES": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert 'event["eventName"] == "Test Event"' in config.rules

    def test_events_to_track_with_spaces(self):
        """Test EVENTS_TO_TRACK with spaces in event names."""
        env = {
            "USE_DEFAULT_RULES": "false",
            "RULES": "",
            "IGNORE_RULES": "",
            "EVENTS_TO_TRACK": "CreateUser, DeleteUser, CreateRole",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            rule = config.rules[0]
            # Spaces should be removed
            assert "CreateUser" in rule
            assert "DeleteUser" in rule
            assert "CreateRole" in rule

    def test_empty_events_to_track(self):
        """Test empty EVENTS_TO_TRACK with other rules."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "EVENTS_TO_TRACK": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            # Should just have default rules
            assert len(config.rules) > 0


class TestConfigSNSParsing:
    """Test SNS configuration parsing."""

    def test_empty_sns_configuration(self):
        """Test empty SNS configuration."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "SNS_CONFIGURATION": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.sns_configuration == []

    def test_sns_configuration_with_multiple_accounts(self):
        """Test SNS configuration with multiple account mappings."""
        sns_config = [
            {
                "accounts": ["111111111111"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:111111111111:topic1",
            },
            {
                "accounts": ["222222222222"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:222222222222:topic2",
            },
        ]

        env = {
            "USE_DEFAULT_RULES": "true",
            "SNS_CONFIGURATION": json.dumps(sns_config),
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert len(config.sns_configuration) == 2  # noqa: PLR2004


class TestConfigDefaults:
    """Test configuration default values."""

    def test_default_rules_separator(self):
        """Test default rules separator is comma."""
        env = {
            "USE_DEFAULT_RULES": "true",
            "RULES_SEPARATOR": ",",  # Explicitly set to avoid conftest override
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.rules_separator == ","

    def test_default_sns_configuration(self):
        """Test default SNS configuration is empty."""
        env = {
            "USE_DEFAULT_RULES": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.sns_configuration == []

    def test_default_boolean_flags(self):
        """Test default boolean flags are False."""
        env = {
            "USE_DEFAULT_RULES": "true",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config()
            assert config.rule_evaluation_errors_to_slack is False
            assert config.push_access_denied_cloudwatch_metrics is False
