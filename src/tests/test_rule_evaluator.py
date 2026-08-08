# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""Tests for the restricted rule evaluator that replaced ``eval()`` (CWE-94)."""

import pytest
from rule_evaluator import (
    _RULE_CACHE,
    MAX_AST_NODES,
    MAX_EXPRESSION_LENGTH,
    MAX_NESTING_DEPTH,
    RuleTooComplexError,
    UnsupportedRuleError,
    evaluate_rule,
)

# ruff: noqa: ANN201, ANN001, E501

FLAT_EVENT = {
    "eventName": "ConsoleLogin",
    "eventSource": "signin.amazonaws.com",
    "userIdentity.type": "IAMUser",
    "userIdentity.arn": "arn:aws:iam::111111111111:user/alice",
    "userIdentity.accountId": "111111111111",
    "additionalEventData.MFAUsed": "No",
    "errorCode": "AccessDenied",
    "responseElements.functionName": "fivexl-cloudtrail-to-slack",
    "requestParameters.instanceCount": 3,
}


# --- supported grammar: everything the documented rules rely on --------------


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        # subscript + equality
        ('event["eventName"] == "ConsoleLogin"', True),
        ('event["eventName"] == "AssumeRole"', False),
        # dict.get with a default
        ('event.get("additionalEventData.MFAUsed", "") != "Yes"', True),
        ('event.get("does.not.exist", "") != ""', False),
        # str.startswith / str.endswith, including the tuple form
        ('event.get("errorCode", "").startswith(("AccessDenied"))', True),
        ('event.get("errorCode", "").endswith(("UnauthorizedOperation"))', False),
        ('not event["eventName"].startswith(("Get", "List", "Describe", "Head"))', True),
        # membership
        ('"userIdentity.accountId" in event', True),
        ('"nope" in event', False),
        ('"assumed-role/AWSReservedSSO" not in event.get("userIdentity.arn", "")', True),
        ('event["eventName"] in ["ConsoleLogin", "AssumeRole"]', True),
        ('event["eventName"] in {"ConsoleLogin", "AssumeRole"}', True),
        ('event["eventName"] in ("Nope",)', False),
        # boolean composition and parentheses
        (
            'event["eventName"] == "ConsoleLogin" '
            'and event.get("additionalEventData.MFAUsed", "") != "Yes" '
            'and "assumed-role/AWSReservedSSO" not in event.get("userIdentity.arn", "")',
            True,
        ),
        ('event["eventName"] == "Nope" or event["eventSource"] == "signin.amazonaws.com"', True),
        (
            '(event.get("errorCode", "").startswith(("AccessDenied"))) '
            'and (event.get("userIdentity.accountId", "") != "ANONYMOUS_PRINCIPAL")',
            True,
        ),
        # allowed builtins, arithmetic, chained comparison, ternary
        ('len(event["userIdentity.accountId"]) == 12', True),
        ('1 < event["requestParameters.instanceCount"] <= 5', True),
        ('str(event["requestParameters.instanceCount"]) == "3"', True),
        ('event["requestParameters.instanceCount"] + 1 == 4', True),
        ('"a" if event["eventName"] == "ConsoleLogin" else "b"', "a"),
        ('event["userIdentity.type"].lower() == "iamuser"', True),
        ('event["userIdentity.arn"][:12] == "arn:aws:iam:"', True),
        ('event["userIdentity.accountId"][-4:] == "1111"', True),
        ('any([event["eventName"] == "ConsoleLogin", False])', True),
    ],
)
def test_supported_expressions(expression, expected):
    assert evaluate_rule(expression, FLAT_EVENT) == expected


def test_default_rules_still_evaluate():
    """Every shipped default rule must evaluate under the restricted grammar."""
    from rules import default_rules

    for rule in default_rules:
        assert evaluate_rule(rule, FLAT_EVENT) in (True, False)


def test_events_to_track_rule_shape():
    """The generated ``events_to_track`` rule from config.py must still work."""
    rule = '"eventName" in event and event["eventName"] in ["ConsoleLogin", "SendSSHPublicKey"]'
    assert evaluate_rule(rule, FLAT_EVENT) is True


# --- the vulnerability: code execution must no longer be reachable ----------


@pytest.mark.parametrize(
    "expression",
    [
        # The exact payload class called out by CWE-94 / Inspector.
        '__import__("os").system("id")',
        '__import__("subprocess").check_output(["id"])',
        # ``eval`` with empty globals still exposed these.
        'eval("1+1")',
        'exec("x=1")',
        'open("/etc/passwd").read()',
        "globals()",
        "locals()",
        'getattr(event, "keys")()',
        # Object-graph traversal to reach a subprocess primitive.
        "().__class__.__bases__[0].__subclasses__()",
        'event.__class__.__init__.__globals__["__builtins__"]',
        "event.__setitem__",
        # Attribute access that is not an allow-listed method call.
        "event.keys",
        "event.keys().mapping",
        'event["eventName"].encode',
        # A dangerous callable cannot be smuggled in as a keyword argument.
        "sorted(event, key=eval)",
        "sorted(event, key=__import__)",
        # An unbound method cannot be reached by smuggling a type into the
        # receiver position through a literal or a dict.get default.
        '[str][0].upper("a")',
        '{"s": str}["s"].upper("a")',
        '(str,)[0].join(",", ["a"])',
        'event.get("nope", str).upper("a")',
        'str.join(",", event.keys())',
        'event.get("nope", len)("abc")',
        '{"f": len}["f"]("abc")',
        # Non-allow-listed method names.
        '"{0.__class__}".format(event)',
        'event["eventName"].__str__()',
        # Statements / assignment / walrus are not expressions we accept.
        "[x for x in event]",
        "(x for x in event)",
        "lambda: 1",
        "{k: v for k, v in event.items()}",
        "10 ** 10 ** 10",
        'f"{event}"',
        'event["eventName"] if (y := 1) else "b"',
    ],
)
def test_dangerous_expressions_are_rejected(expression):
    with pytest.raises((UnsupportedRuleError, NameError, SyntaxError)):
        evaluate_rule(expression, FLAT_EVENT)


def test_no_module_can_be_reached_via_builtins():
    """Sanity check that the builtins we do expose cannot import or open."""
    for name in ("__import__", "compile", "eval", "exec", "open", "getattr", "setattr", "vars", "dir", "type", "input", "breakpoint"):
        with pytest.raises((UnsupportedRuleError, NameError)):
            evaluate_rule(f'{name}("x")', FLAT_EVENT)


# --- error behaviour expected by main.py's rule-error reporting -------------


def test_unknown_name_raises_nameerror_like_eval():
    with pytest.raises(NameError) as excinfo:
        evaluate_rule("incorrect_rule", FLAT_EVENT)
    assert str(excinfo.value) == "name 'incorrect_rule' is not defined"


def test_malformed_rule_raises_syntaxerror():
    with pytest.raises(SyntaxError):
        evaluate_rule('event["eventName" == ', FLAT_EVENT)


@pytest.mark.parametrize(
    "expression",
    [
        '"a" < "b"',
        "1 == 1",
        "1 < 2 < 3",
        "3 < 2 < 1",
        "1 < 2 < 3 == 3 != 4",
        'event["eventName"] == "ConsoleLogin" and event["eventSource"]',
        'event["eventName"] == "Nope" or event["eventSource"]',
        '"" or event["eventName"]',
        '"x" and 0',
        'not event["eventName"]',
        'event["requestParameters.instanceCount"] % 2',
        'event["requestParameters.instanceCount"] - 4',
        'len(event["eventName"]) // 3',
        '"ConsoleLogin" in event["eventName"][0:12]',
    ],
)
def test_result_matches_builtin_eval_for_safe_expressions(expression):
    """The restricted evaluator must not change the value a rule produces."""
    expected = eval(expression, {"__builtins__": {"len": len}}, {"event": FLAT_EVENT})  # noqa: PGH001, S307
    actual = evaluate_rule(expression, FLAT_EVENT)
    assert actual == expected
    assert type(actual) is type(expected)


def test_missing_key_still_raises_keyerror():
    with pytest.raises(KeyError):
        evaluate_rule('event["not.there"] == "x"', FLAT_EVENT)


# --- resource guard rails ---------------------------------------------------


def test_over_long_rule_is_rejected():
    with pytest.raises(RuleTooComplexError):
        evaluate_rule('event["eventName"] == "' + "x" * MAX_EXPRESSION_LENGTH + '"', FLAT_EVENT)


def test_over_complex_rule_is_rejected():
    expression = " or ".join(['event["eventName"] == "x"'] * MAX_AST_NODES)
    with pytest.raises(RuleTooComplexError):
        evaluate_rule(expression, FLAT_EVENT)


def test_deeply_nested_rule_is_rejected_before_recursion_error():
    """A deep tree must fail as RuleTooComplexError, not RecursionError."""
    expression = "not " * (MAX_NESTING_DEPTH + 10) + "True"
    with pytest.raises(RuleTooComplexError):
        evaluate_rule(expression, FLAT_EVENT)


@pytest.mark.parametrize(
    "expression",
    [
        # Sequence repetition can allocate gigabytes from a tiny rule, and an
        # out-of-memory kill is not catchable per-rule the way an error is.
        '"a" * 300000000',
        "[0] * 100000000000",
        '"a".join(["b"] * 2000000000)',
        "10 ** 10 ** 10",
    ],
)
def test_resource_exhaustion_operators_are_rejected(expression):
    with pytest.raises(UnsupportedRuleError):
        evaluate_rule(expression, FLAT_EVENT)


def test_generated_events_to_track_rule_is_not_length_limited():
    """config.py folds the whole events_to_track list into one expression."""
    import json

    previous_limit = 4096  # the limit before it was raised for this exact case
    events = [f"SomeLongishApiCallName{index}" for index in range(200)]
    rule = f'"eventName" in event and event["eventName"] in {json.dumps(events)}'
    assert len(rule) > previous_limit
    assert evaluate_rule(rule, FLAT_EVENT) is False


def test_a_failing_rule_is_only_parsed_once():
    """A rule that fails validation must not be re-parsed for every event."""
    expression = f"[x for x in event]  # {id(object())}"
    for _ in range(3):
        with pytest.raises(UnsupportedRuleError):
            evaluate_rule(expression, FLAT_EVENT)
    assert isinstance(_RULE_CACHE[expression], UnsupportedRuleError)
