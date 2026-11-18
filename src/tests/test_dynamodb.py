"""Thread grouping for the Slack app: same principal + same action within the TTL share a thread."""

import time
from types import SimpleNamespace

import pytest

from dynamodb import get_thread_ts_from_dynamodb, hash_user_identity_and_event_name, put_event_to_dynamodb

# ruff: noqa: ANN201, ANN001, E501

TABLE = "threads"
IDENTITY = {
    "type": "IAMUser",
    "principalId": "AIDAEXAMPLE",
    "arn": "arn:aws:iam::111111111111:user/alice",
    "accountId": "111111111111",
}


def make_event(event_name="CreateUser", **identity_overrides: str):
    return {"eventName": event_name, "userIdentity": IDENTITY | identity_overrides}


@pytest.fixture
def cfg():
    return SimpleNamespace(dynamodb_table_name=TABLE, dynamodb_time_to_live=900)


def test_same_principal_and_action_hash_equal():
    assert hash_user_identity_and_event_name(make_event()) == hash_user_identity_and_event_name(make_event())


@pytest.mark.parametrize(
    "other",
    [make_event("DeleteUser"), make_event(principalId="AIDAOTHER", arn="arn:aws:iam::111111111111:user/bob")],
    ids=["different_action", "different_principal"],
)
def test_different_principal_or_action_hash_differs(other):
    assert hash_user_identity_and_event_name(make_event()) != hash_user_identity_and_event_name(other)


@pytest.mark.parametrize(
    ("user_identity", "hashed"),
    [
        (None, False),
        ({"type": "Unknown"}, False),
        ({"type": "IAMUser", "accountId": "111111111111"}, True),
    ],
    ids=["no_identity", "one_field", "two_fields"],
)
def test_hash_needs_at_least_two_identity_fields(user_identity, hashed):
    event = {"eventName": "CreateUser"}
    if user_identity is not None:
        event["userIdentity"] = user_identity
    assert (hash_user_identity_and_event_name(event) is not None) is hashed


def test_stored_thread_is_found_for_similar_event(cfg, fake_dynamodb):
    put_event_to_dynamodb(make_event(), "1700000000.000100", fake_dynamodb, cfg)
    assert get_thread_ts_from_dynamodb(cfg, make_event(), fake_dynamodb) == "1700000000.000100"
    assert get_thread_ts_from_dynamodb(cfg, make_event("DeleteUser"), fake_dynamodb) is None


@pytest.mark.parametrize("time_to_live", [60, 900, 86400])
def test_stored_item_expiry_uses_configured_ttl(cfg, fake_dynamodb, time_to_live):
    cfg.dynamodb_time_to_live = time_to_live
    before = int(time.time())
    put_event_to_dynamodb(make_event(), "1700000000.000100", fake_dynamodb, cfg)
    (item,) = fake_dynamodb.tables[TABLE].values()
    assert before + time_to_live <= int(item["ttl"]["N"]) <= int(time.time()) + time_to_live


# DynamoDB deletes expired items lazily, so the Lambda must ignore them itself.
def test_expired_item_is_ignored(cfg, fake_dynamodb):
    put_event_to_dynamodb(make_event(), "1700000000.000100", fake_dynamodb, cfg)
    ((key, item),) = fake_dynamodb.tables[TABLE].items()
    fake_dynamodb.tables[TABLE][key] = item | {"ttl": {"N": str(int(time.time()) - 1)}}
    assert get_thread_ts_from_dynamodb(cfg, make_event(), fake_dynamodb) is None


def test_event_without_identity_is_not_stored(cfg, fake_dynamodb):
    event = {"eventName": "CreateUser"}
    assert put_event_to_dynamodb(event, "1700000000.000100", fake_dynamodb, cfg) is None
    assert fake_dynamodb.tables == {}
    assert get_thread_ts_from_dynamodb(cfg, event, fake_dynamodb) is None
