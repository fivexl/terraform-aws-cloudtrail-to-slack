import pytest

from main import extract_s3_info

# ruff: noqa: ANN201, ANN001, E501


def test_extract_s3_info_from_s3_notification():
    """Test extracting S3 info from S3 notification format."""
    s3_notification_record = {
        "eventName": "ObjectCreated:Put",
        "s3": {
            "bucket": {"name": "test-cloudtrail-bucket"},
            "object": {"key": "AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/23/file.json.gz"}
        },
        "userIdentity": {"accountId": "123456789012"}
    }

    result = extract_s3_info(s3_notification_record)

    assert result["bucket"] == "test-cloudtrail-bucket"
    assert result["key"] == "AWSLogs/123456789012/CloudTrail/us-east-1/2026/01/23/file.json.gz"
    assert result["account_id"] == "123456789012"
    assert result["event_name"] == "ObjectCreated:Put"


def test_extract_s3_info_from_eventbridge_object_created():
    """Test extracting S3 info from EventBridge Object Created event."""
    eventbridge_event = {
        "version": "0",
        "id": "test-id",
        "detail-type": "Object Created",
        "source": "aws.s3",
        "account": "111222233344",
        "time": "2026-01-23T19:47:57Z",
        "region": "eu-central-1",
        "detail": {
            "bucket": {"name": "aws-cloudtrail-logs-test"},
            "object": {
                "key": "AWSLogs/o-test/111222233344/CloudTrail/eu-west-2/2026/01/23/file.json.gz",
                "size": 741,
                "etag": "test-etag"
            },
            "reason": "PutObject"
        }
    }

    result = extract_s3_info(eventbridge_event)

    assert result["bucket"] == "aws-cloudtrail-logs-test"
    assert result["key"] == "AWSLogs/o-test/111222233344/CloudTrail/eu-west-2/2026/01/23/file.json.gz"
    assert result["account_id"] == "111222233344"
    assert result["event_name"] == "ObjectCreated:Put"


def test_extract_s3_info_from_eventbridge_object_deleted():
    """Test extracting S3 info from EventBridge Object Deleted event (correct AWS detail-type)."""
    eventbridge_event = {
        "version": "0",
        "id": "test-id",
        "detail-type": "Object Deleted",
        "source": "aws.s3",
        "account": "111222233344",
        "time": "2026-01-23T19:47:57Z",
        "region": "eu-central-1",
        "detail": {
            "bucket": {"name": "aws-cloudtrail-logs-test"},
            "object": {
                "key": "AWSLogs/test/CloudTrail/us-east-1/2026/01/23/file.json.gz"
            },
            "reason": "DeleteObject"
        }
    }

    result = extract_s3_info(eventbridge_event)

    assert result["bucket"] == "aws-cloudtrail-logs-test"
    assert result["key"] == "AWSLogs/test/CloudTrail/us-east-1/2026/01/23/file.json.gz"
    assert result["account_id"] == "111222233344"
    assert result["event_name"] == "ObjectRemoved:Delete"


def test_extract_s3_info_handles_missing_account_in_s3_notification():
    """Test that missing account_id in S3 notification returns empty string."""
    s3_notification_record = {
        "eventName": "ObjectCreated:Put",
        "s3": {
            "bucket": {"name": "test-bucket"},
            "object": {"key": "test-key.json.gz"}
        }
    }

    result = extract_s3_info(s3_notification_record)

    assert result["account_id"] == ""


def test_extract_s3_info_handles_missing_account_in_eventbridge():
    """Test that missing account field in EventBridge event returns empty string."""
    eventbridge_event = {
        "version": "0",
        "detail-type": "Object Created",
        "source": "aws.s3",
        "region": "eu-central-1",
        "detail": {
            "bucket": {"name": "test-bucket"},
            "object": {"key": "test-key.json.gz"},
            "reason": "PutObject"
        }
    }

    result = extract_s3_info(eventbridge_event)

    assert result["account_id"] == ""


def test_extract_s3_info_maps_copy_event():
    """Test that CopyObject reason is mapped correctly."""
    eventbridge_event = {
        "detail-type": "Object Created",
        "detail": {
            "bucket": {"name": "test-bucket"},
            "object": {"key": "test-key.json.gz"},
            "reason": "CopyObject"
        },
        "account": "123456789012"
    }

    result = extract_s3_info(eventbridge_event)

    assert result["event_name"] == "ObjectCreated:Put"


def test_extract_s3_info_with_s3_notification_object_removed():
    """Test S3 notification format with ObjectRemoved event."""
    s3_notification_record = {
        "eventName": "ObjectRemoved:Delete",
        "s3": {
            "bucket": {"name": "test-bucket"},
            "object": {"key": "deleted-file.json.gz"}
        },
        "userIdentity": {"accountId": "987654321012"}
    }

    result = extract_s3_info(s3_notification_record)

    assert result["bucket"] == "test-bucket"
    assert result["key"] == "deleted-file.json.gz"
    assert result["account_id"] == "987654321012"
    assert result["event_name"] == "ObjectRemoved:Delete"


def test_extract_s3_info_unknown_eventbridge_detail_type():
    """Test that unknown EventBridge detail-type raises ValueError."""
    eventbridge_event = {
        "version": "0",
        "detail-type": "Object Tags Added",
        "source": "aws.s3",
        "account": "111222233344",
        "detail": {
            "bucket": {"name": "test-bucket"},
            "object": {"key": "test-key.json.gz"}
        }
    }

    with pytest.raises(ValueError, match="Unknown EventBridge detail-type"):
        extract_s3_info(eventbridge_event)


def test_extract_s3_info_object_deleted_detail_type():
    """Test EventBridge 'Object Deleted' detail-type."""
    eventbridge_event = {
        "version": "0",
        "detail-type": "Object Deleted",
        "source": "aws.s3",
        "account": "111222233344",
        "detail": {
            "bucket": {"name": "test-bucket"},
            "object": {"key": "deleted.json.gz"}
        }
    }

    result = extract_s3_info(eventbridge_event)

    assert result["event_name"] == "ObjectRemoved:Delete"
