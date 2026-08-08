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
"""Restricted evaluator for CloudTrail-to-Slack rule expressions.

Rules are operator-supplied Python-like boolean expressions (see the "Rules"
section of the README). They used to be handed to the builtin ``eval()``, which
executes arbitrary Python: anything able to influence the ``RULES`` /
``IGNORE_RULES`` Lambda environment variables could run code inside the function
(CWE-94). ``eval`` also cannot be locked down by passing empty globals, because
CPython injects ``__builtins__`` automatically, leaving
``__import__("os").system(...)`` reachable.

This module instead parses each rule with :mod:`ast` and walks the tree with an
explicit allow-list of node types, operators, builtins, and method names. There
is no code path that imports a module, accesses an attribute that is not a
white-listed method call, reads a dunder, assigns, or calls anything other than
the small set of pure builtins below - so a rule cannot escape the expression
language regardless of what it contains.

The supported grammar covers everything the documented rules use:

* ``event["key"]`` and ``event.get("key", "default")``
* string helpers such as ``.startswith((...))`` / ``.endswith((...))``
* comparisons, ``in`` / ``not in``, ``and`` / ``or`` / ``not``, ternaries
* literals (str, numbers, bools, ``None``, tuple/list/set/dict) and slicing
* the pure builtins in :data:`_ALLOWED_BUILTINS`

Anything else raises :class:`UnsupportedRuleError`, which the caller reports the
same way it already reports a malformed rule.

Note that this is a sandbox for a *configuration* language, not a defence against
a hostile tenant: anything able to set ``RULES`` can already replace the function
code. Its purpose is to make the documented rule syntax evaluable without
handing the rule string to the interpreter.
"""

import ast
from typing import Any, Callable, Dict, Tuple

# Guard rails against pathological rule strings.
#
# The length limit only exists to stop an absurd input reaching the parser: it
# has to stay well clear of a legitimate rule, because config.py folds an entire
# ``events_to_track`` list into a single expression. ``MAX_NESTING_DEPTH`` is the
# limit that actually matters, since evaluation recurses once per nesting level.
MAX_EXPRESSION_LENGTH = 65536
MAX_AST_NODES = 2000
MAX_NESTING_DEPTH = 100

# Pure, side-effect-free builtins. Deliberately excludes anything that can
# import, open, execute, or reach the object graph (``getattr``, ``vars``,
# ``type``, ``eval``, ``__import__`` ...).
_ALLOWED_BUILTINS: Dict[str, Callable[..., Any]] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "float": float,
    "int": int,
    "len": len,
    "max": max,
    "min": min,
    "round": round,
    "sorted": sorted,
    "str": str,
    "sum": sum,
}

# Method names callable on a value produced by the expression itself (the
# flattened event dict, a literal, or the result of an allowed builtin). Because
# attribute *access* is never allowed on its own, and every name here is a
# method of the JSON-ish types a flattened CloudTrail event can hold, none of
# these can return a callable that widens the sandbox. ``format`` /
# ``format_map`` are excluded on purpose: format strings can traverse
# attributes (``"{0.__class__}".format(x)``).
_ALLOWED_METHODS = frozenset(
    {
        # dict
        "get",
        "items",
        "keys",
        "values",
        # str
        "casefold",
        "count",
        "endswith",
        "find",
        "index",
        "isalnum",
        "isalpha",
        "isdigit",
        "islower",
        "isnumeric",
        "isupper",
        "join",
        "lower",
        "lstrip",
        "removeprefix",
        "removesuffix",
        "replace",
        "rfind",
        "rsplit",
        "rstrip",
        "split",
        "splitlines",
        "startswith",
        "strip",
        "title",
        "upper",
    }
)

_ALLOWED_BOOL_OPS = (ast.And, ast.Or)
_ALLOWED_UNARY_OPS = (ast.Not, ast.UAdd, ast.USub)
# ``Pow`` and ``Mult`` are excluded because both make it trivial to exhaust the
# function's memory or timeout from a 20-character rule (``10 ** 10 ** 10``,
# ``"a" * 300000000``), and an out-of-memory kill takes down the whole
# invocation instead of being reported as a single rule error. The bitwise and
# shift operators are excluded because no rule has any use for them.
_ALLOWED_BIN_OPS = (ast.Add, ast.Sub, ast.Div, ast.FloorDiv, ast.Mod)
_ALLOWED_COMPARE_OPS = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)
_ALLOWED_CONSTANT_TYPES = (str, bytes, int, float, complex, bool, type(None))


class RuleEvaluationError(Exception):
    """Base class for problems found in a rule expression."""


class UnsupportedRuleError(RuleEvaluationError):
    """The rule uses syntax the restricted evaluator does not allow."""


class RuleTooComplexError(RuleEvaluationError):
    """The rule is longer / larger / more deeply nested than the limits allow."""


class _RuleEvaluator:
    """Evaluates a pre-validated rule AST against a set of bound names."""

    def __init__(self, names: Dict[str, Any]) -> None:
        self._names = names

    def evaluate(self, node: ast.AST) -> Any:  # noqa: ANN401 (rules yield arbitrary JSON values)
        handler = _HANDLERS.get(type(node))
        if handler is None:
            # Unreachable for a validated tree; kept so the evaluator fails
            # closed if validation and evaluation ever drift apart.
            raise UnsupportedRuleError(f"'{type(node).__name__}' is not allowed in a rule")
        return handler(self, node)

    def _eval_constant(self, node: ast.Constant) -> Any:  # noqa: ANN401
        return node.value

    def _eval_name(self, node: ast.Name) -> Any:  # noqa: ANN401
        if node.id in self._names:
            return self._names[node.id]
        if node.id in _ALLOWED_BUILTINS:
            return _ALLOWED_BUILTINS[node.id]
        # Mirrors CPython's message so existing rule-error reporting is unchanged.
        raise NameError(f"name '{node.id}' is not defined")

    def _eval_bool_op(self, node: ast.BoolOp) -> Any:  # noqa: ANN401
        if isinstance(node.op, ast.And):
            result: Any = True
            for value in node.values:
                result = self.evaluate(value)
                if not result:
                    return result
            return result
        result = False
        for value in node.values:
            result = self.evaluate(value)
            if result:
                return result
        return result

    def _eval_unary_op(self, node: ast.UnaryOp) -> Any:  # noqa: ANN401
        operand = self.evaluate(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        if isinstance(node.op, ast.USub):
            return -operand
        return +operand

    def _eval_bin_op(self, node: ast.BinOp) -> Any:  # noqa: ANN401
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        return _BIN_OP_IMPLS[type(node.op)](left, right)

    def _eval_compare(self, node: ast.Compare) -> Any:  # noqa: ANN401
        left = self.evaluate(node.left)
        result: Any = True
        for operator, comparator_node in zip(node.ops, node.comparators, strict=True):
            right = self.evaluate(comparator_node)
            # Returning the comparison's own value (rather than a coerced bool)
            # keeps parity with Python, which the caller's ``is True`` relies on.
            result = _COMPARE_IMPLS[type(operator)](left, right)
            if not result:
                return result
            left = right
        return result

    def _eval_if_exp(self, node: ast.IfExp) -> Any:  # noqa: ANN401
        if self.evaluate(node.test):
            return self.evaluate(node.body)
        return self.evaluate(node.orelse)

    def _eval_subscript(self, node: ast.Subscript) -> Any:  # noqa: ANN401
        return self.evaluate(node.value)[self.evaluate(node.slice)]

    def _eval_slice(self, node: ast.Slice) -> slice:
        return slice(
            None if node.lower is None else self.evaluate(node.lower),
            None if node.upper is None else self.evaluate(node.upper),
            None if node.step is None else self.evaluate(node.step),
        )

    def _eval_tuple(self, node: ast.Tuple) -> Tuple[Any, ...]:
        return tuple(self.evaluate(element) for element in node.elts)

    def _eval_list(self, node: ast.List) -> list:
        return [self.evaluate(element) for element in node.elts]

    def _eval_set(self, node: ast.Set) -> set:
        return {self.evaluate(element) for element in node.elts}

    def _eval_dict(self, node: ast.Dict) -> dict:
        return {
            self.evaluate(key): self.evaluate(value)
            for key, value in zip(node.keys, node.values, strict=True)
            if key is not None  # ``{**other}`` is rejected during validation
        }

    def _eval_call(self, node: ast.Call) -> Any:  # noqa: ANN401
        args = [self.evaluate(arg) for arg in node.args]
        kwargs = {keyword.arg: self.evaluate(keyword.value) for keyword in node.keywords if keyword.arg is not None}
        if isinstance(node.func, ast.Attribute):
            receiver = self.evaluate(node.func.value)
            # Defence in depth: every name in ``_ALLOWED_METHODS`` is a method of
            # a plain JSON-ish value, but a receiver can also be a type or a
            # builtin carried in through a literal (``[str][0].upper("a")``).
            # Refusing a callable receiver keeps an unbound method from ever
            # being reachable, so adding a name to the allow-list later cannot
            # accidentally widen the sandbox.
            if isinstance(receiver, type) or callable(receiver):
                raise UnsupportedRuleError(f"method '{node.func.attr}' cannot be called on a callable")
            method = getattr(receiver, node.func.attr, None)
            if method is None or not callable(method):
                raise UnsupportedRuleError(f"'{type(receiver).__name__}' has no method '{node.func.attr}'")
            return method(*args, **kwargs)
        # Validation guarantees a bare call is a name bound to an allowed builtin.
        return self.evaluate(node.func)(*args, **kwargs)


_HANDLERS: Dict[type, Callable[[_RuleEvaluator, Any], Any]] = {
    ast.Constant: _RuleEvaluator._eval_constant,
    ast.Name: _RuleEvaluator._eval_name,
    ast.BoolOp: _RuleEvaluator._eval_bool_op,
    ast.UnaryOp: _RuleEvaluator._eval_unary_op,
    ast.BinOp: _RuleEvaluator._eval_bin_op,
    ast.Compare: _RuleEvaluator._eval_compare,
    ast.IfExp: _RuleEvaluator._eval_if_exp,
    ast.Subscript: _RuleEvaluator._eval_subscript,
    ast.Slice: _RuleEvaluator._eval_slice,
    ast.Tuple: _RuleEvaluator._eval_tuple,
    ast.List: _RuleEvaluator._eval_list,
    ast.Set: _RuleEvaluator._eval_set,
    ast.Dict: _RuleEvaluator._eval_dict,
    ast.Call: _RuleEvaluator._eval_call,
}

_BIN_OP_IMPLS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.FloorDiv: lambda left, right: left // right,
    ast.Mod: lambda left, right: left % right,
}

_COMPARE_IMPLS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Eq: lambda left, right: left == right,
    ast.NotEq: lambda left, right: left != right,
    ast.Lt: lambda left, right: left < right,
    ast.LtE: lambda left, right: left <= right,
    ast.Gt: lambda left, right: left > right,
    ast.GtE: lambda left, right: left >= right,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
    ast.Is: lambda left, right: left is right,
    ast.IsNot: lambda left, right: left is not right,
}


class _Budget:
    """Counts validated nodes so a pathological rule cannot exhaust the Lambda."""

    def __init__(self, limit: int) -> None:
        self._remaining = limit
        self._limit = limit

    def consume(self) -> None:
        self._remaining -= 1
        if self._remaining < 0:
            raise RuleTooComplexError(f"rule has more than {self._limit} expression elements")


def _validate_node_details(node: ast.AST) -> None:
    """Check the operators / constants a node carries as non-child attributes."""
    if isinstance(node, ast.Constant) and not isinstance(node.value, _ALLOWED_CONSTANT_TYPES):
        raise UnsupportedRuleError(f"constant of type '{type(node.value).__name__}' is not allowed in a rule")

    if isinstance(node, ast.BoolOp) and not isinstance(node.op, _ALLOWED_BOOL_OPS):
        raise UnsupportedRuleError(f"boolean operator '{type(node.op).__name__}' is not allowed in a rule")

    if isinstance(node, ast.UnaryOp) and not isinstance(node.op, _ALLOWED_UNARY_OPS):
        raise UnsupportedRuleError(f"unary operator '{type(node.op).__name__}' is not allowed in a rule")

    if isinstance(node, ast.BinOp) and not isinstance(node.op, _ALLOWED_BIN_OPS):
        raise UnsupportedRuleError(f"operator '{type(node.op).__name__}' is not allowed in a rule")

    if isinstance(node, ast.Compare):
        for operator in node.ops:
            if not isinstance(operator, _ALLOWED_COMPARE_OPS):
                raise UnsupportedRuleError(f"comparison '{type(operator).__name__}' is not allowed in a rule")

    if isinstance(node, ast.Dict) and any(key is None for key in node.keys):
        raise UnsupportedRuleError("dictionary unpacking is not allowed in a rule")


def _validate(node: ast.AST, budget: _Budget, depth: int = 0) -> None:
    """Recursively check that ``node`` only uses the allowed grammar.

    Recursion is used rather than :func:`ast.walk` because an ``ast.Attribute``
    is only acceptable in one position - as the callee of a call to an
    allow-listed method - and a flat walk cannot see that context.
    """
    if depth > MAX_NESTING_DEPTH:
        raise RuleTooComplexError(f"rule is nested more than {MAX_NESTING_DEPTH} levels deep")

    node_type = type(node)
    if node_type not in _HANDLERS:
        raise UnsupportedRuleError(f"'{node_type.__name__}' is not allowed in a rule")
    budget.consume()
    _validate_node_details(node)

    if isinstance(node, ast.Call):
        _validate_call(node, budget, depth)
        return

    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.expr_context, ast.boolop, ast.operator, ast.unaryop, ast.cmpop)):
            continue
        _validate(child, budget, depth + 1)


def _validate_call(node: ast.Call, budget: _Budget, depth: int) -> None:
    if any(isinstance(arg, ast.Starred) for arg in node.args):
        raise UnsupportedRuleError("argument unpacking is not allowed in a rule")
    if any(keyword.arg is None for keyword in node.keywords):
        raise UnsupportedRuleError("keyword argument unpacking is not allowed in a rule")

    if isinstance(node.func, ast.Attribute):
        attribute = node.func.attr
        if attribute.startswith("_") or attribute not in _ALLOWED_METHODS:
            raise UnsupportedRuleError(f"method '{attribute}' is not allowed in a rule")
        budget.consume()
        # The receiver is validated as an ordinary expression; the attribute
        # itself is never evaluated as a standalone value.
        _validate(node.func.value, budget, depth + 1)
    elif isinstance(node.func, ast.Name):
        if node.func.id not in _ALLOWED_BUILTINS:
            raise UnsupportedRuleError(f"function '{node.func.id}' is not allowed in a rule")
        budget.consume()
    else:
        raise UnsupportedRuleError("only calls to allowed builtins and allowed methods are permitted in a rule")

    for arg in node.args:
        _validate(arg, budget, depth + 1)
    for keyword in node.keywords:
        _validate(keyword.value, budget, depth + 1)


# Rules are fixed for the lifetime of the Lambda container while
# ``evaluate_rule`` runs once per rule per event, so the parsed-and-validated
# tree is memoised. Failures are memoised too: without that, a single malformed
# rule would be re-parsed on every event forever.
_RULE_CACHE: Dict[str, Any] = {}
_RULE_CACHE_MAX_ENTRIES = 1024


def _parse_and_validate(expression: str) -> ast.Expression:
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise RuleTooComplexError(f"rule is longer than {MAX_EXPRESSION_LENGTH} characters")

    tree = ast.parse(expression, mode="eval")
    _validate(tree.body, _Budget(MAX_AST_NODES))
    return tree


def _compile_rule(expression: str) -> ast.Expression:
    """Return the validated AST for ``expression``, parsing it at most once."""
    cached = _RULE_CACHE.get(expression)
    if cached is not None:
        if isinstance(cached, Exception):
            # Drop the accumulated traceback so re-raising a memoised failure
            # does not grow without bound.
            raise cached.with_traceback(None)
        return cached

    try:
        compiled = _parse_and_validate(expression)
    except Exception as error:
        if len(_RULE_CACHE) < _RULE_CACHE_MAX_ENTRIES:
            _RULE_CACHE[expression] = error
        raise

    if len(_RULE_CACHE) < _RULE_CACHE_MAX_ENTRIES:
        _RULE_CACHE[expression] = compiled
    return compiled


def evaluate_rule(
    expression: str, event: Dict[str, Any]
) -> Any:  # noqa: ANN401 (a rule may return any value; the caller requires ``is True``)
    """Evaluate a rule ``expression`` with ``event`` bound to the flattened event.

    Raises :class:`SyntaxError` for a malformed expression, :class:`NameError`
    for an unknown name, :class:`RuleEvaluationError` for syntax outside the
    allowed grammar, and whatever the expression itself raises (for example
    ``KeyError`` for a missing key) - matching how the previous ``eval``-based
    implementation surfaced rule problems.
    """
    tree = _compile_rule(expression)
    return _RuleEvaluator({"event": event}).evaluate(tree.body)
