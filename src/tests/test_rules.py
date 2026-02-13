"""
Comprehensive tests for rule evaluation system.
Tests all default rules, custom rules, ignore rules, and error handling.
"""

from main import should_message_be_processed, flatten_json
from rules import default_rules

# ruff: noqa: ANN201, ANN001, E501


class TestDefaultRules:
    """Test all default security rules."""

    def test_console_login_without_mfa_matches(self):
        """Test that console login without MFA is detected."""
        event = {
            "eventName": "ConsoleLogin",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/testuser"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True
        assert len(result.errors) == 0

    def test_console_login_with_mfa_does_not_match(self):
        """Test that console login with MFA is not flagged."""
        event = {
            "eventName": "ConsoleLogin",
            "additionalEventData": {"MFAUsed": "Yes"},
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/testuser"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is False

    def test_sso_login_without_mfa_does_not_match(self):
        """Test that SSO logins are excluded from MFA check."""
        event = {
            "eventName": "ConsoleLogin",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {"arn": "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_PowerUser/user@example.com"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is False

    def test_unauthorized_operation_matches(self):
        """Test that UnauthorizedOperation errors are detected."""
        event = {
            "eventName": "DescribeInstances",
            "errorCode": "Client.UnauthorizedOperation",
            "userIdentity": {"accountId": "123456789012"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_access_denied_with_account_matches(self):
        """Test that AccessDenied from authenticated users is detected."""
        event = {
            "eventName": "DescribeEventAggregates",
            "errorCode": "AccessDenied",
            "userIdentity": {"accountId": "123456789012"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_access_denied_anonymous_does_not_match(self):
        """Test that anonymous AccessDenied is ignored (to avoid noise)."""
        event = {
            "eventName": "GetObject",
            "errorCode": "AccessDenied",
            "userIdentity": {"accountId": "ANONYMOUS_PRINCIPAL"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is False

    def test_root_non_read_action_matches(self):
        """Test that non-read actions by root user are detected."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {"type": "Root"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_root_read_action_does_not_match(self):
        """Test that read actions by root are not flagged."""
        for action in ["GetUser", "ListUsers", "DescribeInstances", "HeadBucket"]:
            event = {
                "eventName": action,
                "userIdentity": {"type": "Root"},
            }
            result = should_message_be_processed(event, default_rules, [])
            assert result.should_be_processed is False, f"{action} should not be flagged"

    def test_cloudtrail_stop_logging_matches(self):
        """Test that CloudTrail StopLogging is detected."""
        event = {
            "eventName": "StopLogging",
            "eventSource": "cloudtrail.amazonaws.com",
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_cloudtrail_update_trail_matches(self):
        """Test that CloudTrail UpdateTrail is detected."""
        event = {
            "eventName": "UpdateTrail",
            "eventSource": "cloudtrail.amazonaws.com",
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_cloudtrail_delete_trail_matches(self):
        """Test that CloudTrail DeleteTrail is detected."""
        event = {
            "eventName": "DeleteTrail",
            "eventSource": "cloudtrail.amazonaws.com",
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_lambda_function_update_code_matches(self):
        """Test that updates to the cloudtrail-to-slack Lambda are detected."""
        event = {
            "eventName": "UpdateFunctionCode20150331v2",
            "eventSource": "lambda.amazonaws.com",
            "responseElements": {"functionName": "fivexl-cloudtrail-to-slack"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_lambda_function_update_configuration_matches(self):
        """Test that configuration changes to the Lambda are detected."""
        event = {
            "eventName": "UpdateFunctionConfiguration20150331v2",
            "eventSource": "lambda.amazonaws.com",
            "responseElements": {"functionName": "fivexl-cloudtrail-to-slack"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_other_lambda_function_update_does_not_match(self):
        """Test that updates to other Lambdas are not flagged."""
        event = {
            "eventName": "UpdateFunctionCode20150331v2",
            "eventSource": "lambda.amazonaws.com",
            "responseElements": {"functionName": "some-other-function"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is False


class TestCustomRules:
    """Test custom rule functionality."""

    def test_simple_custom_rule(self):
        """Test a simple custom rule."""
        event = {"eventName": "DeleteBucket", "eventSource": "s3.amazonaws.com"}
        custom_rules = ['event["eventName"] == "DeleteBucket"']
        result = should_message_be_processed(event, custom_rules, [])
        assert result.should_be_processed is True

    def test_multiple_custom_rules_first_matches(self):
        """Test that first matching custom rule triggers processing."""
        event = {"eventName": "CreateKey", "eventSource": "kms.amazonaws.com"}
        custom_rules = [
            'event["eventName"] == "CreateKey"',
            'event["eventName"] == "DeleteKey"',
        ]
        result = should_message_be_processed(event, custom_rules, [])
        assert result.should_be_processed is True

    def test_multiple_custom_rules_second_matches(self):
        """Test that second matching custom rule triggers processing."""
        event = {"eventName": "DeleteKey", "eventSource": "kms.amazonaws.com"}
        custom_rules = [
            'event["eventName"] == "CreateKey"',
            'event["eventName"] == "DeleteKey"',
        ]
        result = should_message_be_processed(event, custom_rules, [])
        assert result.should_be_processed is True

    def test_complex_custom_rule_with_nested_data(self):
        """Test custom rule accessing nested event data."""
        event = {
            "eventName": "PutBucketPolicy",
            "requestParameters": {"bucketName": "sensitive-data-bucket"},
        }
        custom_rules = ['event["eventName"] == "PutBucketPolicy" and "sensitive" in event.get("requestParameters.bucketName", "")']
        result = should_message_be_processed(event, custom_rules, [])
        assert result.should_be_processed is True

    def test_custom_rule_with_contains_operator(self):
        """Test custom rule using 'in' operator."""
        event = {
            "eventName": "AssumeRole",
            "requestParameters": {"roleArn": "arn:aws:iam::123:role/AdminRole"},
        }
        custom_rules = ['"Admin" in event.get("requestParameters.roleArn", "")']
        result = should_message_be_processed(event, custom_rules, [])
        assert result.should_be_processed is True


class TestIgnoreRules:
    """Test ignore rules functionality."""

    def test_ignore_rule_prevents_processing(self):
        """Test that ignore rules take precedence over matching rules."""
        event = {
            "eventName": "ConsoleLogin",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/testuser"},
        }
        ignore_rules = ['event["eventName"] == "ConsoleLogin"']
        result = should_message_be_processed(event, default_rules, ignore_rules)
        assert result.should_be_processed is False
        assert result.is_ignored is True

    def test_ignore_specific_user(self):
        """Test ignoring events from a specific user."""
        event = {
            "eventName": "CreateUser",
            "userIdentity": {
                "type": "Root",
                "arn": "arn:aws:iam::123456789012:root",
            },
        }
        ignore_rules = ['"123456789012:root" in event.get("userIdentity.arn", "")']
        result = should_message_be_processed(event, default_rules, ignore_rules)
        assert result.should_be_processed is False
        assert result.is_ignored is True

    def test_ignore_rule_with_multiple_conditions(self):
        """Test ignore rule with complex conditions."""
        event = {
            "eventName": "GetObject",
            "errorCode": "AccessDenied",
            "userIdentity": {"accountId": "123456789012"},
            "sourceIPAddress": "192.168.1.1",
        }
        ignore_rules = ['event.get("errorCode", "") == "AccessDenied" and event.get("sourceIPAddress", "").startswith("192.168")']
        result = should_message_be_processed(event, default_rules, ignore_rules)
        assert result.should_be_processed is False
        assert result.is_ignored is True

    def test_non_matching_ignore_rule_allows_processing(self):
        """Test that non-matching ignore rules don't prevent processing."""
        event = {
            "eventName": "ConsoleLogin",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/admin"},
        }
        ignore_rules = ['"testuser" in event.get("userIdentity.arn", "")']
        result = should_message_be_processed(event, default_rules, ignore_rules)
        assert result.should_be_processed is True
        assert result.is_ignored is False


class TestRuleErrorHandling:
    """Test error handling in rule evaluation."""

    def test_invalid_rule_syntax_is_caught(self):
        """Test that syntax errors in rules are caught and reported."""
        event = {"eventName": "ConsoleLogin"}
        invalid_rules = ["this is not valid python code"]
        result = should_message_be_processed(event, invalid_rules, [])
        assert len(result.errors) > 0
        assert result.errors[0]["rule"] == "this is not valid python code"

    def test_rule_with_undefined_variable(self):
        """Test that rules with undefined variables are caught."""
        event = {"eventName": "ConsoleLogin"}
        invalid_rules = ["undefined_variable == True"]
        result = should_message_be_processed(event, invalid_rules, [])
        assert len(result.errors) > 0
        assert "undefined_variable" in str(result.errors[0]["error"])

    def test_rule_accessing_missing_field_handles_gracefully(self):
        """Test that rules can safely access missing fields with .get()."""
        event = {"eventName": "CreateUser"}
        # This should not error because .get() returns empty string
        rules = ['event.get("nonexistent.field", "") == "value"']
        result = should_message_be_processed(event, rules, [])
        assert len(result.errors) == 0

    def test_multiple_invalid_rules_all_errors_collected(self):
        """Test that all rule errors are collected."""
        event = {"eventName": "ConsoleLogin"}
        invalid_rules = [
            "invalid syntax here",
            "undefined_var == True",
            "another bad rule!!!",
        ]
        result = should_message_be_processed(event, invalid_rules, [])
        assert len(result.errors) == 3  # noqa: PLR2004

    def test_partial_invalid_rules_still_processes_valid_match(self):
        """Test that valid rules still work even if some are invalid."""
        event = {
            "eventName": "ConsoleLogin",
            "additionalEventData": {"MFAUsed": "No"},
            "userIdentity": {"arn": "arn:aws:iam::123456789012:user/testuser"},
        }
        mixed_rules = [
            "invalid syntax",
            'event["eventName"] == "ConsoleLogin"',  # This one is valid
        ]
        result = should_message_be_processed(event, mixed_rules, [])
        assert result.should_be_processed is True
        assert len(result.errors) == 1


class TestEventFlattening:
    """Test JSON flattening for rule evaluation."""

    def test_flatten_simple_dict(self):
        """Test flattening simple dictionary."""
        event = {"eventName": "CreateUser", "eventSource": "iam.amazonaws.com"}
        flat = flatten_json(event)
        assert flat["eventName"] == "CreateUser"
        assert flat["eventSource"] == "iam.amazonaws.com"

    def test_flatten_nested_dict(self):
        """Test flattening nested dictionary."""
        event = {
            "eventName": "ConsoleLogin",
            "userIdentity": {"type": "IAMUser", "accountId": "123456789012"},
        }
        flat = flatten_json(event)
        assert flat["userIdentity.type"] == "IAMUser"
        assert flat["userIdentity.accountId"] == "123456789012"

    def test_flatten_deeply_nested_dict(self):
        """Test flattening deeply nested structures."""
        event = {"userIdentity": {"sessionContext": {"sessionIssuer": {"type": "Role", "arn": "arn:aws:iam::123:role/test"}}}}
        flat = flatten_json(event)
        assert flat["userIdentity.sessionContext.sessionIssuer.type"] == "Role"
        assert flat["userIdentity.sessionContext.sessionIssuer.arn"] == "arn:aws:iam::123:role/test"

    def test_flatten_list_in_dict(self):
        """Test flattening dictionaries containing lists."""
        event = {"tags": [{"key": "Environment", "value": "Production"}]}
        flat = flatten_json(event)
        assert flat["tags.0.key"] == "Environment"
        assert flat["tags.0.value"] == "Production"

    def test_flatten_multiple_list_items(self):
        """Test flattening lists with multiple items."""
        event = {
            "items": [
                {"name": "first", "id": 1},
                {"name": "second", "id": 2},
            ]
        }
        flat = flatten_json(event)
        assert flat["items.0.name"] == "first"
        assert flat["items.0.id"] == 1  # noqa: PLR2004
        assert flat["items.1.name"] == "second"
        assert flat["items.1.id"] == 2  # noqa: PLR2004

    def test_flatten_empty_dict(self):
        """Test flattening empty dictionary."""
        event = {}
        flat = flatten_json(event)
        assert flat == {}

    def test_flatten_with_none_values(self):
        """Test flattening with None values."""
        event = {"eventName": "Test", "errorCode": None}
        flat = flatten_json(event)
        assert flat["eventName"] == "Test"
        assert flat["errorCode"] is None


class TestRulesWithRealEvents:
    """Test rules with realistic CloudTrail events."""

    def test_real_console_login_without_mfa(self):
        """Test with realistic console login event."""
        event = {
            "eventVersion": "1.05",
            "userIdentity": {
                "type": "IAMUser",
                "principalId": "AIDAI123456789EXAMPLE",
                "arn": "arn:aws:iam::123456789012:user/alice",
                "accountId": "123456789012",
                "userName": "alice",
            },
            "eventTime": "2026-01-24T12:00:00Z",
            "eventSource": "signin.amazonaws.com",
            "eventName": "ConsoleLogin",
            "awsRegion": "us-east-1",
            "sourceIPAddress": "198.51.100.1",
            "userAgent": "Mozilla/5.0",
            "requestParameters": None,
            "responseElements": {"ConsoleLogin": "Success"},
            "additionalEventData": {
                "LoginTo": "https://console.aws.amazon.com/console/home",
                "MobileVersion": "No",
                "MFAUsed": "No",
            },
            "eventID": "abc-123-def-456",
            "eventType": "AwsConsoleSignIn",
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_real_access_denied_event(self):
        """Test with realistic AccessDenied event."""
        event = {
            "eventVersion": "1.08",
            "userIdentity": {
                "type": "AssumedRole",
                "principalId": "AROA123456789EXAMPLE:session",
                "arn": "arn:aws:sts::123456789012:assumed-role/Developer/session",
                "accountId": "123456789012",
            },
            "eventTime": "2026-01-24T12:00:00Z",
            "eventSource": "s3.amazonaws.com",
            "eventName": "GetObject",
            "awsRegion": "us-east-1",
            "errorCode": "AccessDenied",
            "errorMessage": "Access Denied",
            "requestParameters": {"bucketName": "secure-bucket", "key": "secret.txt"},
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True

    def test_real_cloudtrail_stop_logging_event(self):
        """Test with realistic StopLogging event."""
        event = {
            "eventVersion": "1.09",
            "userIdentity": {
                "type": "AssumedRole",
                "principalId": "AROA123456789EXAMPLE:session",
                "arn": "arn:aws:sts::123456789012:assumed-role/Admin/session",
                "accountId": "123456789012",
            },
            "eventTime": "2026-01-24T12:00:00Z",
            "eventSource": "cloudtrail.amazonaws.com",
            "eventName": "StopLogging",
            "awsRegion": "us-east-1",
            "requestParameters": {"name": "my-trail"},
            "responseElements": None,
        }
        result = should_message_be_processed(event, default_rules, [])
        assert result.should_be_processed is True
