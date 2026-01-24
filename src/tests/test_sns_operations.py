"""
Comprehensive tests for SNS operations.
Tests SNS message formatting, account routing, and error handling.
"""

import json
from unittest.mock import Mock
from sns import send_message_to_sns, event_to_sns_message
from config import Config

# ruff: noqa: ANN201, ANN001, E501


class TestEventToSNSMessage:
    """Test CloudTrail event to SNS message formatting."""

    def test_basic_event_to_sns_message(self):
        """Test basic event formatting for SNS."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/admin",
                "accountId": "123456789012",
            },
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        assert "title" in message
        assert "CreateUser" in message["title"]
        assert "admin" in message["title"]
        assert message["account_id"] == "123456789012"
        assert message["event_id"] == "abc-123"

    def test_event_with_error_to_sns_message(self):
        """Test formatting event with error for SNS."""
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

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        assert "AccessDenied" in message["title"]
        assert message["error_message"] == "User is not authorized"

    def test_event_with_request_parameters(self):
        """Test that request parameters are included."""
        event = {
            "eventName": "PutBucketPolicy",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "requestParameters": {"bucketName": "my-bucket"},
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        assert message["request_parameters"] == {"bucketName": "my-bucket"}

    def test_event_with_response_elements(self):
        """Test that response elements are included."""
        event = {
            "eventName": "CreateRole",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "responseElements": {"role": {"roleName": "TestRole"}},
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        assert message["response_elements"] == {"role": {"roleName": "TestRole"}}

    def test_event_with_additional_details(self):
        """Test that additional event data is included."""
        event = {
            "eventName": "ConsoleLogin",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "additionalEventData": {"MFAUsed": "Yes"},
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        assert message["additional_details"] == {"MFAUsed": "Yes"}

    def test_event_without_account_id(self):
        """Test formatting when account_id is None."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {},
        }

        message = event_to_sns_message(event, "test.json.gz", None)

        assert message["account_id"] == "N/A"

    def test_source_file_included(self):
        """Test that source file is included in SNS message."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        source_file = "AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/24/file.json.gz"
        message = event_to_sns_message(event, source_file, "123456789012")

        assert message["source_file"] == source_file

    def test_event_time_is_string(self):
        """Test that event time is converted to string."""
        event = {
            "eventName": "TestEvent",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        assert isinstance(message["event_time"], str)
        assert "2026" in message["event_time"]


class TestSendMessageToSNS:
    """Test sending messages to SNS."""

    def test_send_message_when_sns_configured(self):
        """Test sending message when SNS is configured."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:test-topic"
        cfg.sns_configuration = []

        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="123456789012",
            cfg=cfg,
            sns_client=mock_sns,
        )

        assert mock_sns.publish.called
        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:test-topic"

    def test_no_send_when_sns_not_configured(self):
        """Test that nothing is sent when SNS is not configured."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        mock_sns = Mock()

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = None  # Not configured
        cfg.sns_configuration = []

        result = send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="123456789012",
            cfg=cfg,
            sns_client=mock_sns,
        )

        assert not mock_sns.publish.called
        assert result is None

    def test_account_specific_sns_topic_routing(self):
        """Test routing to account-specific SNS topic."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:default-topic"
        cfg.sns_configuration = [
            {
                "accounts": ["123456789012"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:account-specific-topic",
            }
        ]

        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="123456789012",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:account-specific-topic"

    def test_default_topic_when_account_not_in_config(self):
        """Test using default topic when account is not in configuration."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "999999999999"},
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:default-topic"
        cfg.sns_configuration = [
            {
                "accounts": ["123456789012"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:account-specific-topic",
            }
        ]

        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="999999999999",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:default-topic"

    def test_sns_message_is_valid_json(self):
        """Test that SNS message is valid JSON."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:test-topic"
        cfg.sns_configuration = []

        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="123456789012",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        message = call_args["Message"]

        # Should be valid JSON
        parsed_message = json.loads(message)
        assert "title" in parsed_message
        assert "event_id" in parsed_message

    def test_sns_with_no_account_id(self):
        """Test SNS sending when account_id is None."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {},
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:test-topic"
        cfg.sns_configuration = []

        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id=None,
            cfg=cfg,
            sns_client=mock_sns,
        )

        # Should use default topic
        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:test-topic"


class TestSNSMultipleAccountConfiguration:
    """Test SNS with multiple account configurations."""

    def test_multiple_accounts_in_same_configuration(self):
        """Test configuration with multiple accounts mapped to same topic."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "111111111111"},
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:default"
        cfg.sns_configuration = [
            {
                "accounts": ["111111111111", "222222222222"],  # Multiple accounts
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:prod-topic",
            }
        ]

        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="111111111111",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:prod-topic"

        # Test second account in same config
        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="222222222222",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:prod-topic"

    def test_multiple_separate_account_configurations(self):
        """Test multiple separate account configurations."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {"accountId": "111111111111"},
        }

        mock_sns = Mock()
        mock_sns.publish.return_value = {"MessageId": "test-message-id"}

        cfg = Mock(spec=Config)
        cfg.default_sns_topic_arn = "arn:aws:sns:us-east-1:123456789012:default"
        cfg.sns_configuration = [
            {
                "accounts": ["111111111111"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:prod-topic",
            },
            {
                "accounts": ["222222222222"],
                "sns_topic_arn": "arn:aws:sns:us-east-1:123456789012:dev-topic",
            },
        ]

        # Test first account
        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="111111111111",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:prod-topic"

        # Test second account
        send_message_to_sns(
            event=event,
            source_file="test.json.gz",
            account_id="222222222222",
            cfg=cfg,
            sns_client=mock_sns,
        )

        call_args = mock_sns.publish.call_args[1]
        assert call_args["TopicArn"] == "arn:aws:sns:us-east-1:123456789012:dev-topic"


class TestSNSMessageContent:
    """Test SNS message content and structure."""

    def test_sns_message_contains_all_required_fields(self):
        """Test that SNS message contains all required fields."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        required_fields = [
            "title",
            "error_message",
            "request_parameters",
            "response_elements",
            "additional_details",
            "account_id",
            "event_time",
            "event_id",
            "actor",
            "source_file",
        ]

        for field in required_fields:
            assert field in message

    def test_sns_message_serializable_to_json(self):
        """Test that SNS message can be serialized to JSON."""
        event = {
            "eventName": "CreateUser",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "abc-123",
            "requestParameters": {"userName": "test"},
            "userIdentity": {"accountId": "123456789012"},
        }

        message = event_to_sns_message(event, "test.json.gz", "123456789012")

        # Should not raise
        json_str = json.dumps(message)
        assert isinstance(json_str, str)

        # Should be parseable
        parsed = json.loads(json_str)
        assert parsed["event_id"] == "abc-123"
