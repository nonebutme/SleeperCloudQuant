"""One fail-closed preflight facade for the Fujing V7 research candidate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.services.governed_point_in_time_universe import build_point_in_time_a_share_universe
from app.services.sealed_oos_evidence_gate import verify_frozen_inputs
from app.services.strategy_causality_gate import StrategyExecutor, verify_strategy_prefix_stability
from app.services.strategy_research_preflight import (
    parse_strategy_dataset_contracts,
    validate_prepared_research_window,
    validate_strategy_research_contract,
)


FUJING_V7_STRUCTURAL_EXCLUSION_PREFIXES = (
    "688", "689", "8", "43", "83", "87", "92", "900", "200",
)


def run_fujing_v7_preflight(
    *,
    source_code: str,
    bars: Sequence[Mapping[str, Any]],
    parameters: Mapping[str, Any],
    evaluation_start_date: str,
    evaluation_end_date: str,
    universe_rows: Sequence[Mapping[str, Any]],
    universe_as_of_date: str,
    executor: StrategyExecutor,
    oos_manifest: Mapping[str, Any] | None = None,
    source_sha256: str = "",
    dataset_bindings: Sequence[Mapping[str, Any]] = (),
    factor_bindings: Sequence[Mapping[str, Any]] = (),
    universe_snapshot_id: str = "",
) -> dict[str, Any]:
    """Run every mandatory gate and return one auditable decision."""

    contract = validate_strategy_research_contract(source_code)
    contracts = parse_strategy_dataset_contracts(source_code) if contract["ok"] else ()
    research_window = (
        validate_prepared_research_window(
            bars,
            evaluation_start_date=evaluation_start_date,
            evaluation_end_date=evaluation_end_date,
            contracts=contracts,
        )
        if contracts
        else {"ok": False, "issues": [{"code": "valid_contract_required"}]}
    )
    universe = build_point_in_time_a_share_universe(
        universe_rows,
        as_of_date=universe_as_of_date,
        structural_exclusion_prefixes=FUJING_V7_STRUCTURAL_EXCLUSION_PREFIXES,
    )
    causality = verify_strategy_prefix_stability(
        source_code,
        bars,
        parameters,
        executor=executor,
    )
    oos = {"ok": True, "status": "not_requested", "issues": []}
    if oos_manifest is not None:
        oos = verify_frozen_inputs(
            oos_manifest,
            source_sha256=source_sha256,
            parameters=parameters,
            dataset_bindings=dataset_bindings,
            factor_bindings=factor_bindings,
            universe_snapshot_id=universe_snapshot_id,
        )
    gates = {
        "field_contract": contract,
        "research_window": research_window,
        "point_in_time_universe": universe,
        "causality": causality,
        "sealed_oos": oos,
    }
    failed = [name for name, result in gates.items() if not result.get("ok")]
    return {
        "ok": not failed,
        "status": "ready" if not failed else "blocked",
        "failed_gates": failed,
        "gates": gates,
        "policy": "fujing-v7-preflight-fail-closed-v1",
    }
