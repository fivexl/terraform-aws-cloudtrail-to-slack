import boto3
import os

import pytest


def pytest_sessionstart(session):  # noqa: ANN201, ARG001, ANN001
    mock_env = {
        "HOOK_URL": "x",
        "RULES_SEPARATOR": "x",
        "RULES": "x",
        "IGNORE_RULES": "x",
        "USE_DEFAULT_RULES": "x",
        "EVENTS_TO_TRACK": "x",
        "CONFIGURATION": "[{}]",
        "LOG_LEVEL": "DEBUG",
        "RULE_EVALUATION_ERRORS_TO_SLACK": "x",
    }
    os.environ |= mock_env
    boto3.setup_default_session(region_name="us-east-1")


class FakeDynamoDB:
    """In-memory stand-in for the two DynamoDB client calls the Lambda makes."""

    def __init__(self):  # noqa: ANN204
        self.tables: dict[str, dict[str, dict]] = {}

    def put_item(self, TableName, Item):  # noqa: ANN001, ANN201, N803
        self.tables.setdefault(TableName, {})[Item["principal_structure_and_action_hash"]["S"]] = Item
        return {}

    def get_item(self, TableName, Key):  # noqa: ANN001, ANN201, N803
        item = self.tables.get(TableName, {}).get(Key["principal_structure_and_action_hash"]["S"])
        return {"Item": item} if item else {}


class FakeSNS:
    def __init__(self):  # noqa: ANN204
        self.published: list[dict] = []

    def publish(self, **kwargs):  # noqa: ANN003, ANN201
        self.published.append(kwargs)
        return {"MessageId": str(len(self.published))}


@pytest.fixture
def fake_dynamodb():  # noqa: ANN201
    return FakeDynamoDB()


@pytest.fixture
def fake_sns():  # noqa: ANN201
    return FakeSNS()
