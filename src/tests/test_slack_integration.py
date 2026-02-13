"""
Comprehensive tests for Slack integration.
Tests message posting, formatting, webhooks, Slack app integration, and error handling.
"""

import json
from unittest.mock import Mock, patch
from slack_helpers import (
    post_message,
    event_to_slack_message,
    message_for_slack_error_notification,
    message_for_rule_evaluation_error_notification,
    webhook_post_message,
    slack_app_post_message,
)
from config import SlackWebhookConfig, SlackAppConfig

# ruff: noqa: ANN201, ANN001, E501


class TestPostMessage:
    """Test the main post_message routing function."""

    def test_post_message_with_webhook_config(self):
        """Test posting with webhook configuration."""
        webhook_config = SlackWebhookConfig(
            default_hook_url="https://hooks.slack.com/services/TEST/HOOK/URL",
            configuration=[],
        )

        message = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Test"}}]}

        with patch("slack_helpers.webhook_post_message") as mock_webhook:
            mock_webhook.return_value = 200
            post_message(slack_config=webhook_config, message=message)
            assert mock_webhook.called
            assert mock_webhook.call_args[1]["message"] == message

    def test_post_message_with_slack_app_config(self):
        """Test posting with Slack app configuration."""
        app_config = SlackAppConfig(
            bot_token="xoxb-test-token",
            default_channel_id="C123456",
            configuration=[],
        )

        message = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Test"}}]}

        with patch("slack_helpers.slack_app_post_message") as mock_app:
            post_message(slack_config=app_config, message=message)
            assert mock_app.called
            assert mock_app.call_args[1]["message"] == message
            assert mock_app.call_args[1]["channel_id"] == "C123456"

    def test_webhook_account_routing(self):
        """Test that webhook routes to correct URL based on account."""
        webhook_config = SlackWebhookConfig(
            default_hook_url="https://hooks.slack.com/services/DEFAULT",
            configuration=[
                {
                    "accounts": ["123456789012"],
                    "slack_hook_url": "https://hooks.slack.com/services/ACCOUNT_SPECIFIC",
                }
            ],
        )

        message = {"blocks": []}

        with patch("slack_helpers.webhook_post_message") as mock_webhook:
            mock_webhook.return_value = 200
            post_message(slack_config=webhook_config, message=message, account_id="123456789012")
            # Should use account-specific URL
            assert mock_webhook.call_args[1]["hook_url"] == "https://hooks.slack.com/services/ACCOUNT_SPECIFIC"

    def test_webhook_default_routing(self):
        """Test that webhook uses default URL when account not in config."""
        webhook_config = SlackWebhookConfig(
            default_hook_url="https://hooks.slack.com/services/DEFAULT",
            configuration=[
                {
                    "accounts": ["123456789012"],
                    "slack_hook_url": "https://hooks.slack.com/services/ACCOUNT_SPECIFIC",
                }
            ],
        )

        message = {"blocks": []}

        with patch("slack_helpers.webhook_post_message") as mock_webhook:
            mock_webhook.return_value = 200
            post_message(slack_config=webhook_config, message=message, account_id="999999999999")
            # Should use default URL
            assert mock_webhook.call_args[1]["hook_url"] == "https://hooks.slack.com/services/DEFAULT"

    def test_slack_app_account_routing(self):
        """Test that Slack app routes to correct channel based on account."""
        app_config = SlackAppConfig(
            bot_token="xoxb-test-token",
            default_channel_id="C_DEFAULT",
            configuration=[
                {
                    "accounts": ["123456789012"],
                    "slack_channel_id": "C_PROD",
                }
            ],
        )

        message = {"blocks": []}

        with patch("slack_helpers.slack_app_post_message") as mock_app:
            post_message(slack_config=app_config, message=message, account_id="123456789012")
            # Should use account-specific channel
            assert mock_app.call_args[1]["channel_id"] == "C_PROD"

    def test_slack_app_default_channel(self):
        """Test that Slack app uses default channel when account not in config."""
        app_config = SlackAppConfig(
            bot_token="xoxb-test-token",
            default_channel_id="C_DEFAULT",
            configuration=[
                {
                    "accounts": ["123456789012"],
                    "slack_channel_id": "C_PROD",
                }
            ],
        )

        message = {"blocks": []}

        with patch("slack_helpers.slack_app_post_message") as mock_app:
            post_message(slack_config=app_config, message=message, account_id="999999999999")
            # Should use default channel
            assert mock_app.call_args[1]["channel_id"] == "C_DEFAULT"

    def test_slack_app_thread_ts_passed(self):
        """Test that thread_ts is properly passed to Slack app."""
        app_config = SlackAppConfig(
            bot_token="xoxb-test-token",
            default_channel_id="C123456",
            configuration=[],
        )

        message = {"blocks": []}

        with patch("slack_helpers.slack_app_post_message") as mock_app:
            post_message(slack_config=app_config, message=message, thread_ts="1234567890.123456")
            assert mock_app.call_args[1]["thread_ts"] == "1234567890.123456"


class TestWebhookPostMessage:
    """Test webhook message posting."""

    def test_successful_webhook_post(self):
        """Test successful webhook message posting."""
        message = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Test"}}]}
        hook_url = "https://hooks.slack.com/services/T/B/X"

        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b"ok"

        with patch("http.client.HTTPSConnection") as mock_conn:
            mock_conn.return_value.getresponse.return_value = mock_response
            status = webhook_post_message(message, hook_url)
            assert status == 200  # noqa: PLR2004

    def test_webhook_post_with_error_status(self):
        """Test webhook posting with error response."""
        message = {"blocks": []}
        hook_url = "https://hooks.slack.com/services/T/B/X"

        mock_response = Mock()
        mock_response.status = 400
        mock_response.read.return_value = b"invalid_payload"

        with patch("http.client.HTTPSConnection") as mock_conn:
            mock_conn.return_value.getresponse.return_value = mock_response
            status = webhook_post_message(message, hook_url)
            assert status == 400  # noqa: PLR2004

    def test_webhook_url_parsing(self):
        """Test that webhook URL is correctly parsed."""
        message = {"blocks": []}
        hook_url = "https://hooks.slack.com/services/T123/B456/X789"

        mock_connection = Mock()
        mock_response = Mock()
        mock_response.status = 200
        mock_response.read.return_value = b"ok"
        mock_connection.getresponse.return_value = mock_response

        with patch("http.client.HTTPSConnection") as mock_conn:
            mock_conn.return_value = mock_connection
            webhook_post_message(message, hook_url)
            # Check that path is extracted correctly
            mock_connection.request.assert_called_once()
            call_args = mock_connection.request.call_args
            assert call_args[0][1] == "/services/T123/B456/X789"


class TestSlackAppPostMessage:
    """Test Slack app message posting."""

    def test_successful_slack_app_post(self):
        """Test successful Slack app message posting."""
        message = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Test"}}]}
        channel_id = "C123456"
        app_config = SlackAppConfig(bot_token="xoxb-test-token", default_channel_id=channel_id, configuration=[])

        mock_response = {"ok": True, "ts": "1234567890.123456"}

        with patch("slack_helpers.WebClient") as mock_client:
            mock_client.return_value.chat_postMessage.return_value = mock_response
            result = slack_app_post_message(message, channel_id, app_config)
            assert result["ok"] is True
            assert mock_client.return_value.chat_postMessage.called

    def test_slack_app_post_with_thread(self):
        """Test Slack app posting to a thread."""
        message = {"blocks": []}
        channel_id = "C123456"
        thread_ts = "1234567890.123456"
        app_config = SlackAppConfig(bot_token="xoxb-test-token", default_channel_id=channel_id, configuration=[])

        with patch("slack_helpers.WebClient") as mock_client:
            slack_app_post_message(message, channel_id, app_config, thread_ts=thread_ts)
            call_args = mock_client.return_value.chat_postMessage.call_args
            assert call_args[1]["thread_ts"] == thread_ts

    def test_slack_app_uses_correct_token(self):
        """Test that Slack app uses the correct bot token."""
        message = {"blocks": []}
        channel_id = "C123456"
        app_config = SlackAppConfig(bot_token="xoxb-secret-token", default_channel_id=channel_id, configuration=[])

        with patch("slack_helpers.WebClient") as mock_client:
            slack_app_post_message(message, channel_id, app_config)
            mock_client.assert_called_with(token="xoxb-secret-token")


class TestEventToSlackMessage:
    """Test CloudTrail event to Slack message formatting."""

    def test_basic_event_formatting(self):
        """Test basic event message formatting."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/admin",
                "accountId": "123456789012",
            },
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")

        assert "blocks" in message
        assert len(message["blocks"]) > 0
        # Check that event name is in the message
        blocks_str = json.dumps(message["blocks"])
        assert "CreateUser" in blocks_str
        assert "admin" in blocks_str

    def test_event_with_error_formatting(self):
        """Test formatting of events with errors."""
        event = {
            "eventName": "DeleteBucket",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "errorCode": "AccessDenied",
            "errorMessage": "User is not authorized",
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        blocks_str = json.dumps(message["blocks"])

        # Should include warning indicators
        assert ":warning:" in blocks_str
        assert "AccessDenied" in blocks_str
        assert "User is not authorized" in blocks_str

    def test_console_login_without_mfa_formatting(self):
        """Test special formatting for console login without MFA."""
        event = {
            "eventName": "ConsoleLogin",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        blocks_str = json.dumps(message["blocks"])

        # Should include MFA warning
        assert "Login without MFA" in blocks_str

    def test_console_login_with_mfa_formatting(self):
        """Test formatting for console login with MFA (no special warning)."""
        event = {
            "eventName": "ConsoleLogin",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "additionalEventData": {"MFAUsed": "Yes"},
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        blocks_str = json.dumps(message["blocks"])

        # Should NOT include MFA warning
        assert "Login without MFA" not in blocks_str

    def test_event_with_request_parameters(self):
        """Test formatting includes request parameters."""
        event = {
            "eventName": "PutBucketPolicy",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "requestParameters": {"bucketName": "my-bucket", "policy": "..."},
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        blocks_str = json.dumps(message["blocks"])

        assert "requestParameters" in blocks_str
        assert "my-bucket" in blocks_str

    def test_event_with_response_elements(self):
        """Test formatting includes response elements."""
        event = {
            "eventName": "CreateRole",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "responseElements": {"role": {"roleName": "TestRole"}},
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        blocks_str = json.dumps(message["blocks"])

        assert "responseElements" in blocks_str
        assert "TestRole" in blocks_str

    def test_event_source_file_included(self):
        """Test that source file is included in message."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        source_file = "AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/24/file.json.gz"
        message = event_to_slack_message(event, source_file, "123456789012")
        blocks_str = json.dumps(message["blocks"])

        assert source_file in blocks_str

    def test_event_id_included(self):
        """Test that event ID is included."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "unique-event-id-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        blocks_str = json.dumps(message["blocks"])

        assert "unique-event-id-123" in blocks_str

    def test_account_id_included(self):
        """Test that account ID is included."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_slack_message(event, "test.json.gz", "987654321098")
        blocks_str = json.dumps(message["blocks"])

        assert "987654321098" in blocks_str


class TestErrorNotificationMessages:
    """Test error notification message formatting."""

    def test_slack_error_notification_single_object(self):
        """Test error notification for single S3 object."""
        error = Exception("Test error message")
        s3_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "test.json.gz"},
                    }
                }
            ]
        }

        message = message_for_slack_error_notification(error, s3_event)

        assert "blocks" in message
        blocks_str = json.dumps(message["blocks"])
        assert "Failed to process event" in blocks_str
        assert "test.json.gz" in blocks_str
        assert "Test error message" in blocks_str

    def test_slack_error_notification_multiple_objects(self):
        """Test error notification for multiple S3 objects."""
        error = Exception("Batch error")
        s3_event = {
            "Records": [
                {"s3": {"object": {"key": "file1.json.gz"}}},
                {"s3": {"object": {"key": "file2.json.gz"}}},
            ]
        }

        message = message_for_slack_error_notification(error, s3_event)
        blocks_str = json.dumps(message["blocks"])

        assert "file1.json.gz" in blocks_str
        assert "file2.json.gz" in blocks_str

    def test_rule_evaluation_error_notification(self):
        """Test rule evaluation error notification."""
        error = Exception("Invalid rule syntax")
        rule = 'event["nonexistent"] == "value"'
        object_key = "AWSLogs/test.json.gz"

        message = message_for_rule_evaluation_error_notification(error, object_key, rule)

        assert "blocks" in message
        blocks_str = json.dumps(message["blocks"])
        assert "Failed to evaluate rule" in blocks_str
        assert "nonexistent" in blocks_str  # Part of the rule is in the message
        assert "Invalid rule syntax" in blocks_str
        assert object_key in blocks_str


class TestMessageStructure:
    """Test that messages have correct Slack block structure."""

    def test_message_has_blocks(self):
        """Test that messages have blocks array."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")

        assert "blocks" in message
        assert isinstance(message["blocks"], list)
        assert len(message["blocks"]) > 0

    def test_blocks_have_valid_types(self):
        """Test that blocks have valid Slack types."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")
        valid_types = ["section", "context", "divider", "header"]

        for block in message["blocks"]:
            assert "type" in block
            assert block["type"] in valid_types

    def test_message_has_divider(self):
        """Test that messages include divider for visual separation."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_slack_message(event, "test.json.gz", "123456789012")

        # Should have at least one divider
        dividers = [block for block in message["blocks"] if block["type"] == "divider"]
        assert len(dividers) > 0
