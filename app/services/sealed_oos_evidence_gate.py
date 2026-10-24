"""Immutable evidence manifests for sealed out-of-sample research."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def build_sealed_oos_manifest(
    *,
    strategy_id: str,
    strategy_version: str,
    source_sha256: str,
    parameters: Mapping[str, Any],
    dataset_bindings: Sequence[Mapping[str, Any]],
    factor_bindings: Sequence[Mapping[str, Any]],
    universe_snapshot_id: str,
    development_window: Mapping[str, str],
    oos_window: Mapping[str, str],
    primary_metrics: Sequence[str],
    decision_thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a deterministic freeze manifest before any OOS result is viewed."""

    payload = {
        "manifest_version": "sealed-oos-evidence-v1",
        "strategy_id": str(strategy_id),
        "strategy_version": str(strategy_version),
        "source_sha256": str(source_sha256),
        "parameters": dict(parameters),
        "dataset_bindings": [dict(item) for item in dataset_bindings],
        "factor_bindings": [dict(item) for item in factor_bindings],
        "universe_snapshot_id": str(universe_snapshot_id),
        "development_window": _normalize_window(development_window, "development_window"),
        "oos_window": _normalize_window(oos_window, "oos_window"),
        "primary_metrics": [str(item) for item in primary_metrics],
        "decision_thresholds": dict(decision_thresholds),
        "oos_status": "sealed_not_viewed",
    }
    issues = _validate_freeze_payload(payload)
    if issues:
        raise ValueError(json.dumps(issues, ensure_ascii=False, separators=(",", ":")))
    digest = _digest(payload)
    return {**payload, "freeze_id": f"oos-freeze-{digest[:20]}", "freeze_sha256": digest}


def verify_frozen_inputs(
    manifest: Mapping[str, Any],
    *,
    source_sha256: str,
    parameters: Mapping[str, Any],
    dataset_bindings: Sequence[Mapping[str, Any]],
    factor_bindings: Sequence[Mapping[str, Any]],
    universe_snapshot_id: str,
) -> dict[str, Any]:
    """Fail before OOS execution when any frozen research input changed."""

    mismatches: list[dict[str, str]] = []
    comparisons = {
        "source_sha256": (str(manifest.get("source_sha256") or ""), str(source_sha256)),
        "parameters": (_canonical(manifest.get("parameters") or {}), _canonical(dict(parameters))),
        "dataset_bindings": (
            _canonical(manifest.get("dataset_bindings") or []),
            _canonical([dict(item) for item in dataset_bindings]),
        ),
        "factor_bindings": (
            _canonical(manifest.get("factor_bindings") or []),
            _canonical([dict(item) for item in factor_bindings]),
        ),
        "universe_snapshot_id": (
            str(manifest.get("universe_snapshot_id") or ""),
            str(universe_snapshot_id),
        ),
    }
    for field, (expected, actual) in comparisons.items():
        if expected != actual:
            mismatches.append({"code": "frozen_input_changed", "field": field})
    return {
        "ok": not mismatches,
        "status": "sealed_inputs_match" if not mismatches else "oos_invalidated",
        "freeze_id": manifest.get("freeze_id"),
        "issues": mismatches,
    }


def build_oos_view_record(
    manifest: Mapping[str, Any],
    *,
    result_sha256: str,
    viewed_at: str,
) -> dict[str, Any]:
    """Create the audit record that permanently marks an OOS window as viewed."""

    if str(manifest.get("oos_status") or "") != "sealed_not_viewed":
        raise ValueError("OOS manifest is not sealed_not_viewed")
    if not str(result_sha256).strip() or not str(viewed_at).strip():
        raise ValueError("result_sha256 and viewed_at are required")
    record = {
        "record_version": "sealed-oos-view-v1",
        "freeze_id": str(manifest.get("freeze_id") or ""),
        "freeze_sha256": str(manifest.get("freeze_sha256") or ""),
        "result_sha256": str(result_sha256),
        "viewed_at": str(viewed_at),
        "status": "viewed_no_longer_unseen",
        "rule": "any subsequent input change converts this window to development evidence",
    }
    return {**record, "view_record_sha256": _digest(record)}


def _validate_freeze_payload(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for field in ("strategy_id", "strategy_version", "source_sha256", "universe_snapshot_id"):
        if not str(payload.get(field) or "").strip():
            issues.append({"code": "freeze_field_required", "field": field})
    development = dict(payload["development_window"])
    oos = dict(payload["oos_window"])
    if development["end_date"] >= oos["start_date"]:
        issues.append({"code": "development_oos_windows_overlap", "field": "oos_window"})
    if not payload.get("primary_metrics"):
        issues.append({"code": "primary_metrics_required", "field": "primary_metrics"})
    if not payload.get("decision_thresholds"):
        issues.append({"code": "decision_thresholds_required", "field": "decision_thresholds"})
    for binding in payload.get("dataset_bindings") or []:
        if not binding.get("dataset_id") or not binding.get("version_id") or not binding.get("quality_report_id"):
            issues.append({"code": "dataset_exact_binding_required", "field": str(binding.get("dataset_id") or "")})
    for binding in payload.get("factor_bindings") or []:
        if not binding.get("factor_id") or not binding.get("artifact_id"):
            issues.append({"code": "factor_exact_binding_required", "field": str(binding.get("factor_id") or "")})
    return issues


def _normalize_window(value: Mapping[str, str], name: str) -> dict[str, str]:
    start = str(value.get("start_date") or "")[:10]
    end = str(value.get("end_date") or "")[:10]
    if len(start) != 10 or len(end) != 10 or start > end:
        raise ValueError(f"{name} must contain a valid ordered YYYY-MM-DD window")
    return {"start_date": start, "end_date": end}


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
