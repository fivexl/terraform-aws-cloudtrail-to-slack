"""
Comprehensive tests for DynamoDB operations.
Tests event hashing, thread tracking, TTL handling, and error conditions.
"""

import time
from unittest.mock import Mock
from dynamodb import (
    hash_user_identity_and_event_name,
    put_event_to_dynamodb,
    check_dynamodb_for_similar_events,
    get_thread_ts_from_dynamodb,
)
from config import Config

# ruff: noqa: ANN201, ANN001, E501


class TestHashUserIdentityAndEventName:
    """Test event hashing for DynamoDB keys."""

    def test_hash_with_complete_user_identity(self):
        """Test hashing with all user identity fields present."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        hash_value = hash_user_identity_and_event_name(event)
        assert hash_value is not None
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 produces 64 hex characters  # noqa: PLR2004

    def test_hash_is_consistent(self):
        """Test that same event produces same hash."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        hash1 = hash_user_identity_and_event_name(event)
        hash2 = hash_user_identity_and_event_name(event)
        assert hash1 == hash2

    def test_hash_differs_for_different_events(self):
        """Test that different events produce different hashes."""
        event1 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        event2 = {
            "eventName": "DeleteUser",  # Different event name
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        hash1 = hash_user_identity_and_event_name(event1)
        hash2 = hash_user_identity_and_event_name(event2)
        assert hash1 != hash2

    def test_hash_differs_for_different_users(self):
        """Test that different users produce different hashes."""
        event1 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI111111111",
                "arn": "arn:aws:iam::123456789012:user/user1",
                "accountId": "123456789012",
            },
        }

        event2 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI222222222",  # Different principal
                "arn": "arn:aws:iam::123456789012:user/user2",
                "accountId": "123456789012",
            },
        }

        hash1 = hash_user_identity_and_event_name(event1)
        hash2 = hash_user_identity_and_event_name(event2)
        assert hash1 != hash2

    def test_hash_with_missing_user_identity(self):
        """Test that events without userIdentity return None."""
        event = {"eventName": "SomeEvent"}

        hash_value = hash_user_identity_and_event_name(event)
        assert hash_value is None

    def test_hash_with_too_many_na_values(self):
        """Test that insufficient identity data returns None."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                # Only one field, rest will be N/A - should return None
                "type": "Unknown"
            },
        }

        hash_value = hash_user_identity_and_event_name(event)
        assert hash_value is None

    def test_hash_with_minimum_required_fields(self):
        """Test hashing with minimum required fields (2 non-N/A)."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "accountId": "123456789012",
                # principalId and arn will be N/A, but we have 2 fields
            },
        }

        hash_value = hash_user_identity_and_event_name(event)
        # Should succeed with 2 valid fields
        assert hash_value is not None

    def test_hash_with_assumed_role(self):
        """Test hashing for assumed role events."""
        event = {
            "eventName": "AssumeRole",
            "userIdentity": {
                "type": "AssumedRole",
                "principalId": "AROA123456789:session",
                "arn": "arn:aws:sts::123456789012:assumed-role/MyRole/session",
                "accountId": "123456789012",
            },
        }

        hash_value = hash_user_identity_and_event_name(event)
        assert hash_value is not None

    def test_hash_with_root_user(self):
        """Test hashing for root user events."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "Root",
                "principalId": "123456789012",
                "arn": "arn:aws:iam::123456789012:root",
                "accountId": "123456789012",
            },
        }

        hash_value = hash_user_identity_and_event_name(event)
        assert hash_value is not None


class TestPutEventToDynamoDB:
    """Test storing events in DynamoDB."""

    def test_successful_put_event(self):
        """Test successfully storing an event."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        thread_ts = "1234567890.123456"
        mock_dynamodb = Mock()
        mock_dynamodb.put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"
        cfg.dynamodb_time_to_live = 900

        result = put_event_to_dynamodb(event, thread_ts, mock_dynamodb, cfg)

        assert result is not None
        assert mock_dynamodb.put_item.called
        call_args = mock_dynamodb.put_item.call_args[1]
        assert call_args["TableName"] == "test-table"
        assert "Item" in call_args
        assert call_args["Item"]["thread_ts"]["S"] == thread_ts

    def test_put_event_with_ttl(self):
        """Test that TTL is correctly calculated and stored."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        thread_ts = "1234567890.123456"
        mock_dynamodb = Mock()

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"
        cfg.dynamodb_time_to_live = 900  # 15 minutes

        current_time = time.time()
        put_event_to_dynamodb(event, thread_ts, mock_dynamodb, cfg)

        call_args = mock_dynamodb.put_item.call_args[1]
        ttl_value = int(call_args["Item"]["ttl"]["N"])

        # TTL should be current time + 900 seconds (within a small margin)
        assert ttl_value >= current_time + 890
        assert ttl_value <= current_time + 910

    def test_put_event_without_valid_hash_returns_none(self):
        """Test that events without valid hash are not stored."""
        event = {
            "eventName": "CreateUser",
            # Missing userIdentity
        }

        thread_ts = "1234567890.123456"
        mock_dynamodb = Mock()

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"
        cfg.dynamodb_time_to_live = 900

        result = put_event_to_dynamodb(event, thread_ts, mock_dynamodb, cfg)

        assert result is None
        assert not mock_dynamodb.put_item.called

    def test_put_event_stores_correct_hash(self):
        """Test that the correct hash is stored as the key."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        expected_hash = hash_user_identity_and_event_name(event)
        thread_ts = "1234567890.123456"
        mock_dynamodb = Mock()

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"
        cfg.dynamodb_time_to_live = 900

        put_event_to_dynamodb(event, thread_ts, mock_dynamodb, cfg)

        call_args = mock_dynamodb.put_item.call_args[1]
        stored_hash = call_args["Item"]["principal_structure_and_action_hash"]["S"]

        assert stored_hash == expected_hash


class TestCheckDynamoDBForSimilarEvents:
    """Test checking for similar events in DynamoDB."""

    def test_find_similar_event_not_expired(self):
        """Test finding a similar event that hasn't expired."""
        hash_value = "test-hash-value"
        future_ttl = int(time.time()) + 600  # Expires in 10 minutes

        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "principal_structure_and_action_hash": {"S": hash_value},
                "thread_ts": {"S": "1234567890.123456"},
                "ttl": {"N": str(future_ttl)},
            }
        }

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        result = check_dynamodb_for_similar_events(hash_value, mock_dynamodb, cfg)

        assert result is not None
        assert result["thread_ts"]["S"] == "1234567890.123456"

    def test_find_expired_event_returns_none(self):
        """Test that expired events are treated as not found."""
        hash_value = "test-hash-value"
        past_ttl = int(time.time()) - 600  # Expired 10 minutes ago

        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "principal_structure_and_action_hash": {"S": hash_value},
                "thread_ts": {"S": "1234567890.123456"},
                "ttl": {"N": str(past_ttl)},
            }
        }

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        result = check_dynamodb_for_similar_events(hash_value, mock_dynamodb, cfg)

        assert result is None

    def test_event_not_found_returns_none(self):
        """Test that missing events return None."""
        hash_value = "nonexistent-hash"

        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {}  # No Item in response

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        result = check_dynamodb_for_similar_events(hash_value, mock_dynamodb, cfg)

        assert result is None

    def test_check_uses_correct_table_name(self):
        """Test that correct table name is used in query."""
        hash_value = "test-hash"
        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {}

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "my-custom-table"

        check_dynamodb_for_similar_events(hash_value, mock_dynamodb, cfg)

        call_args = mock_dynamodb.get_item.call_args[1]
        assert call_args["TableName"] == "my-custom-table"

    def test_check_uses_correct_key_structure(self):
        """Test that correct key structure is used."""
        hash_value = "test-hash-value"
        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {}

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        check_dynamodb_for_similar_events(hash_value, mock_dynamodb, cfg)

        call_args = mock_dynamodb.get_item.call_args[1]
        assert call_args["Key"] == {"principal_structure_and_action_hash": {"S": hash_value}}


class TestGetThreadTsFromDynamoDB:
    """Test retrieving thread_ts for event grouping."""

    def test_get_thread_ts_for_similar_event(self):
        """Test retrieving thread_ts for a similar event."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        expected_thread_ts = "1234567890.123456"
        future_ttl = int(time.time()) + 600

        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "thread_ts": {"S": expected_thread_ts},
                "ttl": {"N": str(future_ttl)},
            }
        }

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        thread_ts = get_thread_ts_from_dynamodb(cfg, event, mock_dynamodb)

        assert thread_ts == expected_thread_ts

    def test_get_thread_ts_for_new_event(self):
        """Test that new events (no similar) return None."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {}  # No similar event

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        thread_ts = get_thread_ts_from_dynamodb(cfg, event, mock_dynamodb)

        assert thread_ts is None

    def test_get_thread_ts_for_expired_event(self):
        """Test that expired similar events return None."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        past_ttl = int(time.time()) - 600

        mock_dynamodb = Mock()
        mock_dynamodb.get_item.return_value = {
            "Item": {
                "thread_ts": {"S": "1234567890.123456"},
                "ttl": {"N": str(past_ttl)},
            }
        }

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        thread_ts = get_thread_ts_from_dynamodb(cfg, event, mock_dynamodb)

        assert thread_ts is None

    def test_get_thread_ts_without_hash_returns_none(self):
        """Test that events without valid hash return None."""
        event = {
            "eventName": "CreateUser",
            # Missing userIdentity
        }

        mock_dynamodb = Mock()
        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"

        thread_ts = get_thread_ts_from_dynamodb(cfg, event, mock_dynamodb)

        assert thread_ts is None
        assert not mock_dynamodb.get_item.called


class TestDynamoDBIntegration:
    """Test complete DynamoDB workflow."""

    def test_complete_thread_tracking_workflow(self):
        """Test complete workflow: store event, then retrieve thread_ts."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        original_thread_ts = "1234567890.123456"
        mock_dynamodb = Mock()

        cfg = Mock(spec=Config)
        cfg.dynamodb_table_name = "test-table"
        cfg.dynamodb_time_to_live = 900

        # Store the event
        put_event_to_dynamodb(event, original_thread_ts, mock_dynamodb, cfg)

        # Simulate that it was stored
        stored_hash = hash_user_identity_and_event_name(event)
        future_ttl = int(time.time()) + 900

        mock_dynamodb.get_item.return_value = {
            "Item": {
                "principal_structure_and_action_hash": {"S": stored_hash},
                "thread_ts": {"S": original_thread_ts},
                "ttl": {"N": str(future_ttl)},
            }
        }

        # Retrieve the thread_ts for a similar event
        retrieved_thread_ts = get_thread_ts_from_dynamodb(cfg, event, mock_dynamodb)

        assert retrieved_thread_ts == original_thread_ts

    def test_different_events_dont_share_threads(self):
        """Test that different events get different thread_ts values."""
        event1 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI111111111",
                "arn": "arn:aws:iam::123456789012:user/user1",
                "accountId": "123456789012",
            },
        }

        event2 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI222222222",  # Different user
                "arn": "arn:aws:iam::123456789012:user/user2",
                "accountId": "123456789012",
            },
        }

        hash1 = hash_user_identity_and_event_name(event1)
        hash2 = hash_user_identity_and_event_name(event2)

        # Hashes should be different
        assert hash1 != hash2

    def test_same_user_same_action_shares_thread(self):
        """Test that same user/action combinations share thread_ts."""
        event1 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        event2 = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789",
                "arn": "arn:aws:iam::123456789012:user/test",
                "accountId": "123456789012",
            },
        }

        hash1 = hash_user_identity_and_event_name(event1)
        hash2 = hash_user_identity_and_event_name(event2)

        # Hashes should be identical
        assert hash1 == hash2
