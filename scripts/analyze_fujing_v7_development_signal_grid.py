"""Profile Fujing V7 entry-signal reachability on the pre-OOS cohort."""

from __future__ import annotations

import itertools
import json
from collections import Counter, defaultdict
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


DATA_VERSION_ID = "scq-20260810-045e17a46a731835"
COHORT_SIZE = 200
TASK_PREFIX = f"fujing-v7-development-cohort-{COHORT_SIZE}-"
TASK_SUFFIX = "-2015-2024-raw-v2"
FACTORS = (
    "winner_proxy_low_120d",
    "winner_proxy_high_120d",
    "winner_proxy_spread_120d",
    "causal_trough_event_16d",
    "amplitude_ratio_1d",
)
LOW_THRESHOLDS = (0.05, 0.10, 0.15, 0.20)
HIGH_THRESHOLDS = (0.70, 0.80, 0.90)
SPREAD_THRESHOLDS = (0.20, 0.30, 0.40)
AMPLITUDE_THRESHOLDS = (0.002, 0.004, 0.006, 0.010, 0.020)
DEFAULT = (0.10, 0.80, 0.30, 0.004)


def main() -> None:
    ensure_project_root_on_sys_path()
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    store = SqliteFactorResearchStore(Path("var/runtime/factor_research.sqlite3"))
    artifacts = {}
    tasks = {}
    for factor_id in FACTORS:
        task_id = f"{TASK_PREFIX}{factor_id}{TASK_SUFFIX}"
        task = store.get_task(task_id)
        if task.get("status") != "completed":
            raise SystemExit(f"development task is not completed: {task_id}")
        matches = [
            item for item in store.list_artifacts(factor_id=factor_id, limit=100)
            if str(item.get("source_task_id") or "") == task_id
        ]
        if len(matches) != 1 or matches[0].get("data_version_id") != DATA_VERSION_ID:
            raise SystemExit(f"exact development artifact unavailable: {factor_id}")
        artifacts[factor_id] = matches[0]
        tasks[factor_id] = task
    symbols = list(tasks[FACTORS[0]]["snapshots"][0]["payload"]["symbols"])
    if len(symbols) != COHORT_SIZE:
        raise SystemExit(f"unexpected cohort size: {len(symbols)}")
    grid = list(itertools.product(
        LOW_THRESHOLDS, HIGH_THRESHOLDS, SPREAD_THRESHOLDS, AMPLITUDE_THRESHOLDS,
    ))
    signal_counts = Counter({item: 0 for item in grid})
    symbol_counts: dict[tuple[float, ...], set[str]] = defaultdict(set)
    default_by_year: Counter[str] = Counter()
    factor_samples: dict[str, list[float]] = defaultdict(list)
    common_row_count = 0
    for symbol in symbols:
        series = {}
        for factor_id, artifact in artifacts.items():
            rows = store.fetch_artifact_values(str(artifact["artifact_id"]), symbol=symbol)
            series[factor_id] = {str(row["trade_date"]): float(row["value"]) for row in rows}
            factor_samples[factor_id].extend(float(row["value"]) for row in rows)
        dates = sorted(set.intersection(*(set(values) for values in series.values())))
        common_row_count += len(dates)
        lows = [series["winner_proxy_low_120d"][item] for item in dates]
        highs = [series["winner_proxy_high_120d"][item] for item in dates]
        spreads = [series["winner_proxy_spread_120d"][item] for item in dates]
        troughs = [series["causal_trough_event_16d"][item] for item in dates]
        amplitudes = [series["amplitude_ratio_1d"][item] for item in dates]
        for index in range(199, len(dates)):
            recent_lows = lows[max(0, index - 5):index + 1]
            recent_highs = highs[max(0, index - 9):index + 1]
            trough_pairs = list(zip(
                troughs[max(0, index - 4):index + 1],
                amplitudes[max(0, index - 4):index + 1],
            ))
            for config in grid:
                low_threshold, high_threshold, spread_threshold, amplitude_threshold = config
                signal = (
                    any(value < low_threshold for value in recent_lows)
                    and not any(value > high_threshold for value in recent_highs)
                    and spreads[index] > spread_threshold
                    and any(
                        trough == 1.0 and amplitude > amplitude_threshold
                        for trough, amplitude in trough_pairs
                    )
                )
                if signal:
                    signal_counts[config] += 1
                    symbol_counts[config].add(symbol)
                    if config == DEFAULT:
                        default_by_year[dates[index][:4]] += 1
    ranked = sorted(grid, key=lambda item: (-signal_counts[item], item))
    payload = {
        "status": "passed",
        "policy": "development_signal_reachability_not_performance_not_oos",
        "data_version_id": DATA_VERSION_ID,
        "cohort_symbol_count": len(symbols),
        "cohort_symbols_sha256": tasks[FACTORS[0]]["snapshots"][0]["content_hash"],
        "common_factor_rows": common_row_count,
        "grid_candidate_count": len(grid),
        "default_parameters": _config_payload(DEFAULT, signal_counts, symbol_counts),
        "default_signals_by_year": dict(sorted(default_by_year.items())),
        "highest_signal_count_candidates": [
            _config_payload(item, signal_counts, symbol_counts) for item in ranked[:20]
        ],
        "zero_signal_candidate_count": sum(signal_counts[item] == 0 for item in grid),
        "factor_distributions": {
            factor_id: _percentiles(values)
            for factor_id, values in factor_samples.items()
        },
        "limitations": [
            "signal frequency is not performance evidence",
            "the 200-symbol deterministic cohort is not the full point-in-time universe",
            "no dates on or after 2025-01-01 were read",
            "parameters remain unfrozen and V7 remains inactive",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _config_payload(config, counts, symbols) -> dict[str, object]:
    low, high, spread, amplitude = config
    return {
        "winner_low_threshold": low,
        "winner_high_threshold": high,
        "winner_spread_min": spread,
        "amplitude_ratio_min": amplitude,
        "signal_rows": counts[config],
        "symbols_with_signal": len(symbols[config]),
    }


def _percentiles(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "p01": None, "p05": None, "p50": None, "p95": None, "p99": None}
    ordered = sorted(values)
    def pick(fraction: float) -> float:
        return ordered[round((len(ordered) - 1) * fraction)]
    return {
        "count": len(ordered),
        "p01": pick(0.01), "p05": pick(0.05), "p50": pick(0.50),
        "p95": pick(0.95), "p99": pick(0.99),
    }


if __name__ == "__main__":
    main()
