"""Read-only real-data binding check for the Fujing V7 pilot artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


DATA_VERSION_ID = "scq-20260810-045e17a46a731835"
FACTOR_IDS = (
    "winner_proxy_low_120d",
    "winner_proxy_high_120d",
    "winner_proxy_spread_120d",
    "causal_trough_event_16d",
    "amplitude_ratio_1d",
)


def main() -> None:
    ensure_project_root_on_sys_path()
    from app.services.strategy_dataset_resolver import StrategyDatasetResolver
    from app.services.strategy_service import StrategyService
    from backtest_kernel.strategy_execution import execute_strategy_evidence
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.a_share_market_store import AShareMarketStore
    from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore

    market_path = Path("var/market/a_share_market.sqlite3")
    store = SqliteFactorResearchStore(Path("var/runtime/factor_research.sqlite3"))
    artifacts = {factor_id: store.resolve_artifact(factor_id) for factor_id in FACTOR_IDS}
    if any(item.get("status") != "ready" for item in artifacts.values()):
        raise SystemExit("pilot artifacts are not all ready")
    source = Path("scripts/fujing_v2_v7_candidate.py").read_text(encoding="utf-8-sig")
    validation = StrategyService.validate_source(StrategyService.__new__(StrategyService), source)
    if not validation["ok"]:
        raise SystemExit(json.dumps(validation, ensure_ascii=False))
    market = AShareMarketStore(market_path)
    bars = market.fetch_price_history(
        "000001", "2023-01-03", "2024-03-29", adjustment="qfq",
    )
    for row in bars:
        row.setdefault("symbol", "000001.XSHE")
    parameters = {
        **dict(validation["parameter_defaults"]),
        "factor_artifacts": {
            factor_id: str(artifact["artifact_id"])
            for factor_id, artifact in artifacts.items()
        },
    }
    resolver = StrategyDatasetResolver(
        AShareGovernanceStore(market_path),
        market_reader=market,
        factor_store=store,
    )
    frozen = resolver.freeze_parameters(source, parameters)
    resolved = resolver.resolve(
        source,
        bars,
        frozen,
        {
            "evaluation_start_date": "2024-01-02",
            "evaluation_end_date": "2024-03-29",
            "data_version_id": DATA_VERSION_ID,
        },
    )
    execution = execute_strategy_evidence(source, resolved["bars"], frozen)
    factor_evidence = [
        item for item in resolved["evidence"] if item.get("dataset_id") == "factor_values"
    ]
    print(json.dumps({
        "status": "passed",
        "symbol": "000001.XSHE",
        "data_version_id": DATA_VERSION_ID,
        "source_sha256": validation["source_sha256"],
        "bar_count": len(resolved["bars"]),
        "evaluation": resolved["research_window"]["evaluation"],
        "factor_evidence": factor_evidence,
        "nonzero_weight_rows": sum(float(value) > 0 for value in execution["weights"]),
        "artifact_bindings": parameters["factor_artifacts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
