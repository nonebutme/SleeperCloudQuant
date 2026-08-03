"""M3 strategy data-contract validation kept separate from the legacy editor."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from data_platform.dataset_registry import DatasetRegistry
from factor_lab.dataset_bindings import get_factor_dataset_binding


@dataclass(frozen=True, slots=True)
class StrategyDataRequirements:
    dataset_ids: tuple[str, ...] = ("a_share_daily",)
    factor_ids: tuple[str, ...] = ()


def validate_strategy_data_contract(
    source_code: str,
    *,
    dataset_ids: tuple[str, ...] | list[str] | None = None,
    factor_ids: tuple[str, ...] | list[str] | None = None,
    registry: DatasetRegistry | None = None,
) -> dict[str, Any]:
    """Validate declared datasets/factors without changing legacy source validation."""

    requirements = _resolve_requirements(
        source_code,
        dataset_ids=dataset_ids,
        factor_ids=factor_ids,
    )
    catalog = registry or DatasetRegistry()
    issues: list[dict[str, str]] = []
    datasets: list[dict[str, Any]] = []
    for dataset_id in requirements.dataset_ids:
        definition = catalog.get(dataset_id)
        if definition is None:
            issues.append({"code": "unknown_dataset", "dataset_id": dataset_id})
            continue
        datasets.append(
            {
                "dataset_id": definition.dataset_id,
                "status": definition.availability_status,
                "fields": [field.name for field in definition.fields],
                "point_in_time_policy": definition.point_in_time_policy,
            }
        )
        if definition.availability_status != "connected":
            issues.append(
                {
                    "code": "dataset_unavailable",
                    "dataset_id": dataset_id,
                    "status": definition.availability_status,
                }
            )

    factors: list[dict[str, Any]] = []
    for factor_id in requirements.factor_ids:
        try:
            binding = get_factor_dataset_binding(factor_id)
        except KeyError:
            issues.append({"code": "unknown_factor", "factor_id": factor_id})
            continue
        factors.append(
            {
                "factor_id": binding.factor_id,
                "dataset_id": binding.dataset_id,
                "required_fields": list(binding.required_fields),
                "point_in_time_policy": binding.point_in_time_policy,
            }
        )
        if binding.dataset_id not in requirements.dataset_ids:
            issues.append(
                {
                    "code": "factor_dataset_not_declared",
                    "factor_id": factor_id,
                    "dataset_id": binding.dataset_id,
                }
            )

    return {
        "ok": not issues,
        "execution_contract": "target-weights-v1",
        "requirements": {
            "dataset_ids": list(requirements.dataset_ids),
            "factor_ids": list(requirements.factor_ids),
        },
        "datasets": datasets,
        "factors": factors,
        "issues": issues,
    }


def _resolve_requirements(
    source_code: str,
    *,
    dataset_ids: tuple[str, ...] | list[str] | None,
    factor_ids: tuple[str, ...] | list[str] | None,
) -> StrategyDataRequirements:
    declared = _read_literal_list(source_code, "DATASET_REQUIREMENTS")
    declared_factors = _read_literal_list(source_code, "FACTOR_REQUIREMENTS")
    return StrategyDataRequirements(
        dataset_ids=_normalize(dataset_ids if dataset_ids is not None else declared or ["a_share_daily"]),
        factor_ids=_normalize(factor_ids if factor_ids is not None else declared_factors),
    )


def _read_literal_list(source_code: str, name: str) -> list[str]:
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return []
        if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
            return list(value)
    return []


def _normalize(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

