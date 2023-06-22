import boto3
import os


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
