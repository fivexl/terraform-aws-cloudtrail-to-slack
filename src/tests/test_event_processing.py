"""
Comprehensive tests for event processing.
Tests lambda handler, S3 event handling, error handling, and CloudWatch metrics.
"""

import gzip
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from io import BytesIO

# ruff: noqa: ANN201, ANN001, E501


class TestLambdaHandler:
    """Test the main lambda_handler function."""

    def test_direct_s3_event_processing(self):
        """Test processing of direct S3 notification."""
        from main import lambda_handler

        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "eventSource": "aws:s3",
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "AWSLogs/123/CloudTrail/file.json.gz"},
                    },
                }
            ]
        }

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            mock_get_logs.return_value = None
            result = lambda_handler(s3_event, None)
            assert result == 200  # noqa: PLR2004
            assert mock_get_logs.called

    def test_sns_wrapped_s3_event_processing(self):
        """Test processing of SNS-wrapped S3 notification."""
        from main import lambda_handler

        sns_event = {
            "Records": [
                {
                    "EventSource": "aws:sns",
                    "Sns": {
                        "Message": json.dumps(
                            {
                                "Records": [
                                    {
                                        "eventName": "ObjectCreated:Put",
                                        "s3": {
                                            "bucket": {"name": "test-bucket"},
                                            "object": {"key": "AWSLogs/123/CloudTrail/file.json.gz"},
                                        },
                                    }
                                ]
                            }
                        )
                    },
                }
            ]
        }

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            mock_get_logs.return_value = None
            result = lambda_handler(sns_event, None)
            assert result == 200  # noqa: PLR2004

    def test_digest_files_are_skipped(self):
        """Test that CloudTrail digest files are not processed."""
        from main import lambda_handler

        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "AWSLogs/123/CloudTrail-Digest/2026/file.json.gz"},
                    },
                }
            ]
        }

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            result = lambda_handler(s3_event, None)
            assert result == 200  # noqa: PLR2004
            assert not mock_get_logs.called

    def test_object_removed_event_handling(self):
        """Test handling of S3 ObjectRemoved events."""
        from main import lambda_handler

        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectRemoved:Delete",
                    "userIdentity": {"accountId": "123456789012"},
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "AWSLogs/123/CloudTrail/file.json.gz"},
                    },
                }
            ]
        }

        with patch("main.post_message") as mock_post:
            result = lambda_handler(s3_event, None)
            assert result == 200  # noqa: PLR2004
            assert mock_post.called

    def test_lambda_handler_error_handling(self):
        """Test that lambda handler catches and reports errors."""
        from main import lambda_handler

        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "AWSLogs/file.json.gz"},
                    },
                }
            ]
        }

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            with patch("main.post_message") as mock_post:
                mock_get_logs.side_effect = Exception("Test error")
                result = lambda_handler(s3_event, None)
                # Should still return 200 and post error message
                assert result == 200  # noqa: PLR2004
                assert mock_post.called
                # Check that error message was posted
                call_args = mock_post.call_args
                assert "Failed to process event" in str(call_args)

    def test_multiple_s3_records_in_one_event(self):
        """Test processing multiple S3 records in a single event."""
        from main import lambda_handler

        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "AWSLogs/file1.json.gz"},
                    },
                },
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": "test-bucket"},
                        "object": {"key": "AWSLogs/file2.json.gz"},
                    },
                },
            ]
        }

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            mock_get_logs.return_value = None
            result = lambda_handler(s3_event, None)
            assert result == 200  # noqa: PLR2004
            assert mock_get_logs.call_count == 2  # noqa: PLR2004

    def test_invalid_sns_json_handling(self):
        """Test handling of invalid JSON in SNS message."""
        from main import lambda_handler

        sns_event = {
            "Records": [
                {
                    "EventSource": "aws:sns",
                    "Sns": {"Message": "invalid json {{{"},
                }
            ]
        }

        with patch("main.logger") as mock_logger:
            result = lambda_handler(sns_event, None)
            assert result == 200  # noqa: PLR2004
            # Should log error
            assert mock_logger.error.called


class TestGetCloudTrailLogRecords:
    """Test CloudTrail log file retrieval and parsing."""

    def test_successful_s3_object_retrieval(self):
        """Test successful retrieval and parsing of CloudTrail log."""
        from main import get_cloudtrail_log_records

        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/file.json.gz"},
            }
        }

        # Create gzipped test data
        test_data = {"Records": [{"eventName": "TestEvent"}]}
        compressed_data = BytesIO()
        with gzip.GzipFile(fileobj=compressed_data, mode="w") as gz:
            gz.write(json.dumps(test_data).encode("utf-8"))

        mock_response = {"Body": BytesIO(compressed_data.getvalue())}

        with patch("main.s3_client") as mock_s3:
            mock_s3.get_object.return_value = mock_response
            result = get_cloudtrail_log_records(record)

            assert result is not None
            assert result["key"] == "AWSLogs/file.json.gz"
            assert len(result["events"]) == 1
            assert result["events"][0]["eventName"] == "TestEvent"

    def test_s3_object_retrieval_with_url_encoded_key(self):
        """Test retrieval of objects with URL-encoded keys."""
        from main import get_cloudtrail_log_records

        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/2026/01/24/file%20with%20spaces.json.gz"},
            }
        }

        test_data = {"Records": [{"eventName": "TestEvent"}]}
        compressed_data = BytesIO()
        with gzip.GzipFile(fileobj=compressed_data, mode="w") as gz:
            gz.write(json.dumps(test_data).encode("utf-8"))

        mock_response = {"Body": BytesIO(compressed_data.getvalue())}

        with patch("main.s3_client") as mock_s3:
            mock_s3.get_object.return_value = mock_response
            get_cloudtrail_log_records(record)
            # Should decode URL encoding
            mock_s3.get_object.assert_called_with(Bucket="test-bucket", Key="AWSLogs/2026/01/24/file with spaces.json.gz")

    def test_missing_s3_section_raises_error(self):
        """Test that missing s3 section raises AssertionError."""
        from main import get_cloudtrail_log_records

        invalid_record = {"eventName": "ObjectCreated:Put"}

        with pytest.raises(AssertionError) as exc_info:
            get_cloudtrail_log_records(invalid_record)
        assert "does not contain s3 section" in str(exc_info.value)

    def test_s3_get_object_error_is_raised(self):
        """Test that S3 errors are properly raised."""
        from main import get_cloudtrail_log_records

        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/file.json.gz"},
            }
        }

        with patch("main.s3_client") as mock_s3:
            mock_s3.get_object.side_effect = Exception("S3 Error")
            with pytest.raises(Exception) as exc_info:
                get_cloudtrail_log_records(record)
            assert "S3 Error" in str(exc_info.value)


class TestHandleEvent:
    """Test individual CloudTrail event handling."""

    def test_matching_event_posts_to_slack(self):
        """Test that matching events are posted to Slack."""
        from main import handle_event

        event = {
            "eventName": "ConsoleLogin",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "test-123",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {
                "type": "IAMUser",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        rules = ['event["eventName"] == "ConsoleLogin"']

        with patch("main.post_message") as mock_post:
            with patch("main.send_message_to_sns"):
                # Create a simple object that can be JSON serialized
                mock_cfg = MagicMock()
                mock_cfg.rule_evaluation_errors_to_slack = False
                mock_cfg.push_access_denied_cloudwatch_metrics = False
                mock_cfg.__dict__ = {
                    "rule_evaluation_errors_to_slack": False,
                    "push_access_denied_cloudwatch_metrics": False,
                }
                with patch("main.cfg", mock_cfg):
                    handle_event(event, "test.json.gz", rules, [])
                    assert mock_post.called

    def test_non_matching_event_does_not_post(self):
        """Test that non-matching events are not posted."""
        from main import handle_event

        event = {
            "eventName": "DescribeInstances",
            "userIdentity": {"accountId": "123456789012"},
        }

        rules = ['event["eventName"] == "ConsoleLogin"']

        with patch("main.post_message") as mock_post:
            mock_cfg = MagicMock()
            mock_cfg.rule_evaluation_errors_to_slack = False
            mock_cfg.push_access_denied_cloudwatch_metrics = False
            mock_cfg.__dict__ = {
                "rule_evaluation_errors_to_slack": False,
                "push_access_denied_cloudwatch_metrics": False,
            }
            with patch("main.cfg", mock_cfg):
                handle_event(event, "test.json.gz", rules, [])
                assert not mock_post.called

    def test_ignore_rule_prevents_posting(self):
        """Test that ignore rules prevent posting even when rule matches."""
        from main import handle_event

        event = {
            "eventName": "ConsoleLogin",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "test-123",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        rules = ['event["eventName"] == "ConsoleLogin"']
        ignore_rules = ['event["eventName"] == "ConsoleLogin"']

        with patch("main.post_message") as mock_post:
            mock_cfg = MagicMock()
            mock_cfg.rule_evaluation_errors_to_slack = False
            mock_cfg.push_access_denied_cloudwatch_metrics = False
            mock_cfg.__dict__ = {
                "rule_evaluation_errors_to_slack": False,
                "push_access_denied_cloudwatch_metrics": False,
            }
            with patch("main.cfg", mock_cfg):
                handle_event(event, "test.json.gz", rules, ignore_rules)
                assert not mock_post.called

    def test_rule_evaluation_error_posts_to_slack_when_enabled(self):
        """Test that rule evaluation errors are posted when enabled."""
        from main import handle_event

        event = {"eventName": "ConsoleLogin", "userIdentity": {"accountId": "123"}}

        invalid_rules = ["invalid python syntax here"]

        with patch("main.post_message") as mock_post:
            mock_cfg = MagicMock()
            mock_cfg.rule_evaluation_errors_to_slack = True
            mock_cfg.push_access_denied_cloudwatch_metrics = False
            mock_cfg.__dict__ = {
                "rule_evaluation_errors_to_slack": True,
                "push_access_denied_cloudwatch_metrics": False,
            }
            with patch("main.cfg", mock_cfg):
                handle_event(event, "test.json.gz", invalid_rules, [])
                # Should post error message
                assert mock_post.called
                call_args = mock_post.call_args
                assert "rule" in str(call_args).lower()

    def test_access_denied_cloudwatch_metric_pushed(self):
        """Test that AccessDenied events push CloudWatch metrics when enabled."""
        from main import handle_event

        event = {
            "eventName": "GetObject",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "test-123",
            "errorCode": "AccessDenied",
            "userIdentity": {"accountId": "123456789012"},
        }

        rules = ['event.get("errorCode", "") == "AccessDenied"']

        with patch("main.push_total_access_denied_events_cloudwatch_metric") as mock_metric:
            with patch("main.post_message"):
                with patch("main.send_message_to_sns"):
                    mock_cfg = MagicMock()
                    mock_cfg.rule_evaluation_errors_to_slack = False
                    mock_cfg.push_access_denied_cloudwatch_metrics = True
                    mock_cfg.__dict__ = {
                        "rule_evaluation_errors_to_slack": False,
                        "push_access_denied_cloudwatch_metrics": True,
                    }
                    with patch("main.cfg", mock_cfg):
                        handle_event(event, "test.json.gz", rules, [])
                        assert mock_metric.called

    def test_ignored_access_denied_metric_pushed(self):
        """Test that ignored AccessDenied events push separate metric."""
        from main import handle_event

        event = {
            "eventName": "GetObject",
            "errorCode": "AccessDenied",
            "userIdentity": {"accountId": "123456789012"},
        }

        rules = ['event.get("errorCode", "") == "AccessDenied"']
        ignore_rules = ['event.get("errorCode", "") == "AccessDenied"']

        with patch("main.push_total_access_denied_events_cloudwatch_metric") as mock_total:
            with patch("main.push_total_ignored_access_denied_events_cloudwatch_metric") as mock_ignored:
                mock_cfg = MagicMock()
                mock_cfg.rule_evaluation_errors_to_slack = False
                mock_cfg.push_access_denied_cloudwatch_metrics = True
                mock_cfg.__dict__ = {
                    "rule_evaluation_errors_to_slack": False,
                    "push_access_denied_cloudwatch_metrics": True,
                }
                with patch("main.cfg", mock_cfg):
                    handle_event(event, "test.json.gz", rules, ignore_rules)
                    assert mock_total.called
                    assert mock_ignored.called

    def test_sns_message_sent_when_configured(self):
        """Test that SNS messages are sent when configured."""
        from main import handle_event

        event = {
            "eventName": "ConsoleLogin",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "test-123",
            "userIdentity": {"accountId": "123456789012"},
        }

        rules = ['event["eventName"] == "ConsoleLogin"']

        with patch("main.send_message_to_sns") as mock_sns:
            with patch("main.post_message"):
                mock_cfg = MagicMock()
                mock_cfg.rule_evaluation_errors_to_slack = False
                mock_cfg.push_access_denied_cloudwatch_metrics = False
                mock_cfg.__dict__ = {
                    "rule_evaluation_errors_to_slack": False,
                    "push_access_denied_cloudwatch_metrics": False,
                }
                with patch("main.cfg", mock_cfg):
                    handle_event(event, "test.json.gz", rules, [])
                    assert mock_sns.called


class TestCloudWatchMetrics:
    """Test CloudWatch metrics functionality."""

    def test_push_total_access_denied_metric(self):
        """Test pushing TotalAccessDeniedEvents metric."""
        from main import push_total_access_denied_events_cloudwatch_metric

        with patch("main.cloudwatch_client") as mock_cw:
            push_total_access_denied_events_cloudwatch_metric()
            assert mock_cw.put_metric_data.called
            call_args = mock_cw.put_metric_data.call_args
            assert call_args[1]["Namespace"] == "CloudTrailToSlack/AccessDeniedEvents"
            metric_data = call_args[1]["MetricData"][0]
            assert metric_data["MetricName"] == "TotalAccessDeniedEvents"
            assert metric_data["Value"] == 1

    def test_push_total_ignored_access_denied_metric(self):
        """Test pushing TotalIgnoredAccessDeniedEvents metric."""
        from main import push_total_ignored_access_denied_events_cloudwatch_metric

        with patch("main.cloudwatch_client") as mock_cw:
            push_total_ignored_access_denied_events_cloudwatch_metric()
            assert mock_cw.put_metric_data.called
            call_args = mock_cw.put_metric_data.call_args
            metric_data = call_args[1]["MetricData"][0]
            assert metric_data["MetricName"] == "TotalIgnoredAccessDeniedEvents"

    def test_cloudwatch_metric_error_handling(self):
        """Test that CloudWatch metric errors are caught."""
        from main import push_total_access_denied_events_cloudwatch_metric

        with patch("main.cloudwatch_client") as mock_cw:
            with patch("main.logger") as mock_logger:
                mock_cw.put_metric_data.side_effect = Exception("CloudWatch error")
                # Should not raise, just log
                push_total_access_denied_events_cloudwatch_metric()
                assert mock_logger.exception.called


class TestHandleCreatedObjectRecord:
    """Test handling of ObjectCreated records."""

    def test_handle_created_object_with_events(self):
        """Test processing CloudTrail events from created object."""
        from main import handle_created_object_record, Config

        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/file.json.gz"},
            }
        }

        cloudtrail_events = [
            {
                "eventName": "ConsoleLogin",
                "eventTime": "2026-01-24T12:00:00Z",
                "eventID": "test-123",
                "userIdentity": {"accountId": "123456789012"},
            }
        ]

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            with patch("main.handle_event") as mock_handle:
                mock_get_logs.return_value = {
                    "key": "AWSLogs/file.json.gz",
                    "events": cloudtrail_events,
                }
                cfg = Mock(spec=Config)
                cfg.rules = []
                cfg.ignore_rules = []

                handle_created_object_record(record, cfg)

                assert mock_handle.called
                # Check that handle_event was called with the event
                call_args = mock_handle.call_args
                assert call_args[1]["event"]["eventName"] == "ConsoleLogin"

    def test_handle_created_object_with_no_events(self):
        """Test handling when CloudTrail log contains no events."""
        from main import handle_created_object_record, Config

        record = {
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/file.json.gz"},
            }
        }

        with patch("main.get_cloudtrail_log_records") as mock_get_logs:
            with patch("main.handle_event") as mock_handle:
                mock_get_logs.return_value = None

                cfg = Mock(spec=Config)
                handle_created_object_record(record, cfg)

                # handle_event should not be called
                assert not mock_handle.called


class TestHandleRemovedObjectRecord:
    """Test handling of ObjectRemoved records."""

    def test_handle_removed_object_posts_message(self):
        """Test that removed object events post to Slack."""
        from main import handle_removed_object_record

        record = {
            "eventName": "ObjectRemoved:Delete",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "test-123",
            "userIdentity": {"accountId": "123456789012"},
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/file.json.gz"},
            },
        }

        with patch("main.post_message") as mock_post:
            handle_removed_object_record(record)
            assert mock_post.called
            # Check account_id is passed
            call_args = mock_post.call_args
            assert call_args[1]["account_id"] == "123456789012"

    def test_handle_removed_object_with_no_account_id(self):
        """Test handling removed object with no account ID."""
        from main import handle_removed_object_record

        record = {
            "eventName": "ObjectRemoved:Delete",
            "eventTime": "2026-01-24T12:00:00Z",
            "eventID": "test-123",
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "AWSLogs/file.json.gz"},
            },
        }

        with patch("main.post_message") as mock_post:
            handle_removed_object_record(record)
            assert mock_post.called
            call_args = mock_post.call_args
            assert call_args[1]["account_id"] == ""
