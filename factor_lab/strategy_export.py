"""Build governed strategy declarations from immutable factor artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from factor_lab.research_core import canonical_hash


def build_strategy_factor_declaration(
    artifact: Mapping[str, Any],
    research_task: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a runnable, read-only target-weights declaration for one artifact."""

    artifact_id = str(artifact.get("artifact_id") or "").strip()
    factor_id = str(artifact.get("factor_id") or "").strip()
    if not artifact_id or not factor_id or artifact.get("status") != "ready":
        raise ValueError("a ready factor artifact with exact identity is required")
    if str(research_task.get("task_id") or "") != str(artifact.get("source_task_id") or ""):
        raise ValueError("factor artifact source task does not match")

    source_code = _strategy_source(factor_id)
    parameters = {
        "factor_artifacts": {factor_id: artifact_id},
        "factor_value_field": "aligned_value",
        "factor_threshold": 0.0,
        "position_size": 1.0,
        "execution_price": "close",
    }
    research_config = dict(research_task.get("config") or {})
    identity = {
        "artifact_id": artifact_id,
        "artifact_content_hash": str(artifact.get("content_hash") or ""),
        "factor_id": factor_id,
        "factor_version": str(artifact.get("factor_version") or ""),
        "source_task_id": str(artifact.get("source_task_id") or ""),
        "research_context_hash": str(artifact.get("context_hash") or ""),
        "data_version_id": str(artifact.get("data_version_id") or ""),
        "quality_report_id": str(artifact.get("quality_report_id") or ""),
    }
    declaration_id = f"strategy-factor-{canonical_hash(identity)[:20]}"
    return {
        "status": "ready",
        "schema_version": "strategy-factor-declaration-v1",
        "declaration_id": declaration_id,
        "artifact": identity,
        "value_field": "aligned_value",
        "dataset_requirements": ["a_share_daily", "factor_values"],
        "factor_requirements": [factor_id],
        "source_code": source_code,
        "source_sha256": hashlib.sha256(source_code.encode("utf-8")).hexdigest(),
        "parameters": parameters,
        "research_config_snapshot": research_config,
        "execution_contract": "target-weights-v1",
        "execution_policy": "explicit_start_required",
        "artifact_binding": "immutable_exact_id",
        "writes": 0,
        "task_started": False,
    }


def _strategy_source(factor_id: str) -> str:
    factor_literal = repr(factor_id)
    return f'''DATASET_REQUIREMENTS = ["a_share_daily", "factor_values"]
FACTOR_REQUIREMENTS = [{factor_literal}]
FACTOR_VALUE_FIELD = "aligned_value"

def generate_target_weights(bars, parameters):
    threshold = float(parameters.get("factor_threshold", 0.0))
    position_size = min(max(float(parameters.get("position_size", 1.0)), 0.0), 1.0)
    weights = []
    for bar in bars:
        factor_rows = (bar.get("datasets") or {{}}).get("factor_values") or {{}}
        factor_row = factor_rows.get({factor_literal}) or {{}}
        value = factor_row.get(FACTOR_VALUE_FIELD)
        weights.append(position_size if value is not None and float(value) > threshold else 0.0)
    return weights
'''
