"""Pure preflight gates for governed strategy research inputs.

This module is intentionally side-effect free.  It turns a strategy's literal
``DATASET_CONTRACTS`` declaration into a field-level contract and verifies a
prepared research bundle before any strategy code is executed.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from data_platform.dataset_registry import DatasetRegistry


_MISSING_POLICIES = frozenset({"unavailable", "skip", "forward_fill", "fail"})
_VERSION_POLICIES = frozenset({"latest_published", "exact_published"})
_COVERAGE_MODES = frozenset({"same_trade_date", "as_of_trade_date", "event_stream"})


@dataclass(frozen=True, slots=True)
class StrategyDatasetContract:
    dataset_id: str
    required_fields: tuple[str, ...] = ()
    minimum_history: int = 0
    adjustment: str | None = None
    point_in_time_required: bool = True
    missing_data_policy: str = "unavailable"
    version_policy: str = "latest_published"
    coverage_mode: str = "same_trade_date"


def parse_strategy_dataset_contracts(source_code: str) -> tuple[StrategyDatasetContract, ...]:
    """Parse the strict V7 contract without executing user strategy code."""

    raw = _read_literal(source_code, "DATASET_CONTRACTS")
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ValueError("DATASET_CONTRACTS must be a literal list or tuple")
    contracts: list[StrategyDatasetContract] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"DATASET_CONTRACTS[{index}] must be a literal dict")
        dataset_id = str(item.get("dataset_id") or "").strip()
        if not dataset_id:
            raise ValueError(f"DATASET_CONTRACTS[{index}].dataset_id is required")
        if dataset_id in seen:
            raise ValueError(f"duplicate dataset contract: {dataset_id}")
        fields = item.get("required_fields", ())
        if not isinstance(fields, (list, tuple)) or not all(isinstance(value, str) for value in fields):
            raise ValueError(f"{dataset_id}.required_fields must be a literal string list")
        contract = StrategyDatasetContract(
            dataset_id=dataset_id,
            required_fields=_normalize(fields),
            minimum_history=int(item.get("minimum_history") or 0),
            adjustment=str(item.get("adjustment") or "") or None,
            point_in_time_required=bool(item.get("point_in_time_required", True)),
            missing_data_policy=str(item.get("missing_data_policy") or "unavailable"),
            version_policy=str(item.get("version_policy") or "latest_published"),
            coverage_mode=str(item.get("coverage_mode") or "same_trade_date"),
        )
        _validate_policy_values(contract)
        seen.add(dataset_id)
        contracts.append(contract)
    return tuple(contracts)


def require_strategy_runtime_adjustment(
    source_code: str,
    actual_adjustment: str,
) -> dict[str, str] | None:
    """Fail closed when a strict strategy runs on a different price adjustment.

    Legacy strategies without ``DATASET_CONTRACTS`` keep their compatibility
    behavior.  A strict contract, however, must not declare qfq while the
    runtime silently fetches raw or hfq bars.
    """

    contracts = parse_strategy_dataset_contracts(source_code)
    daily = next(
        (item for item in contracts if item.dataset_id == "a_share_daily"),
        None,
    )
    if daily is None or not daily.adjustment:
        return None
    actual = str(actual_adjustment or "").strip().lower()
    declared = str(daily.adjustment).strip().lower()
    if not actual:
        raise ValueError(
            f"strategy_adjustment_context_required: declared={declared}"
        )
    if actual != declared:
        raise ValueError(
            f"strategy_adjustment_mismatch: declared={declared} run={actual}"
        )
    return {
        "dataset_id": "a_share_daily",
        "declared_adjustment": declared,
        "runtime_adjustment": actual,
        "status": "matched",
    }


def validate_strategy_research_contract(
    source_code: str,
    *,
    registry: DatasetRegistry | None = None,
) -> dict[str, Any]:
    """Validate strict field, adjustment, version and point-in-time declarations."""

    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        contracts = parse_strategy_dataset_contracts(source_code)
    except (TypeError, ValueError) as error:
        return {
            "ok": False,
            "contracts": [],
            "issues": [{"code": "invalid_contract", "message": str(error)}],
            "warnings": [],
        }
    declared_ids = _read_string_list(source_code, "DATASET_REQUIREMENTS")
    contract_ids = [item.dataset_id for item in contracts]
    if not contracts:
        issues.append({"code": "field_level_contract_required"})
    if set(declared_ids) != set(contract_ids):
        issues.append(
            {
                "code": "dataset_declaration_mismatch",
                "declared_dataset_ids": declared_ids,
                "contract_dataset_ids": contract_ids,
            }
        )
    catalog = registry or DatasetRegistry()
    for contract in contracts:
        definition = catalog.get(contract.dataset_id)
        if definition is None:
            issues.append({"code": "unknown_dataset", "dataset_id": contract.dataset_id})
            continue
        if definition.availability_status != "connected":
            issues.append(
                {
                    "code": "dataset_unavailable",
                    "dataset_id": contract.dataset_id,
                    "status": definition.availability_status,
                }
            )
        available_fields = {field.name for field in definition.fields}
        missing = sorted(set(contract.required_fields) - available_fields)
        if missing:
            issues.append(
                {"code": "dataset_fields_missing", "dataset_id": contract.dataset_id, "fields": missing}
            )
        if contract.adjustment and contract.adjustment not in set(definition.supported_adjustments):
            issues.append(
                {
                    "code": "dataset_adjustment_unsupported",
                    "dataset_id": contract.dataset_id,
                    "adjustment": contract.adjustment,
                }
            )
        if contract.point_in_time_required and definition.point_in_time_policy == "not_applicable" and contract.coverage_mode != "same_trade_date":
            issues.append(
                {"code": "point_in_time_policy_missing", "dataset_id": contract.dataset_id}
            )
    accesses = infer_strategy_field_accesses(source_code, contract_ids)
    for contract in contracts:
        accessed = set(accesses.get(contract.dataset_id) or ())
        declared = set(contract.required_fields)
        undeclared = sorted(accessed - declared)
        if undeclared:
            issues.append(
                {
                    "code": "strategy_field_access_undeclared",
                    "dataset_id": contract.dataset_id,
                    "fields": undeclared,
                }
            )
        unused = sorted(declared - accessed)
        if unused:
            warnings.append(
                {
                    "code": "declared_fields_not_observed_in_static_scan",
                    "dataset_id": contract.dataset_id,
                    "fields": unused,
                }
            )
    return {
        "ok": not issues,
        "contracts": [_contract_payload(item) for item in contracts],
        "issues": issues,
        "warnings": warnings,
    }


def infer_strategy_field_accesses(
    source_code: str,
    dataset_ids: Sequence[str],
) -> dict[str, list[str]]:
    """Conservatively infer common ``bar.get`` and dataset-alias field reads."""

    tree = ast.parse(source_code)
    known = set(dataset_ids)
    container_aliases = {"datasets"}
    dataset_aliases: dict[str, str] = {}
    bar_aliases = {"bar", "first", "row"}
    for node in ast.walk(tree):
        if isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            if isinstance(node.iter, ast.Name) and node.iter.id == "bars":
                bar_aliases.add(node.target.id)
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        alias = node.targets[0].id
        if _contains_get_key(node.value, "datasets"):
            container_aliases.add(alias)
        if isinstance(node.value, ast.Subscript) and isinstance(node.value.value, ast.Name) and node.value.value.id == "bars":
            bar_aliases.add(alias)
    for _ in range(3):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            dataset_id = _dataset_reference(node.value, known, container_aliases)
            if dataset_id:
                dataset_aliases[node.targets[0].id] = dataset_id
    accesses: dict[str, set[str]] = {dataset_id: set() for dataset_id in known}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        field = node.args[0].value
        receiver = node.func.value
        if isinstance(receiver, ast.Name) and receiver.id in dataset_aliases:
            accesses[dataset_aliases[receiver.id]].add(field)
        elif "a_share_daily" in known and _is_bar_expression(receiver, bar_aliases):
            if field != "datasets" and field not in known:
                accesses["a_share_daily"].add(field)
    return {dataset_id: sorted(fields) for dataset_id, fields in accesses.items()}


def validate_prepared_research_window(
    bars: Sequence[Mapping[str, Any]],
    *,
    evaluation_start_date: str,
    evaluation_end_date: str,
    contracts: Sequence[StrategyDatasetContract],
) -> dict[str, Any]:
    """Verify warm-up separation and common daily coverage on prepared bars."""

    ordered = sorted((dict(row) for row in bars), key=_bar_date)
    evaluation_start = str(evaluation_start_date)[:10]
    evaluation_end = str(evaluation_end_date)[:10]
    warmup = [row for row in ordered if _bar_date(row) < evaluation_start]
    evaluation = [row for row in ordered if evaluation_start <= _bar_date(row) <= evaluation_end]
    issues: list[dict[str, Any]] = []
    required_history = max((item.minimum_history for item in contracts), default=0)
    if len(warmup) < required_history:
        issues.append(
            {
                "code": "warmup_history_incomplete",
                "required_rows": required_history,
                "available_rows": len(warmup),
            }
        )
    if not evaluation:
        issues.append({"code": "evaluation_window_empty"})
    expected_dates = {_bar_date(row) for row in ordered if _bar_date(row)}
    for contract in contracts:
        if contract.coverage_mode not in {"same_trade_date", "as_of_trade_date"}:
            continue
        matched_dates = {
            _bar_date(row)
            for row in ordered
            if (row.get("datasets") or {}).get(contract.dataset_id) is not None
        }
        contract_expected_dates = expected_dates
        if contract.dataset_id == "factor_values":
            factor_warmup_required = max(0, contract.minimum_history - 1)
            all_factor_warmup_dates = [
                _bar_date(row) for row in warmup if _bar_date(row)
            ]
            factor_warmup_dates = (
                all_factor_warmup_dates[-factor_warmup_required:]
                if factor_warmup_required else []
            )
            contract_expected_dates = {
                *factor_warmup_dates,
                *(_bar_date(row) for row in evaluation if _bar_date(row)),
            }
        missing_dates = sorted(contract_expected_dates - matched_dates)
        if missing_dates and contract.missing_data_policy in {"unavailable", "fail"}:
            issues.append(
                {
                    "code": "dataset_common_coverage_incomplete",
                    "dataset_id": contract.dataset_id,
                    "missing_count": len(missing_dates),
                    "first_missing_date": missing_dates[0],
                    "last_missing_date": missing_dates[-1],
                }
            )
        if contract.dataset_id == "trading_status":
            invalid_dates: list[str] = []
            conflict_dates: list[str] = []
            for row in ordered:
                trade_date = _bar_date(row)
                if trade_date not in contract_expected_dates:
                    continue
                status = (row.get("datasets") or {}).get("trading_status")
                if not isinstance(status, Mapping):
                    continue
                tradable = _parse_optional_bool(status.get("is_tradable"))
                if tradable is None:
                    invalid_dates.append(trade_date)
                    continue
                if tradable is False and _bar_volume(row) > 0:
                    conflict_dates.append(trade_date)
            if invalid_dates:
                issues.append(
                    {
                        "code": "trading_status_value_incomplete",
                        "dataset_id": contract.dataset_id,
                        "missing_count": len(invalid_dates),
                        "first_missing_date": invalid_dates[0],
                        "last_missing_date": invalid_dates[-1],
                    }
                )
            if conflict_dates:
                issues.append(
                    {
                        "code": "trading_status_price_conflict",
                        "dataset_id": contract.dataset_id,
                        "conflict_count": len(conflict_dates),
                        "first_conflict_date": conflict_dates[0],
                        "last_conflict_date": conflict_dates[-1],
                    }
                )
    return {
        "ok": not issues,
        "warmup": {"row_count": len(warmup), "required_rows": required_history},
        "evaluation": {
            "row_count": len(evaluation),
            "start_date": evaluation_start,
            "end_date": evaluation_end,
        },
        "issues": issues,
    }


def research_fetch_start_date(source_code: str, evaluation_start_date: str) -> str:
    """Return a conservative calendar start used to fetch declared warm-up rows."""

    contracts = parse_strategy_dataset_contracts(source_code)
    required_history = max((item.minimum_history for item in contracts), default=0)
    start = date.fromisoformat(str(evaluation_start_date)[:10])
    if required_history <= 0:
        return start.isoformat()
    return (start - timedelta(days=required_history * 3 + 30)).isoformat()


def _read_literal(source_code: str, name: str) -> Any | None:
    try:
        tree = ast.parse(source_code)
    except SyntaxError as error:
        raise ValueError(f"strategy source is invalid: {error.msg}") from error
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        try:
            return ast.literal_eval(node.value)
        except (TypeError, ValueError, SyntaxError) as error:
            raise ValueError(f"{name} must be a literal") from error
    return None


def _contains_get_key(node: ast.AST, key: str) -> bool:
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "get"
        and child.args
        and isinstance(child.args[0], ast.Constant)
        and child.args[0].value == key
        for child in ast.walk(node)
    )


def _dataset_reference(
    node: ast.AST,
    known: set[str],
    container_aliases: set[str],
) -> str | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
            continue
        if child.func.attr != "get" or not child.args or not isinstance(child.args[0], ast.Constant):
            continue
        dataset_id = child.args[0].value
        receiver = child.func.value
        if (
            isinstance(dataset_id, str)
            and dataset_id in known
            and (
                isinstance(receiver, ast.Name) and receiver.id in container_aliases
                or _contains_get_key(receiver, "datasets")
            )
        ):
            return dataset_id
    return None


def _is_bar_expression(node: ast.AST, bar_aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in bar_aliases
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == "bars"
    )


def _read_string_list(source_code: str, name: str) -> list[str]:
    value = _read_literal(source_code, name)
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a literal string list")
    return list(_normalize(value))


def _validate_policy_values(contract: StrategyDatasetContract) -> None:
    if contract.minimum_history < 0:
        raise ValueError(f"{contract.dataset_id}.minimum_history must not be negative")
    if contract.missing_data_policy not in _MISSING_POLICIES:
        raise ValueError(f"unsupported missing_data_policy: {contract.missing_data_policy}")
    if contract.version_policy not in _VERSION_POLICIES:
        raise ValueError(f"unsupported version_policy: {contract.version_policy}")
    if contract.coverage_mode not in _COVERAGE_MODES:
        raise ValueError(f"unsupported coverage_mode: {contract.coverage_mode}")


def _normalize(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _bar_date(row: Mapping[str, Any]) -> str:
    return str(row.get("trade_date") or row.get("date") or "")[:10]


def _bar_volume(row: Mapping[str, Any]) -> float:
    daily = (row.get("datasets") or {}).get("a_share_daily")
    value = daily.get("volume") if isinstance(daily, Mapping) else row.get("volume")
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    return None


def _contract_payload(contract: StrategyDatasetContract) -> dict[str, Any]:
    return {
        "dataset_id": contract.dataset_id,
        "required_fields": list(contract.required_fields),
        "minimum_history": contract.minimum_history,
        "adjustment": contract.adjustment,
        "point_in_time_required": contract.point_in_time_required,
        "missing_data_policy": contract.missing_data_policy,
        "version_policy": contract.version_policy,
        "coverage_mode": contract.coverage_mode,
    }
