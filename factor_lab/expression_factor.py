"""Safe, deterministic expression factors for governed local research."""

from __future__ import annotations

import ast
import math
import statistics
from typing import Any, Mapping, Sequence


ALLOWED_FIELDS = frozenset({"open", "high", "low", "close", "volume", "amount"})
WINDOW_FUNCTIONS = frozenset({"lag", "mean", "std", "min", "max"})
SCALAR_FUNCTIONS = frozenset({"abs"})
MAX_WINDOW = 252


def validate_expression(expression: str) -> dict[str, Any]:
    source = str(expression or "").strip()
    if not source or len(source) > 500:
        raise ValueError("expression must contain 1 to 500 characters")
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as error:
        raise ValueError(f"invalid expression syntax: {error.msg}") from error
    state = {"fields": set(), "minimum_history": 1}
    _validate_node(tree.body, state)
    return {
        "status": "valid",
        "expression": source,
        "input_fields": sorted(state["fields"]),
        "minimum_history": int(state["minimum_history"]),
        "allowed_fields": sorted(ALLOWED_FIELDS),
        "allowed_functions": sorted(WINDOW_FUNCTIONS | SCALAR_FUNCTIONS),
    }


def calculate_expression_factor(
    expression: str, bars: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    validation = validate_expression(expression)
    tree = ast.parse(validation["expression"], mode="eval")
    ordered = sorted(
        (dict(row) for row in bars if row.get("date") or row.get("trade_date")),
        key=lambda row: str(row.get("date") or row.get("trade_date")),
    )
    result: dict[str, float] = {}
    for index, row in enumerate(ordered):
        value = _evaluate(tree.body, ordered, index)
        if value is not None and math.isfinite(value):
            result[str(row.get("date") or row.get("trade_date"))[:10]] = value
    return result


def _validate_node(node: ast.AST, state: dict[str, Any]) -> None:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numeric constants are allowed")
        return
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_FIELDS:
            raise ValueError(f"unsupported field: {node.id}")
        state["fields"].add(node.id)
        return
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
    ):
        _validate_node(node.left, state)
        _validate_node(node.right, state)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        _validate_node(node.operand, state)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if node.keywords:
            raise ValueError("keyword arguments are not allowed")
        if name in SCALAR_FUNCTIONS and len(node.args) == 1:
            _validate_node(node.args[0], state)
            return
        if name in WINDOW_FUNCTIONS and len(node.args) == 2:
            field, window = node.args
            if not isinstance(field, ast.Name) or field.id not in ALLOWED_FIELDS:
                raise ValueError(f"{name} first argument must be an allowed field")
            if (
                not isinstance(window, ast.Constant)
                or isinstance(window.value, bool)
                or not isinstance(window.value, int)
                or not 1 <= window.value <= MAX_WINDOW
            ):
                raise ValueError(f"{name} window must be an integer between 1 and {MAX_WINDOW}")
            state["fields"].add(field.id)
            history = window.value + 1 if name == "lag" else window.value
            state["minimum_history"] = max(state["minimum_history"], history)
            return
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def _evaluate(node: ast.AST, rows: Sequence[Mapping[str, Any]], index: int) -> float | None:
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        return _number(rows[index].get(node.id))
    if isinstance(node, ast.UnaryOp):
        value = _evaluate(node.operand, rows, index)
        if value is None:
            return None
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, rows, index)
        right = _evaluate(node.right, rows, index)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            return None
        return left / right
    if isinstance(node, ast.Call):
        name = node.func.id
        if name == "abs":
            value = _evaluate(node.args[0], rows, index)
            return None if value is None else abs(value)
        field = node.args[0].id
        window = int(node.args[1].value)
        if name == "lag":
            return None if index < window else _number(rows[index - window].get(field))
        start = index - window + 1
        if start < 0:
            return None
        values = [_number(row.get(field)) for row in rows[start : index + 1]]
        if any(value is None for value in values):
            return None
        clean = [float(value) for value in values if value is not None]
        if name == "mean":
            return statistics.fmean(clean)
        if name == "std":
            return statistics.pstdev(clean)
        if name == "min":
            return min(clean)
        return max(clean)
    return None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
