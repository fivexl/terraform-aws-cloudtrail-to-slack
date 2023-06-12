import boto3


def pytest_sessionstart(session):  # noqa: ANN201, ARG001, ANN001
    boto3.setup_default_session(region_name="us-east-1")
