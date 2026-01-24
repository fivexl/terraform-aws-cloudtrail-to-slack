import json
from unittest.mock import patch

# ruff: noqa: ANN201, ANN001, E501

# Test constants
HTTP_SUCCESS_STATUS = 200
EXPECTED_MULTIPLE_S3_RECORDS_COUNT = 3


def test_sns_wrapped_s3_notification():
    """
    Test SNS-wrapped S3 notifications (Lambda does NOT support raw_message_delivery).
    SNS always wraps messages for Lambda endpoints.
    """
    from main import lambda_handler

    # SNS event wrapping S3 notification (how Lambda actually receives it)
    sns_event = {
        "Records": [
            {
                "EventSource": "aws:sns",
                "EventVersion": "1.0",
                "EventSubscriptionArn": "arn:aws:sns:us-east-1:123456789012:cloudtrail-logs:abc-123",
                "Sns": {
                    "Type": "Notification",
                    "MessageId": "test-message-id",
                    "TopicArn": "arn:aws:sns:us-east-1:123456789012:cloudtrail-logs",
                    "Subject": "Amazon S3 Notification",
                    "Message": json.dumps(
                        {
                            "Records": [
                                {
                                    "eventVersion": "2.1",
                                    "eventSource": "aws:s3",
                                    "awsRegion": "us-east-1",
                                    "eventTime": "2026-01-24T00:00:00.000Z",
                                    "eventName": "ObjectCreated:Put",
                                    "userIdentity": {"principalId": "AWS:AIDAI123456789EXAMPLE"},
                                    "s3": {
                                        "s3SchemaVersion": "1.0",
                                        "bucket": {"name": "test-cloudtrail-bucket", "arn": "arn:aws:s3:::test-cloudtrail-bucket"},
                                        "object": {
                                            "key": "AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/24/test.json.gz",
                                            "size": 1024,
                                            "eTag": "d41d8cd98f00b204e9800998ecf8427e",
                                        },
                                    },
                                }
                            ]
                        }
                    ),
                    "Timestamp": "2026-01-24T00:00:00.000Z",
                },
            }
        ]
    }

    with patch("main.get_cloudtrail_log_records") as mock_get_logs:
        mock_get_logs.return_value = None

        result = lambda_handler(sns_event, None)

        # Verify SNS envelope was unwrapped and S3 record extracted
        assert mock_get_logs.called
        called_record = mock_get_logs.call_args[0][0]
        assert called_record["s3"]["bucket"]["name"] == "test-cloudtrail-bucket"
        assert "AWSLogs" in called_record["s3"]["object"]["key"]
        assert result == HTTP_SUCCESS_STATUS


def test_sns_with_multiple_s3_records():
    """Test SNS message containing multiple S3 records (batching maintained)."""
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
                                    "s3": {"bucket": {"name": "test-bucket"}, "object": {"key": "AWSLogs/file1.json.gz"}},
                                },
                                {
                                    "eventName": "ObjectCreated:Put",
                                    "s3": {"bucket": {"name": "test-bucket"}, "object": {"key": "AWSLogs/file2.json.gz"}},
                                },
                                {
                                    "eventName": "ObjectCreated:Put",
                                    "s3": {"bucket": {"name": "test-bucket"}, "object": {"key": "AWSLogs/file3.json.gz"}},
                                },
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

        # Should be called 3 times (once for each S3 record) in ONE Lambda invocation
        assert mock_get_logs.call_count == EXPECTED_MULTIPLE_S3_RECORDS_COUNT
        assert result == HTTP_SUCCESS_STATUS


def test_sns_with_invalid_json_message():
    """Test that invalid JSON in SNS message is handled gracefully."""
    from main import lambda_handler

    sns_event = {"Records": [{"EventSource": "aws:sns", "Sns": {"Message": "invalid json {"}}]}

    with patch("main.logger") as mock_logger:
        result = lambda_handler(sns_event, None)

        # Should log error but not crash
        assert mock_logger.error.called
        assert result == HTTP_SUCCESS_STATUS


def test_direct_s3_notification():
    """Test that direct S3 notifications still work (backward compatibility)."""
    from main import lambda_handler

    s3_event = {
        "Records": [
            {
                "eventName": "ObjectCreated:Put",
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "test-cloudtrail-bucket"},
                    "object": {"key": "AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/24/file.json.gz"},
                },
                "userIdentity": {"accountId": "123456789012"},
            }
        ]
    }

    with patch("main.get_cloudtrail_log_records") as mock_get_logs:
        mock_get_logs.return_value = None

        result = lambda_handler(s3_event, None)

        # Should process the S3 record directly
        assert mock_get_logs.called
        assert result == HTTP_SUCCESS_STATUS


def test_sns_digest_files_are_skipped():
    """Test that digest files are skipped even when coming through SNS."""
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
                                        "object": {"key": "AWSLogs/123/CloudTrail-Digest/file.json.gz"},
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
        result = lambda_handler(sns_event, None)

        # Should NOT call get_cloudtrail_log_records for digest files
        assert not mock_get_logs.called
        assert result == HTTP_SUCCESS_STATUS
