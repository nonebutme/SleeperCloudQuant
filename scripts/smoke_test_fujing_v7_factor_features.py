"""Deterministic checks for governed Fujing v7 candidate features."""

from __future__ import annotations

import math
from datetime import date, timedelta

from _project_bootstrap import ensure_project_root_on_sys_path


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise SystemExit(f"fujing v7 feature smoke failed: {label}: {actual!r} != {expected!r}")


def main() -> None:
    ensure_project_root_on_sys_path()

    from factor_lab import FactorRegistry
    from factor_lab.calculators.fujing_features import (
        FUJING_FEATURE_DEFINITIONS,
        calculate_fujing_feature,
    )

    start = date(2026, 1, 1)
    bars = []
    for index in range(125):
        price = float(index + 1)
        bars.append(
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 1.0,
            }
        )
    bars[119].update({"open": 120.0, "high": 120.5, "low": 119.5, "close": 120.0})
    day_120 = bars[119]["date"]

    low_values = calculate_fujing_feature("winner_proxy_low_120d", bars)
    high_values = calculate_fujing_feature("winner_proxy_high_120d", bars)
    spread_values = calculate_fujing_feature("winner_proxy_spread_120d", bars)
    if len(calculate_fujing_feature("winner_proxy_low_120d", bars[:119])) != 0:
        raise SystemExit("fujing v7 feature smoke failed: WINNER proxy emitted before complete history")
    _assert_close(low_values[day_120], 119.0 / 120.0, "WINNER low proxy")
    _assert_close(high_values[day_120], 1.0, "WINNER high proxy")
    _assert_close(spread_values[day_120], 1.0 / 120.0, "WINNER spread proxy")
    if calculate_fujing_feature(" WINNER_PROXY_LOW_120D ", bars) != low_values:
        raise SystemExit("fujing v7 feature smoke failed: factor id normalization mismatch")

    amplitude = calculate_fujing_feature("amplitude_ratio_1d", bars)
    _assert_close(amplitude[day_120], 1.0 / 119.0, "previous-close amplitude ratio")
    if bars[0]["date"] in amplitude:
        raise SystemExit("fujing v7 feature smoke failed: amplitude emitted without previous close")

    trough_bars = [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "open": 20.0,
            "high": 21.0,
            "low": 20.0 - index,
            "close": 20.0,
            "volume": 1.0,
        }
        for index in range(16)
    ]
    trough = calculate_fujing_feature("causal_trough_event_16d", trough_bars)
    if len(trough) != 1 or trough[trough_bars[-1]["date"]] != 1.0:
        raise SystemExit("fujing v7 feature smoke failed: causal trough golden sample mismatch")

    factor_ids = [item["factor_id"] for item in FUJING_FEATURE_DEFINITIONS]
    for factor_id in factor_ids:
        full = calculate_fujing_feature(factor_id, bars)
        for prefix_length in (16, 119, 120, 123):
            prefix = calculate_fujing_feature(factor_id, bars[:prefix_length])
            if prefix != {key: full[key] for key in prefix}:
                raise SystemExit(f"fujing v7 feature smoke failed: prefix instability: {factor_id}")

    definitions = {item["factor_id"]: item for item in FUJING_FEATURE_DEFINITIONS}
    if not all(definitions[factor_id]["parameters"].get("proxy") for factor_id in factor_ids[:3]):
        raise SystemExit("fujing v7 feature smoke failed: WINNER proxy disclosure missing")
    if definitions["causal_trough_event_16d"]["minimum_history"] != 16:
        raise SystemExit("fujing v7 feature smoke failed: trough history contract mismatch")
    registered = {item.factor_id for item in FactorRegistry().definitions()}
    if not set(factor_ids).issubset(registered):
        raise SystemExit("fujing v7 feature smoke failed: calculators not registered")

    print("fujing v7 governed factor features smoke test passed")


if __name__ == "__main__":
    main()
