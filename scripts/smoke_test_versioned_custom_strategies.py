"""Smoke test for stage 60 versioned executable custom strategies."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from _project_bootstrap import ensure_project_root_on_sys_path


class PriceRepository:
    def fetch_price_history(self, symbol: str, start_date: str, end_date: str):
        del symbol, start_date, end_date
        return [
            {
                "date": f"2026-01-{index:02d}",
                "open": float(9 + index),
                "high": float(10 + index),
                "low": float(8 + index),
                "close": float(9 + index),
                "volume": 1000.0,
            }
            for index in range(1, 11)
        ]


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.services import StrategyService
    from backtest_kernel import LocalSQLiteBacktestRuntime

    database_path = Path("tmp") / f"stage60-strategies-{uuid4().hex}.sqlite3"
    service = StrategyService(database_path, legacy_drafts_path=Path("tmp") / "missing-strategy-drafts.json")

    invalid = service.validate_source("def other():\n    return []\n")
    if invalid["ok"] or not any(item["code"] == "entrypoint_missing" for item in invalid["issues"]):
        raise SystemExit("stage60 smoke failed: invalid entrypoint was accepted")

    flat = service.save_version(
        strategy_id="stage60_flat",
        name="Stage60 Flat",
        source_code="def generate_target_weights(bars, parameters):\n    return [0.0 for bar in bars]\n",
    )
    invested_v1 = service.save_version(
        strategy_id="stage60_invested",
        name="Stage60 Invested",
        source_code="def generate_target_weights(bars, parameters):\n    return [0.5 for bar in bars]\n",
    )
    invested_v2 = service.save_version(
        strategy_id="stage60_invested",
        name="Stage60 Invested",
        source_code="def generate_target_weights(bars, parameters):\n    return [1.0 for bar in bars]\n",
    )
    versions = service.list_versions("stage60_invested")
    if [item["latest_version"] for item in versions] != ["v1", "v2"]:
        raise SystemExit("stage60 smoke failed: immutable version history mismatch")
    if invested_v1["source_sha256"] == invested_v2["source_sha256"]:
        raise SystemExit("stage60 smoke failed: source hashes did not change")

    runtime = LocalSQLiteBacktestRuntime(PriceRepository(), strategy_resolver=service.resolve_version)
    base_payload = {
        "run_id": "stage60-runtime",
        "strategy_name": "stage60",
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
        "initial_cash": 100_000,
        "parameters": {"symbol": "000001.XSHE"},
    }
    flat_result = runtime.run({**base_payload, "extra_config": {"strategy_id": flat["strategy_id"], "strategy_version": "v1"}})
    invested_result = runtime.run({**base_payload, "extra_config": {"strategy_id": invested_v2["strategy_id"], "strategy_version": "v2"}})
    if flat_result["raw_result"]["trades"]:
        raise SystemExit("stage60 smoke failed: flat strategy unexpectedly traded")
    if not invested_result["raw_result"]["trades"]:
        raise SystemExit("stage60 smoke failed: invested strategy did not trade")
    binding = invested_result["raw_result"]["strategy_binding"]
    if binding["strategy_version"] != "v2" or binding["source_sha256"] != invested_v2["source_sha256"]:
        raise SystemExit("stage60 smoke failed: strategy version/hash binding missing")

    print("stage60 versioned custom strategy smoke test passed")


if __name__ == "__main__":
    main()
