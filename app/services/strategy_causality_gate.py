"""Negative gate proving that emitted strategy evidence is prefix-stable."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


StrategyExecutor = Callable[
    [str, Sequence[Mapping[str, Any]], Mapping[str, Any]],
    Mapping[str, Any],
]


def verify_strategy_prefix_stability(
    source_code: str,
    bars: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
    *,
    executor: StrategyExecutor,
    checkpoints: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Reject output for past bars that changes when later bars are withheld.

    This is a runtime negative test, not a proof for every possible input.  A
    formal research run must retain its tested checkpoints and input hash as
    evidence and rerun the gate whenever source, parameters or data changes.
    """

    normalized_bars = [dict(row) for row in bars]
    if len(normalized_bars) < 3:
        return {
            "ok": False,
            "status": "insufficient_evidence",
            "issues": [{"code": "causality_sample_too_short", "row_count": len(normalized_bars)}],
            "checkpoints": [],
        }
    selected = _normalize_checkpoints(len(normalized_bars), checkpoints)
    full = dict(executor(source_code, normalized_bars, parameters))
    full_weights = list(full.get("weights") or [])
    full_scores = full.get("raw_scores")
    issues: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for length in selected:
        prefix = dict(executor(source_code, normalized_bars[:length], parameters))
        prefix_weights = list(prefix.get("weights") or [])
        weight_mismatch = _first_mismatch(full_weights[:length], prefix_weights)
        score_mismatch = None
        if full_scores is not None or prefix.get("raw_scores") is not None:
            score_mismatch = _first_mismatch(
                list(full_scores or [])[:length],
                list(prefix.get("raw_scores") or []),
            )
        evidence.append(
            {
                "prefix_length": length,
                "last_trade_date": _bar_date(normalized_bars[length - 1]),
                "weights_stable": weight_mismatch is None,
                "scores_stable": score_mismatch is None,
            }
        )
        if weight_mismatch is not None:
            issues.append(
                {
                    "code": "future_data_changes_past_weight",
                    "prefix_length": length,
                    "first_mismatch_index": weight_mismatch,
                }
            )
        if score_mismatch is not None:
            issues.append(
                {
                    "code": "future_data_changes_past_score",
                    "prefix_length": length,
                    "first_mismatch_index": score_mismatch,
                }
            )
    return {
        "ok": not issues,
        "status": "passed" if not issues else "failed",
        "issues": issues,
        "checkpoints": evidence,
        "scope": "observed_prefix_stability_negative_gate",
    }


def _normalize_checkpoints(row_count: int, checkpoints: Sequence[int] | None) -> tuple[int, ...]:
    if checkpoints is None:
        checkpoints = (
            max(2, row_count // 4),
            max(2, row_count // 2),
            max(2, row_count * 3 // 4),
            row_count - 1,
        )
    return tuple(sorted({int(value) for value in checkpoints if 2 <= int(value) < row_count}))


def _first_mismatch(expected: Sequence[Any], actual: Sequence[Any]) -> int | None:
    if len(expected) != len(actual):
        return min(len(expected), len(actual))
    for index, (left, right) in enumerate(zip(expected, actual)):
        if left != right:
            return index
    return None


def _bar_date(row: Mapping[str, Any]) -> str:
    return str(row.get("trade_date") or row.get("date") or "")[:10]
