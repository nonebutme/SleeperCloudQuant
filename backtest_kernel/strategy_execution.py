"""Isolated execution helper for versioned local strategies."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


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

