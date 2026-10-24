"""Isolated execution helper for versioned local strategies."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def open_signal_lag(source_code: str = "", execution_contract: str = "") -> int:
    """开盘默认消费前一根信号；已延迟策略必须显式声明。"""
    timing = "before_open" if execution_contract == "next_trade_date_open" else "bar_close"
    for node in ast.parse(source_code or "").body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SIGNAL_TIMING"
            for target in node.targets
        ):
            timing = ast.literal_eval(node.value)
    if timing not in {"bar_close", "before_open"}:
        raise ValueError("SIGNAL_TIMING must be bar_close or before_open")
    return 0 if timing == "before_open" else 1


def bar_is_tradable(row: Mapping[str, Any]) -> bool:
    """显式不可交易或无正成交量的 bar 仅用于估值。"""
    status = row.get("trading_status") or (row.get("datasets") or {}).get("trading_status") or {}
    if row.get("is_tradable") is False or (
        isinstance(status, Mapping) and status.get("is_tradable") is False
    ):
        return False
    try:
        return float(row.get("volume") or 0) > 0
    except (TypeError, ValueError):
        return False


def affordable_quantity(requested: int, cash: float, price: float, rate: float, minimum: float) -> int:
    """按含佣金的实际成交价计算可支付的整手数量。"""
    quantity = min(requested, max(0, int(cash / (price * (1 + rate)) / 100) * 100))
    while quantity > 0 and quantity * price + max(quantity * price * rate, minimum) > cash:
        quantity -= 100
    return quantity


def execute_target_weights(
    source_code: str,
    bars: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
    *,
    timeout_seconds: float = 5.0,
) -> list[float]:
    """Execute one strategy snapshot in a child interpreter."""

    request = {
        "source_code": source_code,
        "bars": [dict(item) for item in bars],
        "parameters": dict(parameters),
    }
    completed = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).with_name("strategy_worker.py"))],
        input=json.dumps(request, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "strategy worker failed"
        raise RuntimeError(message)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("strategy worker returned invalid JSON") from exc
    if payload.get("status") != "completed":
        raise RuntimeError(str(payload.get("error") or "strategy worker failed"))
    weights = payload.get("weights")
    if not isinstance(weights, list) or len(weights) != len(bars):
        raise RuntimeError("strategy must return one target weight for every bar")
    normalized: list[float] = []
    for value in weights:
        weight = float(value)
        if not 0.0 <= weight <= 1.0:
            raise RuntimeError("strategy target weights must be between 0 and 1")
        normalized.append(weight)
    return normalized


def execute_strategy_evidence(
    source_code: str,
    bars: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
    *,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    """Execute target weights and an optional point-in-time raw-score contract."""

    request = {
        "source_code": source_code,
        "bars": [dict(item) for item in bars],
        "parameters": dict(parameters),
    }
    completed = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).with_name("strategy_worker.py"))],
        input=json.dumps(request, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "strategy worker failed"
        raise RuntimeError(message)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("strategy worker returned invalid JSON") from exc
    if payload.get("status") != "completed":
        raise RuntimeError(str(payload.get("error") or "strategy worker failed"))
    weights = payload.get("weights")
    if not isinstance(weights, list) or len(weights) != len(bars):
        raise RuntimeError("strategy must return one target weight for every bar")
    normalized_weights = [float(value) for value in weights]
    if any(not 0.0 <= value <= 1.0 for value in normalized_weights):
        raise RuntimeError("strategy target weights must be between 0 and 1")
    raw_scores = payload.get("scores")
    if raw_scores is not None:
        if not isinstance(raw_scores, list) or len(raw_scores) != len(bars):
            raise RuntimeError("generate_signal_scores must return one score for every bar")
        raw_scores = [float(value) if value is not None else None for value in raw_scores]
    return {
        "weights": normalized_weights,
        "raw_scores": raw_scores,
        "score_contract": (
            "point_in_time_raw_score_v1"
            if raw_scores is not None
            else "unavailable_generate_signal_scores_missing"
        ),
    }
