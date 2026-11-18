import pytest

from config import Config


# Terraform passes booleans to the Lambda as the strings "true" and "false".
@pytest.mark.parametrize(("value", "expected"), [("true", True), ("false", False), ("", False)])
def test_rule_evaluation_errors_to_slack(monkeypatch, value, expected):  # noqa: ANN001, ANN201
    monkeypatch.setenv("RULE_EVALUATION_ERRORS_TO_SLACK", value)
    assert Config().rule_evaluation_errors_to_slack is expected
