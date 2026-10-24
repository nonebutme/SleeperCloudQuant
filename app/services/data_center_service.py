"""Stage-86 data-center application service."""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from data_platform.a_share_sync_scheduler import AShareSyncScheduler
from data_platform.data_maintenance import DataMaintenance
from data_platform.storage.asset_governance_store import AssetGovernanceStore
from data_platform.quality_scan_engine import QualityScanEngine
from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from data_platform.storage.data_center_store import DataCenterStore
from scripts.apply_trading_status_semantic_remediation import (
    CONFIRMATION_PHRASE as TRADING_STATUS_BATCH_CONFIRMATION,
    MAX_AUTHORIZED_TOTAL_WRITES as TRADING_STATUS_MAX_AUTHORIZED_WRITES,
    TradingStatusDatabaseLease,
    TradingStatusDatabaseLeaseBusyError,
    acquire_trading_status_database_lease,
    clear_batch_pause,
    inspect_trading_status_database_lease,
    is_batch_pause_requested,
    mark_batch_interrupted,
    prepare_batch_remediation,
    request_batch_pause,
    run_batch_remediation,
)
from scripts.preview_trading_status_semantic_remediation import build_preview_report


TRADING_STATUS_CORRECTION_CONFIRMATION = "PUBLISH_TRADING_STATUS_CORRECTION"
TRADING_STATUS_ISSUE_RECONCILIATION_CONFIRMATION = (
    "RECONCILE_TRADING_STATUS_ISSUES"
)
TRADING_STATUS_CLOSURE_DETAILS_KEY = "trading_status_remediation_closure"
TRADING_STATUS_CLOSURE_RULE_VERSION = "stage2-status-remediation-closure-v1"
_TRADING_STATUS_CHECKPOINT_READ_ATTEMPTS = 20
_TRADING_STATUS_CHECKPOINT_READ_DELAY_SECONDS = 0.01


class DataCenterService:
    """Aggregate existing market governance behind the stage-86 API contract."""

    _trading_status_workers_lock = threading.Lock()
    _trading_status_workers: dict[str, tuple[str, threading.Thread]] = {}

    def __init__(
        self,
        store: DataCenterStore,
        scheduler: AShareSyncScheduler,
        governance_store: AShareGovernanceStore,
        sync_worker_launcher: Any | None = None,
        panorama_service: Any | None = None,
        trading_status_remediation_dir: str | Path | None = None,
    ) -> None:
        self.store = store
        self.scheduler = scheduler
        self.governance_store = governance_store
        self._sync_worker_launcher = sync_worker_launcher or self._launch_sync_worker
        self.panorama_service = panorama_service
        self._trading_status_remediation_dir = Path(
            trading_status_remediation_dir
            or Path(self.store.database_path).resolve().parent
            / "trading_status_remediation"
        ).resolve()
        self._sync_processes: dict[str, subprocess.Popen[str]] = {}
        self._sync_process_lock = threading.Lock()
        self._sync_previews: dict[str, dict[str, Any]] = {}
        self._sync_preview_lock = threading.Lock()
        self._reference_previews: dict[str, dict[str, Any]] = {}
        self._reference_preview_lock = threading.Lock()
        self._trading_status_repair_previews: dict[str, dict[str, Any]] = {}
        self._trading_status_repair_preview_lock = threading.Lock()
        self._trading_status_batch_lock = threading.Lock()
        self._trading_status_worker_errors: dict[str, str] = {}
        self._trading_status_pending_tasks: dict[str, dict[str, Any]] = {}
        self._trading_status_pending_lock = threading.Lock()
        self.quality_scan_engine = QualityScanEngine(store.database_path, scheduler)
        self._quality_scan_threads: dict[str, threading.Thread] = {}
        self._quality_scan_lock = threading.Lock()
        self.store.ensure_schema()
        self.asset_governance = AssetGovernanceStore(self.store.database_path)
        self.asset_governance.ensure_schema()
        self.recover_interrupted_trading_status_remediations()
        self.maintenance = DataMaintenance(scheduler)

    def start_data_update(self, *, target_trade_date: str) -> dict[str, Any]:
        for required_dataset in (
            "a_share_catalog", "trade_calendar", "index_daily", "a_share_daily",
        ):
            self._usable_routes(required_dataset)
        batch = self.maintenance.create(target_trade_date=target_trade_date)
        snapshot = self.store.freeze_route_snapshot("a_share_daily", task_id=batch["batch_id"])
        with closing(self.maintenance._connect()) as connection, connection:
            request = dict(batch["request"])
            request["effective_config"] = dict(snapshot.get("effective_config") or {})
            connection.execute("UPDATE batches SET request_json=? WHERE batch_id=?",
                               (json.dumps(request), batch["batch_id"]))
        return self.maintenance.start(batch["batch_id"])

    def list_data_updates(self) -> list[dict[str, Any]]:
        self.maintenance.recover()
        return self.maintenance.list()

    def resume_data_update(self, batch_id: str) -> dict[str, Any]:
        for required_dataset in (
            "a_share_catalog", "trade_calendar", "index_daily", "a_share_daily",
        ):
            self._usable_routes(required_dataset)
        return self.maintenance.start(batch_id)

    def get_overview(self) -> dict[str, Any]:
        overview = self.store.get_overview()
        overview["scheduler"] = self.scheduler.get_status()
        overview["governance"] = self.governance_store.get_overview()
        overview["health"] = self._health(overview)
        overview["research_ready"] = bool(
            overview.get("default_version") and overview["health"] == "healthy"
        )
        overview["usage_boundary"] = "noncommercial_local_research"
        return overview
    def sync_index_component_snapshots(
        self,
        index_codes: Sequence[str],
        *,
        operator: str = "local-user",
        authorization_confirmed: bool = False,
        authorization_reference: str = "",
    ) -> dict[str, Any]:
        if not authorization_confirmed or not str(authorization_reference or "").strip():
            raise ValueError(
                "index component synchronization requires explicit data-use authorization "
                "and a non-empty authorization reference"
            )
        allowed = {"000300.XSHG", "000905.XSHG", "000852.XSHG"}
        requested = list(dict.fromkeys(str(item or "").strip().upper() for item in index_codes))
        if not requested:
            requested = sorted(allowed)
        invalid = [item for item in requested if item not in allowed]
        if invalid:
            raise ValueError(f"unsupported controlled index codes: {','.join(invalid)}")
        provider = self.scheduler.governance_provider
        if provider is None or not hasattr(provider, "fetch_index_component_snapshot"):
            raise RuntimeError("configured provider does not expose index component snapshots")
        results = []
        for qualified_code in requested:
            snapshot = dict(
                provider.fetch_index_component_snapshot(
                    index_code=qualified_code.split(".", 1)[0]
                )
            )
            result = self.store.replace_index_component_snapshot(
                index_code=qualified_code,
                as_of_date=str(snapshot["as_of_date"]),
                rows=list(snapshot["rows"]),
                source=str(snapshot["source"]),
                source_version=str(snapshot["source_version"]),
                observed_at=str(snapshot["observed_at"]),
                evidence={
                    "operator": operator or "local-user",
                    "authorization_confirmed": True,
                    "authorization_reference": str(authorization_reference).strip(),
                    "upstream_index_code": snapshot.get("index_code"),
                    "license_scope": "noncommercial_local_research_unverified",
                    "historical_claim": False,
                },
            )
            results.append(result)
        return {
            "status": "ready",
            "snapshot_count": len(results),
            "items": results,
            "coverage": self.store.index_component_coverage(),
            "semantic_boundary": "latest observed snapshots only; no pre-snapshot history is inferred",
        }

    def index_component_coverage(self) -> dict[str, Any]:
        return self.store.index_component_coverage()

    def latest_sync_target(self) -> dict[str, Any]:
        return self.scheduler.latest_sync_target()

    def preview_reference_refresh(self, *, target_trade_date: str) -> dict[str, Any]:
        target = date.fromisoformat(str(target_trade_date)).isoformat()
        if target > date.today().isoformat():
            raise ValueError("reference refresh target cannot be in the future")
        current = self.scheduler.reference_data_status(target_date=target)
        token = f"dcrp-{uuid.uuid4().hex}"
        now = time.monotonic()
        with self._reference_preview_lock:
            self._reference_previews[token] = {
                "created_monotonic": now, "target_trade_date": target,
            }
            self._reference_previews = {
                key: value for key, value in self._reference_previews.items()
                if now - float(value["created_monotonic"]) <= 900
            }
        return {
            "status": "previewed",
            "writes": 0,
            "target_trade_date": target,
            "preview_token": token,
            "preview_expires_in_seconds": 900,
            "current": current,
            "planned_actions": {
                "refresh_security_catalog": str(
                    current.get("catalog_updated_at") or ""
                )[:10] < target,
                "refresh_trade_calendar_through": target,
                "refresh_csi300_through_latest_open_day": True,
                "refresh_target_suspensions": "performed_when_each_price_task_starts",
            },
            "release_gate": {
                "calendar_required": True,
                "csi300_benchmark_required": True,
            },
        }

    def refresh_reference_data(
        self, *, target_trade_date: str, preview_token: str,
    ) -> dict[str, Any]:
        with closing(self.store._connect(read_only=True)) as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='maintenance_commits'").fetchone():
                raise ValueError("已启用统一维护，不能独立写入参考数据；请使用“更新数据”")
        target = date.fromisoformat(str(target_trade_date)).isoformat()
        with self._reference_preview_lock:
            preview = self._reference_previews.pop(str(preview_token), None)
        if preview is None or time.monotonic() - float(
            preview["created_monotonic"]
        ) > 900:
            raise ValueError("a current reference refresh preview is required")
        if str(preview["target_trade_date"]) != target:
            raise ValueError("reference refresh target changed after preview")
        before = self.scheduler.reference_data_status(target_date=target)
        refreshed = self.scheduler.refresh_reference_data(end_date=target)
        after = self.scheduler.reference_data_status(target_date=target)
        if after.get("status") != "ready":
            raise RuntimeError(
                "reference refresh did not satisfy calendar and benchmark release gates"
            )
        return {
            "status": "completed",
            "target_trade_date": target,
            "writes": {
                "catalog_count": int(refreshed.get("catalog_count") or 0),
                "calendar_rows": int(refreshed.get("calendar_rows") or 0),
                "index_rows": int(refreshed.get("index_rows") or 0),
            },
            "before": before,
            "after": after,
            "refresh_result": refreshed,
            "next_action": "create serial raw, qfq and hfq incremental price tasks",
        }


    def list_sources(self) -> list[dict[str, Any]]:
        return self.store.list_sources()

    def get_source(self, source_id: str) -> dict[str, Any]:
        return self.store.get_source(source_id)

    def update_source(self, source_id: str, update: Mapping[str, Any]) -> dict[str, Any]:
        return self.store.update_source(source_id, update)

    def test_source(self, source_id: str, *, live: bool = False) -> dict[str, Any]:
        source = self.store.get_source(source_id)
        routes = [
            item for item in self.store.list_routes()
            if item.get("source_id") == source_id
        ]
        capabilities = list(source.get("capabilities") or [])
        results: list[dict[str, Any]] = []
        if not capabilities:
            results.append(self._record_probe_policy(
                source=source,
                dataset_id="source_registry",
                endpoint_id=str(source.get("provider_type") or source_id),
                error_code="NO_TESTABLE_CAPABILITY",
                evidence={"capability_count": 0},
            ))
        for capability in capabilities:
            route = next((
                item for item in routes
                if item["dataset"] == capability["dataset_id"]
                and item["endpoint"] == capability["endpoint_id"]
            ), None)
            if source.get("verification_status") != "verified":
                results.append(self._record_probe_policy(
                    source=source, capability=capability, route=route,
                    error_code="SOURCE_NOT_VERIFIED",
                    evidence={"verification_status": source.get("verification_status")},
                ))
                continue
            if not source.get("enabled"):
                results.append(self._record_probe_policy(
                    source=source, capability=capability, route=route,
                    error_code="SOURCE_DISABLED",
                ))
                continue
            if not capability.get("enabled"):
                results.append(self._record_probe_policy(
                    source=source, capability=capability, route=route,
                    error_code="CAPABILITY_DISABLED",
                    evidence={"verification_status": capability.get("verification_status")},
                ))
                continue
            if route is None:
                results.append(self._record_probe_policy(
                    source=source, capability=capability,
                    error_code="ROUTE_NOT_INSTALLED",
                ))
                continue
            results.append(self.test_route(str(route["route_id"]), live=live))
        active_results = [
            item for item in results
            if str(item.get("error_code") or "") not in {
                "SOURCE_NOT_VERIFIED", "SOURCE_DISABLED", "CAPABILITY_DISABLED",
                "NO_TESTABLE_CAPABILITY",
            }
        ]
        active_statuses = {str(item["status"]) for item in active_results}
        structural_errors = {
            str(item.get("error_code") or "") for item in active_results
        } & {"ROUTE_NOT_INSTALLED", "ROUTE_DISABLED", "ROUTE_NOT_REGISTERED"}
        if source.get("verification_status") != "verified" or not source.get("enabled"):
            aggregate_status = "policy_blocked"
        elif structural_errors or "failed" in active_statuses:
            aggregate_status = "needs_attention"
        elif active_statuses and active_statuses <= {"passed", "ready"}:
            aggregate_status = "passed"
        else:
            aggregate_status = "policy_blocked"
        return {
            "source_id": source_id,
            "status": aggregate_status,
            "writes": 0,
            "tested_count": len(results),
            "active_tested_count": len(active_results),
            "skipped_count": len(results) - len(active_results),
            "items": results,
            "message": "连接测试不会启用数据源，也不会写入业务数据。",
        }

    def _record_probe_policy(
        self,
        *,
        source: Mapping[str, Any],
        error_code: str,
        capability: Mapping[str, Any] | None = None,
        route: Mapping[str, Any] | None = None,
        dataset_id: str = "",
        endpoint_id: str = "",
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        capability = capability or {}
        route = route or {}
        return self.store.record_source_probe({
            "source_id": source["source_id"],
            "route_id": route.get("route_id"),
            "dataset_id": dataset_id or capability.get("dataset_id") or route.get("dataset") or "source_registry",
            "endpoint_id": endpoint_id or capability.get("endpoint_id") or route.get("endpoint") or source["source_id"],
            "mode": "contract_only",
            "status": "policy_blocked",
            "error_code": error_code,
            "error_class": "policy",
            "retryable": False,
            "evidence": {
                "writes": 0,
                "source_enabled": bool(source.get("enabled")),
                "route_enabled": bool(route.get("enabled")) if route else None,
                **dict(evidence or {}),
            },
        })

    def list_source_probes(
        self, *, source_id: str = "", route_id: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.store.list_source_probes(
            source_id=source_id, route_id=route_id, limit=limit,
        )

    def list_datasets(self) -> list[dict[str, Any]]:
        datasets = self.store.list_datasets()
        routes = self.store.list_routes()
        sources = {source["source_id"]: source for source in self.store.list_sources()}
        for dataset in datasets:
            matching = [
                route for route in routes
                if route.get("dataset") == dataset.get("dataset_id")
            ]
            usable = [
                route for route in matching
                if self.store._route_is_usable(route, sources)
            ]
            dataset["route_count"] = len(matching)
            dataset["enabled_route_count"] = sum(
                bool(route.get("enabled")) for route in matching
            )
            dataset["usable_route_count"] = len(usable)
            missing_partitions = self.store.missing_route_partitions(
                str(dataset["dataset_id"]), usable,
            )
            dataset["missing_route_partitions"] = missing_partitions
            if dataset.get("availability_status") == "disabled":
                dataset["route_status"] = "disabled"
            elif not dataset.get("route_required"):
                dataset["route_status"] = "not_required"
            elif usable and not missing_partitions:
                dataset["route_status"] = "ready"
            elif matching:
                dataset["route_status"] = "blocked"
            else:
                dataset["route_status"] = "missing"
        return datasets

    def list_routes(self) -> list[dict[str, Any]]:
        return self.store.list_routes()

    def update_routes(self, routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return self.store.update_routes(routes)

    def test_route(self, route_id: str, *, live: bool = False) -> dict[str, Any]:
        route = self.store.get_route(route_id)
        source = self.store.get_source(str(route.get("source_id") or route["provider"]))
        result: dict[str, Any] = {
            "source_id": source["source_id"],
            "route_id": route_id,
            "dataset": route["dataset"],
            "endpoint": route["endpoint"],
            "mode": "contract_only",
            "writes": 0,
            "status": "ready",
        }
        capability = next((
            item for item in source.get("capabilities") or []
            if item.get("dataset_id") == route.get("dataset")
            and item.get("endpoint_id") == route.get("endpoint")
        ), None)
        if source.get("verification_status") != "verified":
            return self._record_probe_policy(
                source=source, route=route, error_code="SOURCE_NOT_VERIFIED",
                evidence={"verification_status": source.get("verification_status")},
            )
        if not source.get("enabled"):
            return self._record_probe_policy(
                source=source, route=route, error_code="SOURCE_DISABLED",
            )
        if capability is None:
            return self._record_probe_policy(
                source=source, route=route, error_code="ROUTE_NOT_REGISTERED",
            )
        if not capability.get("enabled"):
            return self._record_probe_policy(
                source=source, capability=capability, route=route,
                error_code="CAPABILITY_DISABLED",
                evidence={"verification_status": capability.get("verification_status")},
            )
        if not route.get("enabled"):
            return self._record_probe_policy(
                source=source, capability=capability, route=route,
                error_code="ROUTE_DISABLED",
            )
        if not live:
            result["message"] = "route contract validated; set live=true for a lightweight upstream read"
            return self.store.record_source_probe({
                **result,
                "dataset_id": route["dataset"],
                "endpoint_id": route["endpoint"],
                "sample_rows": 0,
                "evidence": {"writes": 0, "route_enabled": route["enabled"]},
            })
        whitelist = set(source.get("allowed_hosts") or [])
        required = set(self.store.effective_route_config(
            str(route["dataset"]), routes=[route],
            require_complete_route_coverage=False,
        ).get("required_hosts") or [])
        if required and not required.issubset(whitelist):
            return self.store.record_source_probe({
                **result,
                "dataset_id": route["dataset"],
                "endpoint_id": route["endpoint"],
                "mode": "live_read",
                "status": "policy_blocked",
                "error_code": "HOST_NOT_ALLOWED",
                "error_class": "policy",
                "retryable": False,
                "evidence": {
                    "writes": 0,
                    "required_hosts": sorted(required),
                    "allowed_hosts": sorted(whitelist),
                },
            })
        started = time.monotonic()
        max_attempts = max(1, min(3, int(route.get("retry_count") or 0) + 1))
        attempt = 0
        previous_errors: list[str] = []
        while True:
            attempt += 1
            try:
                sample = self._live_probe(route)
                break
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                error_code, error_class, retryable = self._classify_probe_error(error)
                previous_errors.append(message)
                if not retryable or attempt >= max_attempts:
                    latency = int((time.monotonic() - started) * 1000)
                    self.store.record_route_probe(
                        route_id, succeeded=False, latency_ms=latency, error=message,
                    )
                    return self.store.record_source_probe({
                        **result,
                        "dataset_id": route["dataset"],
                        "endpoint_id": route["endpoint"],
                        "status": "failed",
                        "mode": "live_read",
                        "latency_ms": latency,
                        "error_code": error_code,
                        "error_class": error_class,
                        "retryable": retryable,
                        "evidence": {
                            "writes": 0,
                            "message": message,
                            "attempts": attempt,
                            "previous_errors": previous_errors[:-1],
                        },
                    })
                backoff = min(5.0, max(0.0, float(route.get("backoff_seconds") or 0)) * attempt)
                if backoff:
                    time.sleep(backoff)
        latency = int((time.monotonic() - started) * 1000)
        self.store.record_route_probe(route_id, succeeded=True, latency_ms=latency)
        return self.store.record_source_probe({
            **result,
            "dataset_id": route["dataset"],
            "endpoint_id": route["endpoint"],
            "status": "passed",
            "mode": "live_read",
            "latency_ms": latency,
            "sample_rows": int(sample.get("row_count") or 0),
            "evidence": {
                "writes": 0,
                "sample": sample,
                "attempts": attempt,
                "previous_errors": previous_errors,
            },
        })

    def preview_sync(
        self, *, dataset: str = "a_share_daily", target_trade_date: str,
        start_trade_date: str = "",
        symbols: Sequence[str], all_current: bool, adjustments: Sequence[str],
        mode: str, selected_shards: Sequence[str] = (),
    ) -> dict[str, Any]:
        catalog = {item["dataset_id"]: item for item in self.store.list_datasets()}
        definition = catalog.get(dataset)
        if definition is None or not definition["sync_enabled"]:
            raise ValueError(f"dataset is not enabled for manual sync: {dataset}")
        if mode == "full_rebuild":
            return {
                "status": "blocked", "risk": "high",
                "reason": "full rebuild requires a fresh backup, impact preview and separate confirmation",
                "writes": 0,
            }
        usable_routes = self._usable_routes(dataset)
        if dataset == "a_share_daily":
            preview = self.scheduler.preview_job(
                target_trade_date=target_trade_date, symbols=symbols or None,
                all_current=all_current, adjustments=adjustments,
                start_floor=start_trade_date or "2015-01-05",
                gap_scan=mode == "historical_gap",
            )
            shards = [dict(item) for item in preview.get("tasks", [])]
        else:
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            preview = self.panorama_service.preview_job(
                datasets=[dataset], target_trade_date=target_trade_date,
                start_trade_date=start_trade_date, mode=mode,
                symbols=symbols, selected_shards=selected_shards,
            )
            shards = [dict(item) for item in preview.get("shards", [])]
        request = self._sync_request_payload(
            dataset=dataset, target_trade_date=target_trade_date, symbols=symbols,
            start_trade_date=start_trade_date,
            all_current=all_current, adjustments=adjustments, mode=mode,
        )
        token = f"dcp-{uuid.uuid4().hex}"
        available = {
            str(item.get("shard_id")) for item in shards if item.get("shard_id")
        }
        with self._sync_preview_lock:
            self._sync_previews[token] = {
                "created_monotonic": time.monotonic(), "request": request,
                "available_shards": available,
            }
            self._sync_previews = {
                key: value for key, value in self._sync_previews.items()
                if time.monotonic() - float(value["created_monotonic"]) <= 900
            }
        return {
            **preview, "status": "previewed", "mode": mode, "writes": 0,
            "dataset_id": dataset, "dataset_name": definition["display_name"],
            "config_fields": definition["config_fields"], "preview_token": token,
            "preview_expires_in_seconds": 900, "shards": shards,
            "route_summary": [
                {"route_id": row["route_id"], "source_id": row.get("source_id"),
                 "priority": row["priority"], "fallback_policy": row.get("fallback_policy"),
                 "partition_key": row.get("partition_key") or ""}
                for row in usable_routes
            ],
        }

    def create_sync_task(
        self, *, dataset: str = "a_share_daily", target_trade_date: str,
        start_trade_date: str = "",
        symbols: Sequence[str], all_current: bool, adjustments: Sequence[str],
        run_now: bool, mode: str, preview_token: str = "",
        selected_shards: Sequence[str] = (),
    ) -> dict[str, Any]:
        request = self._sync_request_payload(
            dataset=dataset, target_trade_date=target_trade_date, symbols=symbols,
            start_trade_date=start_trade_date,
            all_current=all_current, adjustments=adjustments, mode=mode,
        )
        with self._sync_preview_lock:
            preview = self._sync_previews.pop(str(preview_token), None)
        if preview is None or time.monotonic() - float(preview["created_monotonic"]) > 900:
            raise ValueError("a current sync preview is required before task creation")
        if preview["request"] != request:
            raise ValueError("sync parameters changed after preview; generate a new preview")
        chosen = {str(item) for item in selected_shards if str(item)}
        available = set(preview["available_shards"])
        if chosen and available and not chosen.issubset(available):
            raise ValueError("selected shard is not part of the frozen preview")
        if mode not in {"incremental", "historical_gap"}:
            raise ValueError("only incremental and historical-gap sync are enabled")
        if dataset == "a_share_daily":
            effective_config = self.store.effective_route_config(dataset)
            job = self.scheduler.create_job(
                target_trade_date=target_trade_date, symbols=symbols or None,
                all_current=all_current, adjustments=adjustments, mode="data_center",
                selected_shards=selected_shards,
                start_floor=start_trade_date or "2015-01-05",
                gap_scan=mode == "historical_gap",
                effective_config=effective_config,
            )
        else:
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            job = self.panorama_service.create_job(
                datasets=[dataset], target_trade_date=target_trade_date,
                start_trade_date=start_trade_date, mode=mode,
                symbols=symbols, selected_shards=selected_shards,
            )
        task_id = str(job["job_id"])
        snapshot = self.store.freeze_route_snapshot(dataset, task_id=task_id)
        result = {**job, "dataset_id": dataset, "route_snapshot_id": snapshot["snapshot_id"]}
        return self.run_sync_task(task_id) if run_now else result

    def run_sync_task(self, task_id: str) -> dict[str, Any]:
        if task_id.startswith("panorama-sync-"):
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            snapshot = self.store.get_route_snapshot(task_id=task_id)
            if snapshot is None:
                raise ValueError("panorama sync task is missing its frozen route snapshot")
            return self.panorama_service.start_job(
                task_id, routes=list(snapshot.get("routes") or []),
            )
        job = self.scheduler.get_job(task_id)
        if job.get("status") == "not_found":
            return job
        if job.get("status") in {"published", "completed_noop"}:
            return job
        if job.get("status") not in {
            "queued", "partial_failure", "failed", "interrupted"
        }:
            raise RuntimeError(
                f"job is not runnable from status={job.get('status')}"
            )
        launch = self._sync_worker_launcher(task_id)
        return {
            **job,
            "execution": {
                "mode": "background_process",
                "status": "dispatched",
                **dict(launch or {}),
            },
        }

    def list_sync_tasks(self) -> list[dict[str, Any]]:
        jobs = list(self.scheduler.list_jobs(limit=100))
        if self.panorama_service is not None:
            jobs.extend(self.panorama_service.list_jobs(limit=100))
        return sorted(jobs, key=lambda row: str(row.get("created_at") or ""), reverse=True)[:100]

    def delete_sync_task(self, task_id: str) -> dict[str, Any]:
        """Delete inactive task metadata while preserving synchronized data and governance evidence."""

        if task_id.startswith("panorama-sync-"):
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            return self.panorama_service.delete_job(task_id)
        with self._sync_process_lock:
            process = self._sync_processes.get(task_id)
            if process is not None and process.poll() is None:
                raise ValueError("running sync task cannot be deleted")
        result = self.scheduler.delete_job(task_id)
        with self._sync_process_lock:
            self._sync_processes.pop(task_id, None)
        return result
    def stop_sync_task(self, task_id: str) -> dict[str, Any]:
        if task_id.startswith("panorama-sync-"):
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            return self.panorama_service.stop_job(task_id)
        return self.scheduler.stop_job(task_id)

    def retry_failed_sync_task(self, task_id: str, *, run_now: bool = False) -> dict[str, Any]:
        if task_id.startswith("panorama-sync-"):
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            snapshot = self.store.get_route_snapshot(task_id=task_id)
            if snapshot is None:
                raise ValueError("panorama sync task is missing its frozen route snapshot")
            return self.panorama_service.retry_job(
                task_id, run_now=run_now,
                routes=list(snapshot.get("routes") or []),
            )
        job = self.scheduler.retry_quarantined(task_id)
        return self.run_sync_task(task_id) if run_now else job

    def _usable_routes(self, dataset_id: str) -> list[dict[str, Any]]:
        sources = {source["source_id"]: source for source in self.store.list_sources()}
        routes = [
            route for route in self.store.list_routes()
            if route["dataset"] == dataset_id
            and self.store._route_is_usable(route, sources)
        ]
        if not routes:
            raise ValueError(f"dataset has no enabled verified route: {dataset_id}")
        self.store.assert_route_coverage(dataset_id, routes)
        return routes

    @staticmethod
    def _sync_request_payload(
        *, dataset: str, target_trade_date: str, start_trade_date: str,
        symbols: Sequence[str],
        all_current: bool, adjustments: Sequence[str], mode: str,
    ) -> dict[str, Any]:
        return {
            "dataset": str(dataset), "target_trade_date": str(target_trade_date)[:10],
            "start_trade_date": str(start_trade_date)[:10],
            "symbols": sorted(str(item).strip() for item in symbols if str(item).strip()),
            "all_current": bool(all_current),
            "adjustments": sorted(str(item) for item in adjustments), "mode": str(mode),
        }

    def get_sync_task(self, task_id: str) -> dict[str, Any]:
        if task_id.startswith("panorama-sync-"):
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            job = self.panorama_service.get_job(task_id)
            snapshot = self.store.get_route_snapshot(task_id=task_id)
            release = job.get("global_index_release") or {}
            actual_routes = [
                item.get("quality", {}).get("runtime_config", {})
                for item in release.get("items", [])
                if item.get("quality", {}).get("runtime_config")
            ]
            return {
                **job,
                "route_snapshot": snapshot,
                "effective_config": (
                    snapshot.get("effective_config", {}) if snapshot else {}
                ),
                "actual_config": (
                    {"routes": actual_routes} if actual_routes else {}
                ),
            }
        job = self.scheduler.get_job(task_id, include_items=False)
        snapshot = self.store.get_route_snapshot(task_id=task_id)
        return {**job, "route_snapshot": snapshot}

    def get_sync_task_items(self, task_id: str) -> list[dict[str, Any]]:
        if task_id.startswith("panorama-sync-"):
            if self.panorama_service is None:
                raise RuntimeError("market panorama sync service is not configured")
            return self.panorama_service.get_job_items(task_id)
        task = self.scheduler.get_job(task_id, include_items=True)
        return list(task.get("items") or [])

    def _launch_sync_worker(self, task_id: str) -> dict[str, Any]:
        with self._sync_process_lock:
            existing = self._sync_processes.get(task_id)
            if existing is not None and existing.poll() is None:
                return {"pid": existing.pid, "already_running": True}

            project_root = Path(__file__).resolve().parents[2]
            runtime_dir = project_root / "var" / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = runtime_dir / f"data-center-sync-{task_id}.out.log"
            stderr_path = runtime_dir / f"data-center-sync-{task_id}.err.log"
            stdout_file = stdout_path.open("a", encoding="utf-8")
            stderr_file = stderr_path.open("a", encoding="utf-8")
            creationflags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                if sys.platform == "win32"
                else 0
            )
            try:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(project_root / "scripts" / "run_data_center_sync_job.py"),
                        "--database",
                        str(self.scheduler.database_path.resolve()),
                        "--job-id",
                        task_id,
                    ],
                    cwd=project_root,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    text=True,
                    creationflags=creationflags,
                )
            except Exception:
                stdout_file.close()
                stderr_file.close()
                raise
            self._sync_processes[task_id] = process
            threading.Thread(
                target=self._monitor_sync_worker,
                args=(task_id, process, stdout_file, stderr_file),
                daemon=True,
                name=f"data-center-sync-monitor-{task_id}",
            ).start()
            return {
                "pid": process.pid,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }

    def _monitor_sync_worker(
        self,
        task_id: str,
        process: subprocess.Popen[str],
        stdout_file: Any,
        stderr_file: Any,
    ) -> None:
        return_code = process.wait()
        stdout_file.close()
        stderr_file.close()
        with self._sync_process_lock:
            if self._sync_processes.get(task_id) is process:
                self._sync_processes.pop(task_id, None)
        if return_code != 0:
            self.scheduler.mark_job_interrupted(
                task_id,
                error=f"sync_worker_exited_abnormally:{return_code}",
            )

    def list_quality_rules(self) -> list[dict[str, str]]:
        return self.quality_scan_engine.list_rules()

    def create_quality_scan(
        self, *, dataset: str, date_from: str, date_to: str, scope: str,
        symbols: Sequence[str], adjustments: Sequence[str], rules: Sequence[str],
        run_now: bool = False,
    ) -> dict[str, Any]:
        scan = self.quality_scan_engine.create_scan(
            dataset=dataset, date_from=date_from, date_to=date_to, scope=scope,
            symbols=symbols, adjustments=adjustments, rules=rules,
        )
        return self.run_quality_scan(str(scan["scan_id"])) if run_now else scan

    def list_quality_scans(self) -> list[dict[str, Any]]:
        return self.quality_scan_engine.list_scans()

    def get_quality_scan(self, scan_id: str) -> dict[str, Any]:
        return self.quality_scan_engine.get_scan(scan_id)

    def delete_quality_scan(self, scan_id: str) -> dict[str, Any]:
        with self._quality_scan_lock:
            worker = self._quality_scan_threads.get(scan_id)
            if worker is not None and worker.is_alive():
                raise ValueError("running quality scan cannot be deleted; stop it first")
        return self.quality_scan_engine.delete_scan(scan_id)

    def run_quality_scan(self, scan_id: str) -> dict[str, Any]:
        scan = self.quality_scan_engine.get_scan(scan_id)
        if scan["status"] in {"passed", "issues_found"}:
            return scan
        if scan["status"] not in {"queued", "failed", "running"}:
            raise ValueError(f"quality scan is not runnable from status={scan['status']}")
        with self._quality_scan_lock:
            existing = self._quality_scan_threads.get(scan_id)
            if existing is not None and existing.is_alive():
                return {**scan, "execution": {"status": "already_running", "mode": "background_thread"}}
            if scan["status"] == "running":
                raise RuntimeError("quality scan is marked running but has no local worker")
            worker = threading.Thread(
                target=self._run_quality_scan_worker,
                args=(scan_id,), daemon=True,
                name=f"data-quality-scan-{scan_id}",
            )
            self._quality_scan_threads[scan_id] = worker
            worker.start()
        return {**scan, "execution": {"status": "dispatched", "mode": "background_thread"}}

    def pause_quality_scan(self, scan_id: str) -> dict[str, Any]:
        return self.quality_scan_engine.request_pause(scan_id)

    def resume_quality_scan(self, scan_id: str) -> dict[str, Any]:
        return self.quality_scan_engine.resume(scan_id)

    def stop_quality_scan(self, scan_id: str) -> dict[str, Any]:
        return self.quality_scan_engine.request_stop(scan_id)

    def _run_quality_scan_worker(self, scan_id: str) -> None:
        try:
            self.quality_scan_engine.run_scan(scan_id)
        except Exception:
            pass
        finally:
            with self._quality_scan_lock:
                self._quality_scan_threads.pop(scan_id, None)

    def recheck_quality_scan(self, scan_id: str) -> dict[str, Any]:
        scan = self.quality_scan_engine.recheck(scan_id)
        return self.run_quality_scan(str(scan["scan_id"]))
    def list_quality_issues(
        self, *, status: str = "", severity: str = "", dataset: str = "",
        source_task_id: str = "", source: str = "", symbol: str = "", rule_id: str = "",
        date_from: str = "", date_to: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.store.list_issues(
            status=status, severity=severity, dataset=dataset,
            source_task_id=source_task_id, source=source, symbol=symbol, rule_id=rule_id,
            date_from=date_from, date_to=date_to, limit=limit,
        )

    def summarize_quality_issues(
        self, *, severity: str = "", dataset: str = "", source_task_id: str = "", source: str = "",
        symbol: str = "", rule_id: str = "", date_from: str = "", date_to: str = "",
    ) -> dict[str, Any]:
        return self.store.summarize_issues(
            severity=severity, dataset=dataset, source_task_id=source_task_id, source=source,
            symbol=symbol, rule_id=rule_id, date_from=date_from, date_to=date_to,
        )
    def quality_filter_options(self) -> dict[str, Any]:
        return self.store.quality_facets()


    def get_quality_issue(self, issue_id: str) -> dict[str, Any]:
        return self.store.get_issue(issue_id)

    def get_quality_issue_history(self, issue_id: str) -> dict[str, Any]:
        history = self.store.get_issue_history(issue_id)
        reconciled: list[dict[str, Any]] = []
        for refetch in history["refetches"]:
            task_id = str(refetch["task_id"])
            try:
                job = self.get_sync_task(task_id)
            except (KeyError, RuntimeError):
                reconciled.append(refetch)
                continue
            job_status = str(job.get("status") or refetch["status"])
            if job_status == "not_found":
                reconciled.append(refetch)
                continue
            related = [
                item for item in self.store.list_issues(source_task_id=task_id, limit=500)
                if item["issue_id"] != issue_id
            ]
            updated = self.store.update_refetch(
                str(refetch["refetch_id"]), status=job_status,
                last_error=str(job.get("last_error") or ""),
                related_issue_id=str(related[0]["issue_id"]) if related else "",
            )
            updated["job"] = job
            reconciled.append(updated)
            if job_status in {"published", "completed_noop"}:
                for remediation in history.get("remediations") or []:
                    if (
                        str(remediation.get("executor_id") or "") == task_id
                        and str(remediation.get("status") or "") == "remediating"
                    ):
                        self.store.update_remediation(
                            str(remediation["remediation_id"]),
                            status="awaiting_recheck",
                            data_version_id=str(job.get("data_version_id") or ""),
                        )
            elif job_status in {"partial_failure", "failed", "interrupted", "stopped"}:
                for remediation in history.get("remediations") or []:
                    if (
                        str(remediation.get("executor_id") or "") == task_id
                        and str(remediation.get("status") or "") == "remediating"
                    ):
                        self.store.update_remediation(
                            str(remediation["remediation_id"]),
                            status="failed",
                            last_error=str(job.get("last_error") or job_status),
                        )
        history["refetches"] = reconciled
        return self.store.get_issue_history(issue_id)

    def publish_correction_overlay(self, issue_id: str) -> dict[str, Any]:
        from data_platform.maintenance_transaction import maintenance_transaction
        with maintenance_transaction(self.store.database_path):
            return self._complete_overlay_repair(issue_id)

    def _publish_correction_overlay(self, issue_id: str) -> dict[str, Any]:
        readiness = self.store.release_readiness(exempt_issue_id=issue_id)
        if readiness["status"] != "ready":
            raise ValueError("correction overlay cannot be published while other release checks fail")
        versions = self.store.list_versions()
        base = versions.get("latest_published_version") or versions.get("default_version")
        if not base:
            raise ValueError("correction overlay requires an existing published base version")
        base_version = self.governance_store.fetch_data_version(str(base["data_version_id"]))
        members = []
        for raw in base_version.get("members") or []:
            member = dict(raw)
            member["details"] = json.loads(str(member.pop("details_json", "{}") or "{}"))
            member["content_hash"] = f"{member.get('content_hash')}:overlay:{issue_id}"
            member["sync_run_ref"] = str(member.get("sync_run_ref") or "") or None
            members.append(member)
        published = self.governance_store.publish_data_version(
            as_of_trade_date=str(base_version["as_of_trade_date"]),
            quality_report_id=str(base_version["quality_report_id"]),
            members=members,
            notes=f"stage91 correction overlay for {issue_id}",
        )
        history = self.store.mark_overlay_published(
            issue_id, data_version_id=str(published["data_version_id"]),
        )
        return {
            "status": "awaiting_recheck",
            "issue_id": issue_id,
            "data_version_id": published["data_version_id"],
            "history": history,
        }

    def disposition_quality_issue(
        self, issue_id: str, *, action: str, reason: str, operator: str,
        before: Mapping[str, Any] | None, after: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if action == "correct":
            from data_platform.maintenance_transaction import maintenance_transaction
            with maintenance_transaction(self.store.database_path) as connection:
                allowed = {'open','high','low','close','volume','amount','amplitude','change_pct','change_amount','turnover_rate'}
                changes = dict(after or {})
                import math
                if not changes or set(changes) - allowed or any(
                    isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                    for value in changes.values()
                ):
                    raise ValueError("修正值必须是合法价格字段及有限数值")
                original = self.store.get_issue(issue_id)
                adjustment = str((original.get('evidence') or {}).get('adjustment') or '')
                row = connection.execute(
                    'SELECT * FROM market_daily_prices WHERE symbol=? AND trade_date=? AND adjustment=?',
                    (original.get('symbol'), str(original.get('observation_at') or '')[:10], adjustment),
                ).fetchone()
                if row is None or any(key not in (before or {}) or row[key] != before[key] for key in changes):
                    raise ValueError("原值已变化或缺少修正前值，请刷新异常详情后重试")
                issue = self.store.disposition_issue(
                    issue_id, action=action, reason=reason, operator=operator,
                    before=before, after=after,
                )
                return self._complete_overlay_repair(issue_id)
        return self.store.disposition_issue(
            issue_id, action=action, reason=reason, operator=operator,
            before=before, after=after,
        )

    def _complete_overlay_repair(self, issue_id: str) -> dict[str, Any]:
        from data_platform.maintenance_transaction import transaction_connection, materialize_price_corrections, record_activation
        connection = transaction_connection(self.store.database_path)
        issue = self.store.get_issue(issue_id)
        if issue["dataset"] != "a_share_daily" or issue["rule_id"] != "ohlcv_validity":
            raise ValueError("此问题不能通过价格字段修正自动闭环，请使用对应的重拉或证据修复流程")
        parent_scan = str(issue.get("source_task_id") or "")
        if not parent_scan:
            raise ValueError("缺少原始检查任务，无法验证修复范围")
        readiness = self.store.release_readiness(exempt_issue_id=issue_id)
        if readiness["status"] != "ready":
            raise ValueError("其他质量问题仍阻断生效；本次修正未写入，请先处理阻断项")
        versions = self.store.list_versions()
        base = versions.get("default_version") or versions.get("latest_published_version")
        if not base:
            raise ValueError("价格修正需要现有可用数据")
        base_id = str(base["data_version_id"])
        if base_id != str((versions.get("latest_published_version") or {}).get("data_version_id")):
            raise ValueError("当前数据与最新检查记录不一致，请先完成一次数据更新")
        # 仅处理本次请求指定的单个问题；不消费其他待处理纠错。
        self.store.mark_overlay_published(issue_id, data_version_id=base_id)
        materialize_price_corrections(connection, base_id, selected_issue_ids={issue_id})
        scan = self.quality_scan_engine.recheck(parent_scan)
        checked = self.quality_scan_engine.run_scan(scan["scan_id"], selected_issue_ids={issue_id})
        if checked["status"] != "passed" or self.store.get_issue(issue_id)["status"] != "corrected":
            raise ValueError("修复复检未通过；修正及生效均已撤回")
        history = self.store.get_issue_history(issue_id)
        payload = {"issue_id": issue_id, "base_version_id": base_id,
                   "verification_scan_id": scan["scan_id"], "corrections": history["overlays"]}
        digest = sha256(self._stable_json(payload).encode("utf-8")).hexdigest()
        report = self.governance_store.save_quality_report(
            quality_report_id="dq-correction-" + digest[:24], rule_version="r1-price-correction-v1",
            status="passed", payload=payload,
        )
        base_version = self.governance_store.fetch_data_version(base_id)
        members = []
        for raw in base_version.get("members") or []:
            member = self._data_version_member_payload(raw)
            if member["dataset"] == "market_daily_prices":
                member["content_hash"] = sha256((str(member.get("content_hash")) + digest).encode()).hexdigest()
                member["details"] = {**member.get("details", {}), "correction_evidence_hash": digest}
            members.append(member)
        published = self.governance_store.publish_data_version(
            as_of_trade_date=str(base_version["as_of_trade_date"]),
            quality_report_id=report["quality_report_id"], members=members,
            notes="R1 single-issue price correction; issue=" + issue_id,
        )
        version_id = published["data_version_id"]
        connection.execute("UPDATE data_correction_overlays SET data_version_id=? WHERE issue_id=? AND data_version_id=?",
                           (version_id, issue_id, base_id))
        connection.execute("UPDATE data_quality_remediations SET data_version_id=? WHERE issue_id=? AND data_version_id=?",
                           (version_id, issue_id, base_id))
        connection.execute("UPDATE data_quality_issues SET data_version_id=? WHERE issue_id=?",
                           (version_id, issue_id))
        self.store.set_default_version(version_id)
        record_activation(connection, "correction-" + issue_id, version_id)
        return {**self.store.get_issue(issue_id), "data_version_id": version_id,
                "verification_scan_id": scan["scan_id"], "automatically_effective": True}

    def bulk_disposition_quality_issues(
        self, issue_ids: Sequence[str], *, action: str, reason: str, operator: str,
    ) -> dict[str, Any]:
        items = self.store.bulk_disposition_issues(
            issue_ids, action=action, reason=reason, operator=operator,
        )
        return {"processed_count": len(items), "items": items}

    def preview_selected_corrections(self, issue_ids: Sequence[str]) -> dict[str, Any]:
        from app.services.selected_quality_repair import correction_preview
        return correction_preview(self, issue_ids)

    def correct_selected_issues(self, issue_ids: Sequence[str], *, corrections: Sequence[dict[str, Any]],
                                reason: str, operator: str) -> dict[str, Any]:
        from app.services.selected_quality_repair import execute_selected
        return execute_selected(self, issue_ids, action="correct", corrections=corrections, reason=reason, operator=operator)

    def _validate_quality_refetch_issue(self, issue: Mapping[str, Any]) -> None:
        if str(issue.get("status")) not in {"open", "quarantined"}:
            raise ValueError(f"quality issue is already resolved: {issue.get('issue_id')}")
        if str(issue.get("rule_id") or "") == "trading_status_semantics":
            raise ValueError(
                "trading status semantic issues require the governed preview/apply repair path"
            )
        dataset = str(issue["dataset"])
        symbol = str(issue.get("symbol") or "")
        self._usable_routes(dataset)
        if dataset == "a_share_daily" and not symbol:
            raise ValueError("A-share daily quality refetch requires a symbol")
        if dataset != "a_share_daily":
            catalog = {item["dataset_id"]: item for item in self.store.list_datasets()}
            if not catalog.get(dataset, {}).get("sync_enabled") or self.panorama_service is None:
                raise ValueError(f"quality refetch is not enabled for dataset: {dataset}")

    def refetch_quality_issue(self, issue_id: str, *, run_now: bool = False) -> dict[str, Any]:
        issue = self.store.get_issue(issue_id)
        self._validate_quality_refetch_issue(issue)
        dataset = str(issue["dataset"])
        symbol = str(issue.get("symbol") or "")
        target = str(issue.get("observation_at") or date.today().isoformat())[:10]
        gap_scan = False
        if dataset == "a_share_daily":
            evidence = dict(issue.get("evidence") or {})
            rule_id = str(issue.get("rule_id") or "")
            adjustments = [str(evidence.get("adjustment") or "raw")]
            start_floor = target
            if rule_id == "missing_open_day":
                start_floor = str(evidence.get("first_missing_date") or target)[:10]
                target = str(evidence.get("last_missing_date") or target)[:10]
                gap_scan = True
            elif rule_id == "adjustment_date_consistency":
                adjustments = [
                    str(item) for item in evidence.get("missing_adjustments") or ()
                ] or ["raw"]
                gap_scan = True
            job = self.scheduler.create_job(
                target_trade_date=target, symbols=[symbol], all_current=False,
                adjustments=adjustments, mode="quality_refetch",
                start_floor=start_floor, gap_scan=gap_scan,
                effective_config=self.store.effective_route_config(dataset),
            )
        else:
            symbols = [symbol] if dataset == "events" and symbol else []
            job = self.panorama_service.create_job(
                datasets=[dataset], target_trade_date=target, symbols=symbols,
            )
        task_id = str(job["job_id"])
        snapshot = self.store.freeze_route_snapshot(dataset, task_id=task_id)
        refetch = self.store.record_refetch(issue_id, task_id)
        remediation = self.store.create_remediation(
            issue_id,
            method="refetch" if not gap_scan else "historical_backfill",
            executor_type="a_share_sync" if dataset == "a_share_daily" else "panorama_sync",
            executor_id=task_id,
            reason="受控重拉质量问题范围",
            operator="local-user",
        )
        if run_now:
            job = self.run_sync_task(task_id)
            self.store.update_refetch(str(refetch["refetch_id"]), status=str(job.get("status") or "running"))
        return {
            **refetch,
            "job": job,
            "remediation": remediation,
            "route_snapshot_id": snapshot["snapshot_id"],
        }

    def preview_trading_status_repair(
        self, issue_id: str, *, operator: str = "local-user",
    ) -> dict[str, Any]:
        issue = self._trading_status_repair_issue(issue_id)
        preview = self.governance_store.inspect_trading_status_repair(
            symbol=str(issue["symbol"]),
            trade_date=str(issue["observation_at"])[:10],
        )
        result = {
            **preview, "status": "previewed", "writes": 0,
            "issue_id": str(issue_id), "operator": str(operator or "local-user"),
            "preview_token": "", "preview_expires_in_seconds": 0,
        }
        if preview["repairability"] != "auto_repairable":
            return result
        token = f"dctrp-{uuid.uuid4().hex}"
        now = time.monotonic()
        with self._trading_status_repair_preview_lock:
            self._trading_status_repair_previews[token] = {
                "created_monotonic": now, "issue_id": str(issue_id),
                "evidence_fingerprint": preview["evidence_fingerprint"],
            }
            self._trading_status_repair_previews = {
                key: value
                for key, value in self._trading_status_repair_previews.items()
                if now - float(value["created_monotonic"]) <= 900
            }
        result.update({
            "preview_token": token, "preview_expires_in_seconds": 900,
        })
        return result

    def apply_trading_status_repair(
        self, issue_id: str, *, preview_token: str,
        operator: str = "local-user",
    ) -> dict[str, Any]:
        issue = self._trading_status_repair_issue(issue_id)
        with self._trading_status_repair_preview_lock:
            preview = self._trading_status_repair_previews.pop(
                str(preview_token), None,
            )
        if preview is None or time.monotonic() - float(
            preview["created_monotonic"]
        ) > 900:
            raise ValueError("a current trading status repair preview is required")
        if str(preview["issue_id"]) != str(issue_id):
            raise ValueError("trading status repair issue changed after preview")
        remediation = self.store.create_remediation(
            str(issue_id), method="recompute",
            executor_type="trading_status_semantic_repair",
            executor_id=str(preview_token),
            reason="根据规范正成交量与停牌区间证据确定性修复交易状态",
            operator=str(operator or "local-user"),
        )
        try:
            repaired = self.governance_store.repair_trading_status_from_canonical_bar(
                symbol=str(issue["symbol"]),
                trade_date=str(issue["observation_at"])[:10],
                expected_fingerprint=str(preview["evidence_fingerprint"]),
                issue_id=str(issue_id), operator=str(operator or "local-user"),
            )
            self.store.update_remediation(
                str(remediation["remediation_id"]), status="awaiting_recheck",
            )
        except Exception as error:
            self.store.update_remediation(
                str(remediation["remediation_id"]), status="failed",
                last_error=f"{type(error).__name__}: {error}",
            )
            raise
        return {
            "status": "awaiting_recheck", "writes": 1,
            "issue_id": str(issue_id), "repair": repaired,
            "remediation": self.store.get_remediation(
                str(remediation["remediation_id"]),
            ),
            "next_action": "recheck the source quality scan in M3",
        }

    def preview_trading_status_batch_remediation(
        self, *, scope: str = "all_symbols",
    ) -> dict[str, Any]:
        """Run the administrator preflight without creating a task or writing data."""

        normalized_scope = self._normalize_trading_status_scope(scope)
        report = build_preview_report(
            self.governance_store.database_path,
            current_symbols_only=normalized_scope == "current_symbols",
            page_size=1_000,
            sample_limit=20,
        )
        return {
            **report,
            "scope": normalized_scope,
            "status": "previewed",
            "writes": 0,
            "apply_supported": True,
            "task_start_supported": True,
            "task_execution_mode": "background_v2",
            "max_writes_per_request": 1_000,
            "max_commit_batch_size": 1_000,
            "max_authorized_total_writes": TRADING_STATUS_MAX_AUTHORIZED_WRITES,
            "recommended_canary_writes": 100,
            "confirmation_phrase": TRADING_STATUS_BATCH_CONFIRMATION,
            "next_authorization_required": (
                "each background task requires an explicit authorization_reference "
                "and the exact confirmation phrase before start"
            ),
            "execution_boundary": (
                "administrator-only; a new task freezes its total authorization "
                "at no more than 1000000 writes, commits no more than 1000 rows "
                "per transaction, and cannot expand its authorization on resume"
            ),
        }

    def get_trading_status_remediation_closure(self) -> dict[str, Any]:
        """Describe the unpublished aggregate administrator remediation set."""

        return self._build_trading_status_remediation_closure()

    def reconcile_trading_status_quality_issues(
        self,
        *,
        scan_id: str,
        expected_issue_set_hash: str,
        operator: str,
        reason: str,
        confirmation: str,
    ) -> dict[str, Any]:
        """Close stale issue rows only after an exact governed physical recheck."""

        if str(confirmation or "") != (
            TRADING_STATUS_ISSUE_RECONCILIATION_CONFIRMATION
        ):
            raise ValueError("exact trading-status issue reconciliation confirmation is required")
        try:
            database_lease = acquire_trading_status_database_lease(
                self.governance_store.database_path,
                run_id="status-issue-reconciliation",
                holder_kind="web_issue_reconciliation",
            )
        except TradingStatusDatabaseLeaseBusyError as error:
            raise ValueError(str(error)) from error
        try:
            database_lease.assert_database(self.store.database_path)
            result = self.store.reconcile_trading_status_issues(
                scan_id=scan_id,
                expected_issue_set_hash=expected_issue_set_hash,
                operator=operator,
                reason=reason,
            )
            closure = self._build_trading_status_remediation_closure()
            closure["issue_reconciliation_result"] = result
            return closure
        finally:
            database_lease.release()

    def quick_recheck_trading_status_remediation_closure(
        self, *, expected_base_version_id: str,
        expected_base_manifest_hash: str, expected_change_set_hash: str,
    ) -> dict[str, Any]:
        try:
            database_lease = acquire_trading_status_database_lease(
                self.governance_store.database_path,
                run_id="status-closure-quick-recheck",
                holder_kind="web_correction_quick_recheck",
            )
        except TradingStatusDatabaseLeaseBusyError as error:
            closure = self._build_trading_status_remediation_closure()
            return self._block_trading_status_closure(
                closure,
                check_id="active_trading_status_writer",
                reason=str(error),
            )
        try:
            return self._quick_recheck_trading_status_remediation_under_lease(
                expected_base_version_id=expected_base_version_id,
                expected_base_manifest_hash=expected_base_manifest_hash,
                expected_change_set_hash=expected_change_set_hash,
                database_lease=database_lease,
            )
        finally:
            database_lease.release()

    def publish_trading_status_correction_version(
        self, **request,
    ) -> dict[str, Any]:
        from data_platform.maintenance_transaction import maintenance_transaction
        with maintenance_transaction(self.store.database_path) as connection:
            result = self._publish_trading_status_correction_version(**request)
            if result.get('status') in {'published', 'already_published'}:
                self.store.set_default_version(result['data_version_id'])
                from data_platform.maintenance_transaction import record_activation
                record_activation(connection, 'status-' + result['data_version_id'], result['data_version_id'])
                result['release'].update(default_changed=True, is_default=True)
                result['next_action'] = 'none'
            return result

    def complete_trading_status_correction(self, **request) -> dict[str, Any]:
        """保留历史修复的显式授权，复检与自动生效合为一次操作。"""
        from data_platform.maintenance_transaction import maintenance_transaction
        if request.get('confirmation') != TRADING_STATUS_CORRECTION_CONFIRMATION:
            raise ValueError('exact trading-status correction confirmation is required')
        if not str(request.get('operator') or '').strip() or not str(request.get('authorization_reference') or '').strip():
            raise ValueError('operator and authorization_reference are required')
        with maintenance_transaction(self.store.database_path) as connection:
            checked = self.quick_recheck_trading_status_remediation_closure(**{
                key: request[key] for key in ('expected_base_version_id', 'expected_base_manifest_hash', 'expected_change_set_hash')
            })
            if checked.get('status') != 'passed':
                return checked
            request.update(expected_quality_report_id=checked['recheck']['quality_report_id'],
                           expected_quality_report_hash=checked['recheck']['quality_report_hash'])
            result = self._publish_trading_status_correction_version(**request)
            if result.get('status') in {'published', 'already_published'}:
                self.store.set_default_version(result['data_version_id'])
                from data_platform.maintenance_transaction import record_activation
                record_activation(connection, 'status-' + result['data_version_id'], result['data_version_id'])
                result['release'].update(default_changed=True, is_default=True)
                result['next_action'] = 'none'
            return result

    def _publish_trading_status_correction_version(
        self, *, expected_base_version_id: str,
        expected_base_manifest_hash: str, expected_change_set_hash: str,
        expected_quality_report_id: str, expected_quality_report_hash: str,
        operator: str, authorization_reference: str, confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "") != TRADING_STATUS_CORRECTION_CONFIRMATION:
            raise ValueError("exact trading-status correction confirmation is required")
        normalized_operator = str(operator or "").strip()
        if not normalized_operator or len(normalized_operator) > 120:
            raise ValueError("operator is required and must not exceed 120 characters")
        normalized_authorization_reference = str(
            authorization_reference or ""
        ).strip()
        if (
            not normalized_authorization_reference
            or len(normalized_authorization_reference) > 500
        ):
            raise ValueError(
                "authorization_reference is required and must not exceed 500 characters"
            )
        try:
            database_lease = acquire_trading_status_database_lease(
                self.governance_store.database_path,
                run_id="status-correction-publish",
                holder_kind="web_correction_publish",
            )
        except TradingStatusDatabaseLeaseBusyError as error:
            closure = self._build_trading_status_remediation_closure()
            return self._block_trading_status_closure(
                closure,
                check_id="active_trading_status_writer",
                reason=str(error),
            )
        try:
            current = self.governance_store.fetch_current_published_data_version()
            idempotent = self._idempotent_trading_status_correction_target(
                current,
                expected_base_version_id=expected_base_version_id,
                expected_base_manifest_hash=expected_base_manifest_hash,
                expected_change_set_hash=expected_change_set_hash,
                expected_quality_report_id=expected_quality_report_id,
                expected_quality_report_hash=expected_quality_report_hash,
            )
            if idempotent is not None:
                current_members = [
                    self._data_version_member_payload(member)
                    for member in current.get("members") or []
                ]
                current_status = next(
                    member for member in current_members
                    if member["dataset"] == "security_trading_status_daily"
                    and member["adjustment"] == ""
                )
                published = self.governance_store.publish_trading_status_correction_version(
                    as_of_trade_date=str(current["as_of_trade_date"]),
                    quality_report_id=str(current["quality_report_id"]),
                    expected_quality_report_hash=expected_quality_report_hash,
                    change_set_hash=expected_change_set_hash,
                    run_bindings=list(
                        (idempotent.get("change_set") or {}).get(
                            "run_bindings"
                        ) or []
                    ),
                    members=current_members,
                    expected_parent_version_id=expected_base_version_id,
                    expected_parent_manifest_hash=expected_base_manifest_hash,
                    expected_trading_status_content_hash=str(
                        current_status["content_hash"]
                    ),
                    notes=str(current.get("notes") or ""),
                )
                return {
                    **idempotent,
                    "status": "already_published",
                    "data_version_id": published["data_version_id"],
                    "version_id": published["data_version_id"],
                    "release": {
                        "status": "already_published",
                        "data_version_id": published["data_version_id"],
                        "manifest_hash": published["manifest_hash"],
                        "quality_report_id": published["quality_report_id"],
                        "default_changed": False,
                    },
                    "next_action": "set_default_version",
                }

            recheck = self._quick_recheck_trading_status_remediation_under_lease(
                expected_base_version_id=expected_base_version_id,
                expected_base_manifest_hash=expected_base_manifest_hash,
                expected_change_set_hash=expected_change_set_hash,
                database_lease=database_lease,
            )
            if recheck.get("status") != "passed":
                return recheck
            actual_recheck = dict(recheck.get("recheck") or {})
            if (
                str(actual_recheck.get("quality_report_id") or "")
                != str(expected_quality_report_id or "")
                or str(actual_recheck.get("quality_report_hash") or "")
                != str(expected_quality_report_hash or "")
            ):
                return self._block_trading_status_closure(
                    recheck,
                    check_id="quality_report_drift",
                    reason="quick-recheck quality report changed; review it before publish",
                )
            base = self.governance_store.fetch_current_published_data_version()
            if (
                str(base.get("data_version_id") or "") != expected_base_version_id
                or str(base.get("manifest_hash") or "") != expected_base_manifest_hash
            ):
                return self._block_trading_status_closure(
                    recheck,
                    check_id="published_parent_drift",
                    reason="published parent changed after quick recheck",
                )
            members = [
                self._data_version_member_payload(member)
                for member in base.get("members") or []
            ]
            physical = dict(actual_recheck["physical_member"])
            change_set = dict(recheck["change_set"])
            published_run_ids = sorted(set(
                str(item) for item in (
                    list(recheck.get("consumed_run_ids") or [])
                    + list(change_set.get("run_ids") or [])
                ) if str(item)
            ))
            included = self.governance_store.inspect_admin_trading_status_change_set(
                excluded_run_ids=published_run_ids,
            )
            if int(included.get("key_count") or 0) != 0:
                return self._block_trading_status_closure(
                    recheck,
                    check_id="change_set_drift",
                    reason="new administrator rows appeared after quick recheck",
                )
            closure_details = {
                "schema_version": "1",
                "scope": "all_symbols",
                "parent_data_version_id": expected_base_version_id,
                "parent_manifest_hash": expected_base_manifest_hash,
                "published_run_ids": published_run_ids,
                "change_run_ids": list(change_set.get("run_ids") or []),
                "change_set_hash": expected_change_set_hash,
                "change_key_count": int(change_set.get("key_count") or 0),
                "change_key_hash": str(change_set.get("key_hash") or ""),
                "change_row_content_hash": str(
                    change_set.get("row_content_hash") or ""
                ),
                "included_key_count": int(included.get("included_key_count") or 0),
                "included_key_hash": str(included.get("included_key_hash") or ""),
                "included_row_content_hash": str(
                    included.get("included_row_content_hash") or ""
                ),
                "quality_report_id": expected_quality_report_id,
                "quality_report_hash": expected_quality_report_hash,
                "full_member_content_hash": str(physical["content_hash"]),
                "operator": normalized_operator,
                "authorization_reference": normalized_authorization_reference,
            }
            status_member_count = 0
            for member in members:
                if (
                    member["dataset"] == "security_trading_status_daily"
                    and member["adjustment"] == ""
                ):
                    status_member_count += 1
                    details = dict(member.get("details") or {})
                    details[TRADING_STATUS_CLOSURE_DETAILS_KEY] = closure_details
                    member.update({
                        "row_count": int(physical["row_count"]),
                        "symbol_count": int(physical["symbol_count"]),
                        "min_date": physical.get("min_date"),
                        "max_date": physical.get("max_date"),
                        "source": "stage2-trading-status-correction",
                        "sync_run_ref": (
                            f"status-remediation-change-set:{expected_change_set_hash}"
                        ),
                        "content_hash": str(physical["content_hash"]),
                        "quality_status": "passed",
                        "details": details,
                    })
            if status_member_count != 1:
                raise ValueError("base release requires exactly one trading-status member")
            published = self.governance_store.publish_trading_status_correction_version(
                as_of_trade_date=str(base["as_of_trade_date"]),
                quality_report_id=expected_quality_report_id,
                expected_quality_report_hash=expected_quality_report_hash,
                change_set_hash=expected_change_set_hash,
                run_bindings=list(change_set.get("run_bindings") or []),
                members=members,
                expected_parent_version_id=expected_base_version_id,
                expected_parent_manifest_hash=expected_base_manifest_hash,
                expected_trading_status_content_hash=str(physical["content_hash"]),
                notes=(
                    "stage2 independent trading-status correction; "
                    f"change_set={expected_change_set_hash}; operator={normalized_operator}; "
                    f"authorization={normalized_authorization_reference}"
                ),
            )
            release_status = str(published.get("publication_status") or "published")
            return {
                **recheck,
                "status": release_status,
                "data_version_id": published["data_version_id"],
                "version_id": published["data_version_id"],
                "release": {
                    "status": release_status,
                    "data_version_id": published["data_version_id"],
                    "manifest_hash": published["manifest_hash"],
                    "quality_report_id": expected_quality_report_id,
                    "default_changed": False,
                },
                "next_action": "set_default_version",
            }
        finally:
            database_lease.release()

    def _quick_recheck_trading_status_remediation_under_lease(
        self, *, expected_base_version_id: str,
        expected_base_manifest_hash: str, expected_change_set_hash: str,
        database_lease: TradingStatusDatabaseLease,
    ) -> dict[str, Any]:
        database_lease.assert_database(self.governance_store.database_path)
        closure = self._build_trading_status_remediation_closure()
        drift_checks = (
            (
                "base_version_drift",
                str((closure.get("base_version") or {}).get("data_version_id") or "")
                == str(expected_base_version_id or ""),
                "published base version changed",
            ),
            (
                "base_manifest_drift",
                str((closure.get("base_version") or {}).get("manifest_hash") or "")
                == str(expected_base_manifest_hash or ""),
                "published base manifest changed",
            ),
            (
                "change_set_drift",
                str((closure.get("change_set") or {}).get("change_set_hash") or "")
                == str(expected_change_set_hash or ""),
                "administrator change set changed",
            ),
        )
        for check_id, passed, reason in drift_checks:
            if not passed:
                closure = self._block_trading_status_closure(
                    closure, check_id=check_id, reason=reason,
                )
        if closure.get("blockers"):
            return closure
        if (
            int((closure.get("change_set") or {}).get("key_count") or 0) == 0
            and int((closure.get("change_set") or {}).get("run_count") or 0) == 0
        ):
            closure["status"] = "no_changes"
            closure["next_action"] = "none"
            return closure

        preview = build_preview_report(
            self.governance_store.database_path,
            current_symbols_only=False,
            page_size=5_000,
            sample_limit=20,
        )
        repairability = dict(preview.get("repairability_counts") or {})
        candidate_count = int(preview.get("candidate_count") or 0)
        auto_count = int(repairability.get("auto_repairable") or 0)
        manual_count = int(repairability.get("manual_evidence_required") or 0)
        physical = self.governance_store.inspect_trading_status_member_content()
        base_member = dict(closure.get("base_trading_status_member") or {})
        summary_matches = all(
            base_member.get(field) == physical.get(field)
            for field in ("row_count", "symbol_count", "min_date", "max_date")
        )
        after = self._build_trading_status_remediation_closure()
        stable = bool(
            str((after.get("base_version") or {}).get("data_version_id") or "")
            == str(expected_base_version_id)
            and str((after.get("base_version") or {}).get("manifest_hash") or "")
            == str(expected_base_manifest_hash)
            and str((after.get("change_set") or {}).get("change_set_hash") or "")
            == str(expected_change_set_hash)
        )
        checks = [
            {
                "check_id": "all_symbols_candidate_count_zero",
                "status": "passed" if candidate_count == 0 else "blocked",
                "count": candidate_count,
            },
            {
                "check_id": "all_symbols_auto_candidate_count_zero",
                "status": "passed" if auto_count == 0 else "blocked",
                "count": auto_count,
            },
            {
                "check_id": "all_symbols_manual_candidate_count_zero",
                "status": "passed" if manual_count == 0 else "blocked",
                "count": manual_count,
            },
            {
                "check_id": "trading_status_member_summary_consistent",
                "status": "passed" if summary_matches else "blocked",
            },
            {
                "check_id": "closure_evidence_stable_during_recheck",
                "status": "passed" if stable else "blocked",
            },
        ]
        passed = all(item["status"] == "passed" for item in checks)
        stable_preview = {
            "scope": "all_symbols",
            "candidate_count": candidate_count,
            "repairability_counts": repairability,
            "reason_counts": dict(preview.get("reason_counts") or {}),
            "source_counts": dict(preview.get("source_counts") or {}),
            "candidate_set_hash": str(preview.get("candidate_set_hash") or ""),
        }
        report_payload = {
            "rule_version": TRADING_STATUS_CLOSURE_RULE_VERSION,
            "base_version": closure.get("base_version"),
            "change_set": closure.get("change_set"),
            "scope": "all_symbols",
            "preview": stable_preview,
            "physical_member": physical,
            "checks": checks,
            "release_readiness": closure.get("release_readiness"),
        }
        report_payload_hash = sha256(
            self._stable_json(report_payload).encode("utf-8")
        ).hexdigest()
        quality_report_id = f"dq-ts-closure-{report_payload_hash[:24]}"
        quality_report = self.governance_store.save_quality_report(
            quality_report_id=quality_report_id,
            rule_version=TRADING_STATUS_CLOSURE_RULE_VERSION,
            status="passed" if passed else "failed",
            payload=report_payload,
        )
        result = dict(after if stable else closure)
        result["recheck"] = {
            "status": "passed" if passed else "blocked",
            **stable_preview,
            "quality_report_id": quality_report_id,
            "quality_report_hash": str(quality_report["payload_hash"]),
            "physical_member": physical,
            "checks": checks,
        }
        if passed:
            result["status"] = "passed"
            result["release"] = {
                "status": "ready",
                "quality_report_id": quality_report_id,
                "default_changed": False,
            }
            result["next_action"] = "publish_correction"
        else:
            for check in checks:
                if check["status"] == "blocked":
                    result = self._block_trading_status_closure(
                        result,
                        check_id=str(check["check_id"]),
                        reason="quick all-symbol trading-status gate failed",
                        count=check.get("count"),
                    )
        return result

    def _build_trading_status_remediation_closure(self) -> dict[str, Any]:
        blockers: list[dict[str, Any]] = []
        base = self.governance_store.fetch_current_published_data_version()
        base_version: dict[str, Any] | None = None
        base_member: dict[str, Any] = {}
        base_closure_details: dict[str, Any] = {}
        consumed_bindings = (
            self.governance_store
            .fetch_trading_status_remediation_release_bindings()
        )
        consumed_run_ids = sorted(set(
            str(item.get("run_id") or "") for item in consumed_bindings
            if str(item.get("run_id") or "")
        ))
        if base.get("status") == "not_found":
            blockers.append({
                "check_id": "published_base_version",
                "status": "blocked",
                "reason": "no current published base version",
            })
        else:
            base_version = {
                "data_version_id": str(base["data_version_id"]),
                "manifest_hash": str(base["manifest_hash"]),
                "as_of_trade_date": str(base["as_of_trade_date"]),
                "quality_report_id": str(base["quality_report_id"]),
            }
            recomputed_manifest_hash = self._data_version_manifest_hash(base)
            if recomputed_manifest_hash != base_version["manifest_hash"]:
                blockers.append({
                    "check_id": "base_manifest_integrity",
                    "status": "blocked",
                    "reason": "stored base manifest hash does not match its members",
                })
            status_members = [
                member for member in base.get("members") or []
                if str(member.get("dataset") or "")
                == "security_trading_status_daily"
                and str(member.get("adjustment") or "") == ""
            ]
            if len(status_members) != 1:
                blockers.append({
                    "check_id": "base_trading_status_member",
                    "status": "blocked",
                    "reason": "base requires exactly one trading-status member",
                })
            else:
                base_member = self._data_version_member_payload(status_members[0])
                base_closure_details = dict(
                    (base_member.get("details") or {}).get(
                        TRADING_STATUS_CLOSURE_DETAILS_KEY
                    ) or {}
                )

        audit = self.governance_store.inspect_admin_trading_status_change_set(
            excluded_run_ids=consumed_run_ids,
        )
        if int(audit.get("invalid_evidence_count") or 0):
            blockers.append({
                "check_id": "admin_row_run_evidence",
                "status": "blocked",
                "reason": "administrator rows without a valid remediation run_id exist",
                "count": int(audit["invalid_evidence_count"]),
            })
        empty_hash = sha256(b"").hexdigest()
        physical_key_counts = dict(audit.get("physical_run_key_counts") or {})
        physical_fingerprint_hashes = dict(
            audit.get("physical_run_key_fingerprint_hashes") or {}
        )
        physical_row_hashes = dict(
            audit.get("physical_run_row_content_hashes") or {}
        )
        for consumed_binding in consumed_bindings:
            run_id = str(consumed_binding.get("run_id") or "")
            actual_consumed_identity = {
                "physical_key_count": int(physical_key_counts.get(run_id) or 0),
                "physical_key_fingerprint_hash": str(
                    physical_fingerprint_hashes.get(run_id) or empty_hash
                ),
                "physical_row_content_hash": str(
                    physical_row_hashes.get(run_id) or empty_hash
                ),
            }
            expected_consumed_identity = {
                "physical_key_count": int(
                    consumed_binding.get("physical_key_count") or 0
                ),
                "physical_key_fingerprint_hash": str(
                    consumed_binding.get("physical_key_fingerprint_hash") or ""
                ),
                "physical_row_content_hash": str(
                    consumed_binding.get("physical_row_content_hash") or ""
                ),
            }
            if expected_consumed_identity != actual_consumed_identity:
                blockers.append({
                    "check_id": "published_admin_subset_integrity",
                    "status": "blocked",
                    "reason": (
                        "a consumed remediation run was changed, overwritten or removed"
                    ),
                    "run_id": run_id,
                })
        if base_member and int(audit.get("key_count") or 0):
            min_date = str(audit.get("min_date") or "")
            max_date = str(audit.get("max_date") or "")
            if (
                not base_member.get("min_date")
                or not base_member.get("max_date")
                or min_date < str(base_member["min_date"])
                or max_date > str(base_member["max_date"])
            ):
                blockers.append({
                    "check_id": "change_dates_within_base_coverage",
                    "status": "blocked",
                    "reason": "administrator changes extend beyond base member coverage",
                })

        tasks = self.list_trading_status_batch_remediations()
        raw_checkpoint_run_ids, checkpoint_inventory_blockers = (
            self._raw_trading_status_checkpoint_inventory()
        )
        blockers.extend(checkpoint_inventory_blockers)
        checkpoint_run_ids = sorted(set(
            list(raw_checkpoint_run_ids)
            + [
                str(task.get("run_id") or "")
                for task in tasks
                if str(task.get("run_id") or "")
            ]
        ))
        unpublished_checkpoint_run_ids = sorted(
            set(checkpoint_run_ids) - set(consumed_run_ids)
        )
        physical_unpublished_run_ids = sorted(
            set(str(item) for item in audit.get("physical_run_ids") or [])
            - set(consumed_run_ids)
        )
        unpublished_run_ids = sorted(
            set(unpublished_checkpoint_run_ids) | set(physical_unpublished_run_ids)
        )
        run_bindings, run_blockers = self._trading_status_run_bindings(
            unpublished_run_ids,
            physical_key_counts,
            physical_fingerprint_hashes,
            physical_row_hashes,
        )
        blockers.extend(run_blockers)
        sealed_legacy_run_ids: set[str] = set()
        for task in tasks:
            if (
                str(task.get("checkpoint_version") or "1") == "1"
                and str(task.get("status") or "") == "paused_max_writes"
            ):
                legacy_run_id = str(task.get("run_id") or "")
                legacy_bindings, legacy_blockers = self._trading_status_run_bindings(
                    [legacy_run_id],
                    physical_key_counts,
                    physical_fingerprint_hashes,
                    physical_row_hashes,
                )
                if (
                    not legacy_blockers
                    and len(legacy_bindings) == 1
                    and legacy_bindings[0].get("evidence_status")
                    == "sealed_legacy_partial"
                ):
                    sealed_legacy_run_ids.add(legacy_run_id)
        incomplete = [
            {
                "run_id": str(item.get("run_id") or ""),
                "status": str(item.get("status") or "unknown"),
            }
            for item in tasks
            if str(item.get("status") or "")
            not in {"completed", "authorization_exhausted"}
            and str(item.get("run_id") or "") not in sealed_legacy_run_ids
        ]
        if incomplete:
            blockers.append({
                "check_id": "unfinished_remediation_tasks",
                "status": "blocked",
                "reason": "active or unfinished trading-status tasks exist",
                "count": len(incomplete),
                "items": incomplete[:20],
            })
        if unpublished_run_ids:
            sealer_bindings = [
                binding for binding in run_bindings
                if str(binding.get("checkpoint_version") or "") == "2"
                and str(binding.get("status") or "") == "completed"
                and str(binding.get("scope") or "") == "all_symbols"
                and str(binding.get("run_id") or "") in unpublished_run_ids
            ]
            valid_sealers: list[dict[str, Any]] = []
            for candidate_sealer in sealer_bindings:
                sealer_run_id = str(candidate_sealer.get("run_id") or "")
                sealer_authorized_at = self._iso_timestamp(
                    candidate_sealer.get("authorization_created_at")
                )
                sealer_finished_at = self._iso_timestamp(
                    candidate_sealer.get("finished_at")
                )
                other_times = [
                    self._iso_timestamp(
                        binding.get("finished_at") or binding.get("updated_at")
                    )
                    for binding in run_bindings
                    if str(binding.get("run_id") or "") != sealer_run_id
                ]
                if (
                    sealer_authorized_at is not None
                    and sealer_finished_at is not None
                    and sealer_finished_at >= sealer_authorized_at
                    and all(item is not None for item in other_times)
                    and (
                        not other_times
                        or sealer_authorized_at >= max(
                            item for item in other_times if item is not None
                        )
                    )
                ):
                    valid_sealers.append(candidate_sealer)
            if not valid_sealers:
                blockers.append({
                    "check_id": "completed_remediation_task",
                    "status": "blocked",
                    "reason": (
                        "current unpublished run universe lacks a latest completed "
                        "v2 all-symbol sealer"
                    ),
                })
        readiness = self.store.release_readiness(
            data_version_id=str((base_version or {}).get("data_version_id") or "")
        )
        issue_reconciliation = (
            self.store.preview_trading_status_issue_reconciliation()
        )
        if readiness.get("status") != "ready":
            blockers.append({
                "check_id": "release_readiness",
                "status": "blocked",
                "reason": "general data release readiness is blocked",
                "checks": readiness.get("checks") or [],
            })

        binding_hash = sha256(
            self._stable_json(run_bindings).encode("utf-8")
        ).hexdigest()
        change_identity = {
            "schema_version": "1",
            "base_version": base_version,
            "scope": "all_symbols",
            "run_ids": unpublished_run_ids,
            "run_count": len(unpublished_run_ids),
            "checkpoint_run_ids": unpublished_checkpoint_run_ids,
            "physical_run_ids": physical_unpublished_run_ids,
            "key_count": int(audit.get("key_count") or 0),
            "key_hash": str(audit.get("key_hash") or ""),
            "row_content_hash": str(audit.get("row_content_hash") or ""),
            "symbol_count": int(audit.get("symbol_count") or 0),
            "min_date": audit.get("min_date"),
            "max_date": audit.get("max_date"),
            "run_binding_hash": binding_hash,
            "base_included_key_count": int(audit.get("included_key_count") or 0),
            "base_included_key_hash": str(audit.get("included_key_hash") or ""),
            "base_included_row_content_hash": str(
                audit.get("included_row_content_hash") or ""
            ),
        }
        change_set_hash = sha256(
            self._stable_json(change_identity).encode("utf-8")
        ).hexdigest()
        change_set = {
            **change_identity,
            "status": "ready" if unpublished_run_ids else "empty",
            "change_set_hash": change_set_hash,
            "sample_keys": list(audit.get("exact_keys") or [])[:20],
            "key_hash_semantics": "sha256_canonical_exact_symbol_trade_date_keys_v1",
            "row_hash_semantics": "sha256_canonical_physical_admin_rows_v1",
            "run_bindings": run_bindings,
        }
        no_changes = (
            int(change_set["key_count"]) == 0
            and int(change_set["run_count"]) == 0
        )
        already_released = bool(no_changes and consumed_bindings)
        status = "blocked" if blockers else ("no_changes" if no_changes else "ready")
        return {
            "status": status,
            "scope": "all_symbols",
            "base_version": base_version,
            "base_trading_status_member": base_member,
            "base_closure_details": base_closure_details,
            "consumed_run_ids": consumed_run_ids,
            "consumed_binding_count": len(consumed_bindings),
            "change_set": change_set,
            "blockers": blockers,
            "release_readiness": readiness,
            "issue_reconciliation": issue_reconciliation,
            "recheck": {
                "status": "blocked" if blockers else (
                    "passed" if already_released else "required"
                ),
                "candidate_count": None,
                "quality_report_id": base_closure_details.get("quality_report_id"),
                "quality_report_hash": base_closure_details.get("quality_report_hash"),
            },
            "release": {
                "status": "published" if already_released else (
                    "not_published" if not blockers else "blocked"
                ),
                "data_version_id": (
                    (base_version or {}).get("data_version_id")
                    if already_released else None
                ),
                "manifest_hash": (
                    (base_version or {}).get("manifest_hash")
                    if already_released else None
                ),
                "quality_report_id": base_closure_details.get("quality_report_id"),
                "default_changed": False,
            },
            "next_action": (
                "resolve_blockers" if blockers else (
                    "none" if no_changes else "quick_recheck"
                )
            ),
            "confirmation_phrase": TRADING_STATUS_CORRECTION_CONFIRMATION,
        }

    def _raw_trading_status_checkpoint_inventory(
        self,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Inventory checkpoint filenames even when their JSON cannot be parsed."""

        blockers: list[dict[str, Any]] = []
        if not self._trading_status_remediation_dir.is_dir():
            return [], blockers
        try:
            checkpoints = list(
                self._trading_status_remediation_dir.glob("*.json")
            )
        except (OSError, RuntimeError) as error:
            return [], [{
                "check_id": "remediation_checkpoint_unreadable",
                "status": "blocked",
                "reason": (
                    "checkpoint directory cannot be inventoried: "
                    f"{type(error).__name__}: {error}"
                ),
            }]
        run_ids: list[str] = []
        directory = self._trading_status_remediation_dir.resolve()
        for checkpoint in sorted(checkpoints, key=lambda item: item.name):
            if checkpoint.name.endswith(".pause.json"):
                continue
            run_id = checkpoint.name[:-5]
            try:
                normalized_run_id = self._normalize_trading_status_run_id(run_id)
                resolved_checkpoint = checkpoint.resolve()
            except (OSError, RuntimeError, ValueError) as error:
                blockers.append({
                    "check_id": "remediation_checkpoint_unreadable",
                    "status": "blocked",
                    "reason": (
                        f"invalid checkpoint entry {checkpoint.name}: "
                        f"{type(error).__name__}: {error}"
                    ),
                })
                continue
            if resolved_checkpoint.parent != directory or not checkpoint.is_file():
                blockers.append({
                    "check_id": "remediation_checkpoint_unreadable",
                    "status": "blocked",
                    "reason": f"unsafe checkpoint entry {checkpoint.name}",
                })
                continue
            run_ids.append(normalized_run_id)
        return sorted(set(run_ids)), blockers

    def _trading_status_run_bindings(
        self, run_ids: Sequence[str], run_key_counts: Mapping[str, Any],
        run_fingerprint_hashes: Mapping[str, Any],
        run_row_content_hashes: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        bindings: list[dict[str, Any]] = []
        blockers: list[dict[str, Any]] = []
        for run_id in sorted(set(str(item) for item in run_ids if str(item))):
            checkpoint = self._trading_status_batch_checkpoint(run_id)
            if not checkpoint.is_file():
                blockers.append({
                    "check_id": "remediation_checkpoint_missing",
                    "status": "blocked",
                    "reason": f"checkpoint is missing for remediation run {run_id}",
                })
                continue
            try:
                checkpoint_bytes = self._read_trading_status_checkpoint_bytes(
                    checkpoint
                )
                state = json.loads(checkpoint_bytes.decode("utf-8"))
            except (OSError, UnicodeError, ValueError, TypeError) as error:
                blockers.append({
                    "check_id": "remediation_checkpoint_unreadable",
                    "status": "blocked",
                    "reason": f"{run_id}: {type(error).__name__}: {error}",
                })
                continue
            if (
                str(state.get("run_id") or "") != run_id
                or not self._trading_status_state_matches_database(state)
            ):
                blockers.append({
                    "check_id": "remediation_checkpoint_identity",
                    "status": "blocked",
                    "reason": f"checkpoint identity changed for remediation run {run_id}",
                })
                continue
            run_status = str(state.get("status") or "unknown")
            checkpoint_version = str(state.get("checkpoint_version") or "1")
            legacy_partial = bool(
                checkpoint_version == "1"
                and run_status == "paused_max_writes"
                and str(state.get("scope") or "") == "current_symbols"
            )
            if (
                run_status not in {"completed", "authorization_exhausted"}
                and not legacy_partial
            ):
                blockers.append({
                    "check_id": "remediation_run_incomplete",
                    "status": "blocked",
                    "reason": f"remediation run {run_id} is {run_status}",
                })
            manifest_path = Path(str(state.get("candidate_manifest") or ""))
            recorded_manifest_hash = str(
                state.get("candidate_manifest_file_hash") or ""
            )
            actual_manifest_hash = ""
            if manifest_path.is_file():
                try:
                    actual_manifest_hash = self._file_sha256(manifest_path)
                except OSError:
                    actual_manifest_hash = ""
            if (
                not recorded_manifest_hash
                or not actual_manifest_hash
                or recorded_manifest_hash != actual_manifest_hash
            ):
                blockers.append({
                    "check_id": "remediation_candidate_manifest_integrity",
                    "status": "blocked",
                    "reason": f"candidate manifest hash changed for run {run_id}",
                })
            batches = list(state.get("batches") or [])
            written_key_hashes = [
                str(batch.get("written_key_hash") or "")
                for batch in batches
            ]
            if any(
                len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in written_key_hashes
            ):
                blockers.append({
                    "check_id": "remediation_written_key_hashes",
                    "status": "blocked",
                    "reason": f"written-key hashes are incomplete for run {run_id}",
                })
            manifest_evidence: dict[str, Any] = {}
            if actual_manifest_hash:
                try:
                    manifest_evidence = self._manifest_remediation_evidence(
                        manifest_path,
                        byte_offset=int(
                            state.get("candidate_manifest_byte_offset") or 0
                        ),
                        batches=batches,
                    )
                except (OSError, UnicodeError, ValueError, TypeError) as error:
                    blockers.append({
                        "check_id": "remediation_manifest_written_evidence",
                        "status": "blocked",
                        "reason": f"{run_id}: {type(error).__name__}: {error}",
                    })
            reported_written = int(state.get("written") or 0)
            physical_key_count = int(run_key_counts.get(run_id) or 0)
            physical_fingerprint_hash = str(
                run_fingerprint_hashes.get(run_id)
                or sha256(b"").hexdigest()
            )
            physical_row_content_hash = str(
                run_row_content_hashes.get(run_id)
                or sha256(b"").hexdigest()
            )
            batch_written = sum(int(batch.get("written") or 0) for batch in batches)
            evidence_matches = bool(
                manifest_evidence
                and int(state.get("skipped") or 0) == 0
                and int(state.get("evidence_mismatch_skipped") or 0) == 0
                and batch_written == reported_written == physical_key_count
                and int(manifest_evidence.get("auto_written_count") or 0)
                == reported_written
                and list(manifest_evidence.get("batch_written_key_hashes") or [])
                == written_key_hashes
                and str(manifest_evidence.get("key_fingerprint_hash") or "")
                == physical_fingerprint_hash
            )
            if not evidence_matches:
                blockers.append({
                    "check_id": "remediation_run_evidence_consistency",
                    "status": "blocked",
                    "reason": (
                        f"checkpoint, manifest and physical rows disagree for run {run_id}"
                    ),
                })
            if (
                checkpoint_version == "2"
                and run_status == "completed"
                and (
                    str(state.get("completion_consistency") or "") != "matched"
                    or int(state.get("scanned_candidates") or 0)
                    != int(state.get("expected_candidate_count") or 0)
                    or int(manifest_evidence.get("processed_candidate_count", -1))
                    != int(state.get("expected_candidate_count") or 0)
                )
            ):
                blockers.append({
                    "check_id": "completed_run_consistency",
                    "status": "blocked",
                    "reason": f"completed v2 run {run_id} lacks matched completion evidence",
                })
            binding = {
                "run_id": run_id,
                "checkpoint_version": checkpoint_version,
                "status": run_status,
                "evidence_status": (
                    "sealed_legacy_partial" if legacy_partial and evidence_matches
                    else "terminal_run_evidence"
                ),
                "scope": str(state.get("scope") or ""),
                "authorization_created_at": str(
                    state.get("authorization_created_at") or ""
                ),
                "updated_at": str(state.get("updated_at") or ""),
                "finished_at": str(state.get("finished_at") or ""),
                "expected_candidate_set_hash": str(
                    state.get("expected_candidate_set_hash") or ""
                ),
                "checkpoint_hash": sha256(checkpoint_bytes).hexdigest(),
                "candidate_manifest_hash": actual_manifest_hash,
                "written_key_hashes": written_key_hashes,
                "manifest_key_fingerprint_hash": manifest_evidence.get(
                    "key_fingerprint_hash"
                ),
                "physical_key_fingerprint_hash": str(
                    physical_fingerprint_hash
                ),
                "physical_row_content_hash": physical_row_content_hash,
                "reported_written": reported_written,
                "physical_key_count": physical_key_count,
                "skipped": int(state.get("skipped") or 0),
                "evidence_mismatch_skipped": int(
                    state.get("evidence_mismatch_skipped") or 0
                ),
            }
            binding["binding_hash"] = sha256(
                self._stable_json(binding).encode("utf-8")
            ).hexdigest()
            bindings.append(binding)
        return bindings, blockers

    @classmethod
    def _manifest_remediation_evidence(
        cls, path: Path, *, byte_offset: int,
        batches: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if byte_offset < 0:
            raise ValueError("candidate manifest byte offset is invalid")
        records: list[dict[str, Any]] = []
        with path.open("rb") as stream:
            while stream.tell() < byte_offset:
                line = stream.readline()
                if not line or stream.tell() > byte_offset:
                    raise ValueError("candidate manifest byte offset is not a record boundary")
                record = json.loads(line.decode("utf-8"))
                records.append(dict(record))
            if stream.tell() != byte_offset:
                raise ValueError("candidate manifest byte offset changed")
        expected_processed = sum(
            int(batch.get("candidate_count") or 0) for batch in batches
        )
        if expected_processed != len(records):
            raise ValueError("batch candidate counts do not match manifest prefix")
        fingerprint_digest = sha256()
        batch_hashes: list[str] = []
        auto_written_count = 0
        cursor = 0
        for batch in batches:
            candidate_count = int(batch.get("candidate_count") or 0)
            batch_records = records[cursor:cursor + candidate_count]
            cursor += candidate_count
            key_digest = sha256()
            for record in batch_records:
                if str(record.get("repairability") or "") != "auto_repairable":
                    continue
                key = f"{record.get('symbol')}|{record.get('trade_date')}"
                fingerprint = str(record.get("evidence_fingerprint") or "")
                if not fingerprint:
                    raise ValueError("manifest candidate fingerprint is missing")
                key_digest.update(key.encode("ascii"))
                fingerprint_digest.update((
                    cls._stable_json({
                        "key": key,
                        "candidate_fingerprint": fingerprint,
                    }) + "\n"
                ).encode("utf-8"))
                auto_written_count += 1
            batch_hashes.append(key_digest.hexdigest())
        return {
            "processed_candidate_count": len(records),
            "auto_written_count": auto_written_count,
            "batch_written_key_hashes": batch_hashes,
            "key_fingerprint_hash": fingerprint_digest.hexdigest(),
        }

    def _idempotent_trading_status_correction_target(
        self, current: Mapping[str, Any], *, expected_base_version_id: str,
        expected_base_manifest_hash: str, expected_change_set_hash: str,
        expected_quality_report_id: str, expected_quality_report_hash: str,
    ) -> dict[str, Any] | None:
        if current.get("status") == "not_found":
            return None
        status_members = [
            self._data_version_member_payload(member)
            for member in current.get("members") or []
            if str(member.get("dataset") or "")
            == "security_trading_status_daily"
            and str(member.get("adjustment") or "") == ""
        ]
        if len(status_members) != 1:
            return None
        details = dict(
            (status_members[0].get("details") or {}).get(
                TRADING_STATUS_CLOSURE_DETAILS_KEY
            ) or {}
        )
        matches = all((
            str(details.get("parent_data_version_id") or "")
            == str(expected_base_version_id or ""),
            str(details.get("parent_manifest_hash") or "")
            == str(expected_base_manifest_hash or ""),
            str(details.get("change_set_hash") or "")
            == str(expected_change_set_hash or ""),
            str(details.get("quality_report_id") or "")
            == str(expected_quality_report_id or ""),
            str(details.get("quality_report_hash") or "")
            == str(expected_quality_report_hash or ""),
            str(current.get("quality_report_id") or "")
            == str(expected_quality_report_id or ""),
        ))
        if not matches:
            return None
        report = self.governance_store.fetch_quality_report(
            str(expected_quality_report_id)
        )
        if (
            str(report.get("status") or "") != "passed"
            or str(report.get("payload_hash") or "")
            != str(expected_quality_report_hash or "")
        ):
            return None
        report_change_set = dict(
            (report.get("payload") or {}).get("change_set") or {}
        )
        if (
            str(report_change_set.get("change_set_hash") or "")
            != str(expected_change_set_hash or "")
        ):
            return None
        return {
            "scope": "all_symbols",
            "base_version": {
                "data_version_id": expected_base_version_id,
                "manifest_hash": expected_base_manifest_hash,
            },
            "change_set": {
                "change_set_hash": expected_change_set_hash,
                "run_ids": list(details.get("change_run_ids") or []),
                "key_count": int(details.get("change_key_count") or 0),
                "key_hash": details.get("change_key_hash"),
                "row_content_hash": details.get("change_row_content_hash"),
                "run_bindings": list(
                    report_change_set.get("run_bindings") or []
                ),
            },
            "blockers": [],
            "recheck": {
                "status": "passed",
                "quality_report_id": expected_quality_report_id,
                "quality_report_hash": expected_quality_report_hash,
            },
            "confirmation_phrase": TRADING_STATUS_CORRECTION_CONFIRMATION,
        }

    @staticmethod
    def _block_trading_status_closure(
        payload: Mapping[str, Any], *, check_id: str, reason: str,
        count: Any = None,
    ) -> dict[str, Any]:
        result = dict(payload)
        blockers = list(result.get("blockers") or [])
        blocker = {"check_id": check_id, "status": "blocked", "reason": reason}
        if count is not None:
            blocker["count"] = count
        if not any(
            item.get("check_id") == check_id and item.get("reason") == reason
            for item in blockers
        ):
            blockers.append(blocker)
        result["status"] = "blocked"
        result["blockers"] = blockers
        recheck = dict(result.get("recheck") or {})
        recheck["status"] = "blocked"
        result["recheck"] = recheck
        release = dict(result.get("release") or {})
        release["status"] = "blocked"
        release["default_changed"] = False
        result["release"] = release
        result["next_action"] = "resolve_blockers"
        return result

    @classmethod
    def _data_version_manifest_hash(cls, version: Mapping[str, Any]) -> str:
        manifest = {
            "as_of_trade_date": str(version.get("as_of_trade_date") or ""),
            "quality_report_id": str(version.get("quality_report_id") or ""),
            "members": sorted(
                [
                    cls._data_version_member_payload(member)
                    for member in version.get("members") or []
                ],
                key=lambda item: (item["dataset"], item["adjustment"]),
            ),
        }
        return sha256(cls._stable_json(manifest).encode("utf-8")).hexdigest()

    @staticmethod
    def _data_version_member_payload(raw: Mapping[str, Any]) -> dict[str, Any]:
        details_value = raw.get("details")
        if details_value is None:
            try:
                details_value = json.loads(str(raw.get("details_json") or "{}"))
            except (TypeError, ValueError) as error:
                raise ValueError("data version member details are invalid JSON") from error
        return {
            "dataset": str(raw.get("dataset") or ""),
            "adjustment": str(raw.get("adjustment") or ""),
            "symbol_scope": str(raw.get("symbol_scope") or "all"),
            "row_count": int(raw.get("row_count") or 0),
            "symbol_count": int(raw.get("symbol_count") or 0),
            "min_date": raw.get("min_date") or None,
            "max_date": raw.get("max_date") or None,
            "source": str(raw.get("source") or "unknown"),
            "sync_run_ref": raw.get("sync_run_ref") or None,
            "content_hash": str(raw.get("content_hash") or ""),
            "quality_status": str(raw.get("quality_status") or "unknown"),
            "details": dict(details_value or {}),
        }

    @staticmethod
    def _stable_json(payload: Any) -> str:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str,
            separators=(",", ":"),
        )

    @staticmethod
    def _iso_timestamp(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value or ""))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            return None
        return parsed

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def apply_trading_status_batch_remediation(
        self, *, expected_candidate_set_hash: str, run_id: str,
        operator: str, confirmation: str, max_writes: int = 100,
        scope: str = "", authorized_total_writes: int = 0,
        commit_batch_size: int = 1_000, authorization_reference: str = "",
    ) -> dict[str, Any]:
        """Keep the <=1000 legacy call synchronous; dispatch explicit v2 tasks."""

        if (
            int(authorized_total_writes or 0) > 0
            or str(scope or "").strip()
            or str(authorization_reference or "").strip()
        ):
            return self.start_trading_status_batch_remediation(
                expected_candidate_set_hash=expected_candidate_set_hash,
                run_id=run_id,
                operator=operator,
                confirmation=confirmation,
                scope=scope or "all_symbols",
                authorized_total_writes=authorized_total_writes,
                commit_batch_size=commit_batch_size,
                authorization_reference=authorization_reference,
            )

        request = self._validate_trading_status_task_request(
            expected_candidate_set_hash=expected_candidate_set_hash,
            run_id=run_id,
            operator=operator,
            confirmation=confirmation,
            scope="current_symbols",
            authorized_total_writes=max_writes,
            commit_batch_size=1_000,
            authorization_reference="",
            require_authorization_reference=False,
        )
        if int(request["authorized_total_writes"]) > 1_000:
            raise ValueError("legacy Web batch max_writes must be between 1 and 1000")
        checkpoint = self._trading_status_batch_checkpoint(str(request["run_id"]))
        database_key = str(Path(self.governance_store.database_path).resolve())
        current_worker = threading.current_thread()
        database_lease: TradingStatusDatabaseLease | None = None
        with self.__class__._trading_status_workers_lock:
            existing = self.__class__._trading_status_workers.get(database_key)
            if existing is not None and existing[1].is_alive():
                raise ValueError(
                    f"another trading status remediation task is running for this database: "
                    f"{existing[0]}"
                )
            database_lease = acquire_trading_status_database_lease(
                self.governance_store.database_path,
                run_id=str(request["run_id"]),
                holder_kind="web_legacy_sync",
            )
            try:
                self.__class__._trading_status_workers[database_key] = (
                    str(request["run_id"]), current_worker,
                )
            except Exception:
                database_lease.release()
                raise
        try:
            with self._trading_status_batch_lock:
                state = run_batch_remediation(
                    self.governance_store.database_path,
                    expected_candidate_set_hash=str(request["expected_candidate_set_hash"]),
                    run_id=str(request["run_id"]),
                    operator=str(request["operator"]),
                    checkpoint_path=checkpoint,
                    confirmation=str(request["confirmation"]),
                    current_symbols_only=True,
                    page_size=1_000,
                    max_writes=int(request["authorized_total_writes"]),
                    database_lease=database_lease,
                )
        finally:
            if database_lease is not None:
                database_lease.release()
            with self.__class__._trading_status_workers_lock:
                existing = self.__class__._trading_status_workers.get(database_key)
                if existing is not None and existing == (
                    str(request["run_id"]), current_worker,
                ):
                    self.__class__._trading_status_workers.pop(database_key, None)
        return self._annotate_trading_status_task(state)

    def start_trading_status_batch_remediation(
        self, *, expected_candidate_set_hash: str, run_id: str,
        operator: str, confirmation: str, scope: str = "all_symbols",
        authorized_total_writes: int, commit_batch_size: int = 1_000,
        authorization_reference: str = "",
    ) -> dict[str, Any]:
        """Dispatch one durable v2 task; the request thread never writes market data."""

        request = self._validate_trading_status_task_request(
            expected_candidate_set_hash=expected_candidate_set_hash,
            run_id=run_id,
            operator=operator,
            confirmation=confirmation,
            scope=scope,
            authorized_total_writes=authorized_total_writes,
            commit_batch_size=commit_batch_size,
            authorization_reference=authorization_reference,
            require_authorization_reference=True,
        )
        checkpoint = self._trading_status_batch_checkpoint(str(request["run_id"]))
        state = {
            "checkpoint_version": "2",
            "status": "initializing",
            "run_id": request["run_id"],
            "operator": request["operator"],
            "authorized_by": request["operator"],
            "authorization_reference": request["authorization_reference"],
            "authorized_total_writes": request["authorized_total_writes"],
            "commit_batch_size": request["commit_batch_size"],
            "scope": request["scope"],
            "expected_candidate_set_hash": request["expected_candidate_set_hash"],
            "written": 0,
            "authorization_consumed": 0,
            "writes": 0,
            "pause_requested": False,
        }
        pending_state = dict(state)
        with self._trading_status_pending_lock:
            if checkpoint.exists():
                raise ValueError(
                    "trading status remediation run_id already exists; use resume without "
                    "changing its frozen authorization"
                )
            if str(request["run_id"]) in self._trading_status_pending_tasks:
                raise ValueError(
                    "trading status remediation run_id is already initializing"
                )
            self._trading_status_pending_tasks[str(request["run_id"])] = pending_state
        try:
            execution = self._dispatch_trading_status_worker(request)
        except Exception:
            with self._trading_status_pending_lock:
                existing_pending = self._trading_status_pending_tasks.get(
                    str(request["run_id"])
                )
                if existing_pending is pending_state:
                    self._trading_status_pending_tasks.pop(str(request["run_id"]), None)
            raise
        return {**self._annotate_trading_status_task(state), "execution": execution}

    def list_trading_status_batch_remediations(self) -> list[dict[str, Any]]:
        with self._trading_status_pending_lock:
            states_by_run_id = {
                run_id: dict(state)
                for run_id, state in self._trading_status_pending_tasks.items()
            }
        checkpoints = (
            self._trading_status_remediation_dir.glob("*.json")
            if self._trading_status_remediation_dir.is_dir()
            else ()
        )
        for checkpoint in checkpoints:
            if checkpoint.name.endswith(".pause.json"):
                continue
            try:
                state = json.loads(
                    self._read_trading_status_checkpoint_bytes(checkpoint).decode(
                        "utf-8"
                    )
                )
            except (OSError, ValueError, TypeError):
                continue
            if not state.get("run_id") or not self._trading_status_state_matches_database(state):
                continue
            states_by_run_id[str(state["run_id"])] = state
        items: list[dict[str, Any]] = []
        for state in states_by_run_id.values():
            annotated = self._annotate_trading_status_task(state)
            items.append({
                key: annotated.get(key)
                for key in (
                    "checkpoint_version", "run_id", "status", "scope", "operator",
                    "authorization_reference", "authorized_total_writes",
                    "commit_batch_size", "expected_candidate_count", "scanned_candidates",
                    "authorization_consumed", "written", "newly_written",
                    "recovered_written", "manual_candidates_seen", "skipped",
                    "evidence_mismatch_skipped", "throughput_candidates_per_second",
                    "pause_requested", "last_error", "started_at", "updated_at",
                    "finished_at", "progress", "execution", "read_only",
                )
            })
        items.sort(
            key=lambda item: (str(item.get("updated_at") or ""), str(item.get("run_id") or "")),
            reverse=True,
        )
        return items

    def get_trading_status_batch_remediation(self, run_id: str) -> dict[str, Any]:
        normalized_run_id = self._normalize_trading_status_run_id(run_id)
        checkpoint = self._trading_status_batch_checkpoint(normalized_run_id)
        if not checkpoint.is_file():
            with self._trading_status_pending_lock:
                pending = self._trading_status_pending_tasks.get(normalized_run_id)
                if pending is not None:
                    return self._annotate_trading_status_task(dict(pending))
            worker_error = self._trading_status_worker_errors.get(normalized_run_id)
            if worker_error:
                raise RuntimeError(worker_error)
            raise KeyError(f"trading status remediation run not found: {normalized_run_id}")
        try:
            state = json.loads(
                self._read_trading_status_checkpoint_bytes(checkpoint).decode(
                    "utf-8"
                )
            )
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("trading status remediation checkpoint is unreadable") from error
        if not self._trading_status_state_matches_database(state):
            raise ValueError("trading status remediation checkpoint database changed")
        return self._annotate_trading_status_task(state)

    def pause_trading_status_batch_remediation(self, run_id: str) -> dict[str, Any]:
        normalized_run_id = self._normalize_trading_status_run_id(run_id)
        checkpoint = self._trading_status_batch_checkpoint(normalized_run_id)
        if not checkpoint.is_file():
            with self._trading_status_pending_lock:
                pending = self._trading_status_pending_tasks.get(normalized_run_id)
                if pending is not None:
                    pending["pause_requested"] = True
                    pending["status"] = "pause_requested"
                    return self._annotate_trading_status_task(dict(pending))
        state = self.get_trading_status_batch_remediation(run_id)
        if str(state.get("checkpoint_version") or "1") != "2":
            raise ValueError("legacy checkpoint v1 is read-only")
        paused = request_batch_pause(
            self._trading_status_batch_checkpoint(str(state["run_id"]))
        )
        return self._annotate_trading_status_task(paused)

    def resume_trading_status_batch_remediation(
        self, run_id: str, *, confirmation: str,
    ) -> dict[str, Any]:
        if str(confirmation or "") != TRADING_STATUS_BATCH_CONFIRMATION:
            raise ValueError("exact trading status repair confirmation phrase is required")
        normalized_run_id = self._normalize_trading_status_run_id(run_id)
        checkpoint = self._trading_status_batch_checkpoint(normalized_run_id)
        if not checkpoint.is_file():
            with self._trading_status_pending_lock:
                pending = self._trading_status_pending_tasks.get(normalized_run_id)
            if pending is not None:
                pending_state = dict(pending)
                execution = self._trading_status_worker_execution(normalized_run_id)
                if (
                    str(pending_state.get("status") or "") != "failed"
                    or execution["status"] == "running"
                ):
                    annotated = self._annotate_trading_status_task(pending_state)
                    return {
                        **annotated,
                        "execution": {**execution, "status": "already_running"},
                    }
                with self._trading_status_pending_lock:
                    current = self._trading_status_pending_tasks.get(normalized_run_id)
                    retry_precheckpoint = bool(
                        current is pending
                        and str(current.get("status") or "") == "failed"
                    )
                    if retry_precheckpoint:
                        pending_state = dict(current)
                        current["pause_requested"] = False
                        current["status"] = "initializing"
                        current.pop("last_error", None)
                        retry_state = dict(current)
                    else:
                        retry_state = dict(current or pending_state)
                if not retry_precheckpoint:
                    annotated = self._annotate_trading_status_task(retry_state)
                    return {
                        **annotated,
                        "execution": {
                            **annotated["execution"], "status": "already_running",
                        },
                    }
                prior_runtime_error = self._trading_status_worker_errors.pop(
                    normalized_run_id, None,
                )
                request = {
                    "expected_candidate_set_hash": str(
                        pending_state["expected_candidate_set_hash"]
                    ),
                    "run_id": normalized_run_id,
                    "operator": str(pending_state["operator"]),
                    "confirmation": str(confirmation),
                    "scope": str(pending_state["scope"]),
                    "authorized_total_writes": int(
                        pending_state["authorized_total_writes"]
                    ),
                    "commit_batch_size": int(pending_state["commit_batch_size"]),
                    "authorization_reference": str(
                        pending_state.get("authorization_reference") or ""
                    ),
                }
                try:
                    execution = self._dispatch_trading_status_worker(request)
                except Exception:
                    with self._trading_status_pending_lock:
                        current = self._trading_status_pending_tasks.get(
                            normalized_run_id
                        )
                        if current is pending:
                            current.clear()
                            current.update(pending_state)
                    if prior_runtime_error:
                        self._trading_status_worker_errors[normalized_run_id] = (
                            prior_runtime_error
                        )
                    raise
                with self._trading_status_pending_lock:
                    current_state = dict(
                        self._trading_status_pending_tasks.get(
                            normalized_run_id, retry_state,
                        )
                    )
                return {
                    **self._annotate_trading_status_task(current_state),
                    "execution": execution,
                }
        state = self.get_trading_status_batch_remediation(run_id)
        if str(state.get("checkpoint_version") or "1") != "2":
            raise ValueError("legacy checkpoint v1 is read-only")
        if str(state.get("status") or "") in {"completed", "authorization_exhausted"}:
            raise ValueError(f"terminal remediation run cannot be resumed: {state['status']}")
        execution = self._trading_status_worker_execution(str(state["run_id"]))
        if execution["status"] == "running":
            return {**state, "execution": {**execution, "status": "already_running"}}
        request = {
            "expected_candidate_set_hash": str(state["expected_candidate_set_hash"]),
            "run_id": str(state["run_id"]),
            "operator": str(state["operator"]),
            "confirmation": str(confirmation),
            "scope": str(state["scope"]),
            "authorized_total_writes": int(state["authorized_total_writes"]),
            "commit_batch_size": int(state["commit_batch_size"]),
            "authorization_reference": str(state.get("authorization_reference") or ""),
            "resume": True,
        }
        execution = self._dispatch_trading_status_worker(request)
        return {**self._annotate_trading_status_task(state), "execution": execution}

    def recover_interrupted_trading_status_remediations(self) -> list[dict[str, Any]]:
        """Fail stale v2 tasks on service startup without resuming or touching market rows."""

        if not self._trading_status_remediation_dir.is_dir():
            return []
        try:
            database_lease = acquire_trading_status_database_lease(
                self.governance_store.database_path,
                run_id="__startup_recovery__",
                holder_kind="web_startup_recovery",
            )
        except TradingStatusDatabaseLeaseBusyError:
            return []
        try:
            return self._recover_interrupted_trading_status_remediations_under_lease(
                database_lease
            )
        finally:
            database_lease.release()

    def _recover_interrupted_trading_status_remediations_under_lease(
        self, database_lease: TradingStatusDatabaseLease,
    ) -> list[dict[str, Any]]:
        recovered: list[dict[str, Any]] = []
        for checkpoint in self._trading_status_remediation_dir.glob("*.json"):
            if checkpoint.name.endswith(".pause.json"):
                continue
            try:
                state = json.loads(
                    self._read_trading_status_checkpoint_bytes(checkpoint).decode(
                        "utf-8"
                    )
                )
            except (OSError, ValueError, TypeError):
                continue
            if (
                str(state.get("checkpoint_version") or "1") != "2"
                or not state.get("run_id")
                or not self._trading_status_state_matches_database(state)
                or is_batch_pause_requested(checkpoint)
                or str(state.get("status") or "") not in {
                    "initializing", "queued", "running", "pause_requested",
                }
            ):
                continue
            execution = self._trading_status_worker_execution(str(state["run_id"]))
            if execution["status"] == "running":
                continue
            interrupted = mark_batch_interrupted(
                checkpoint,
                reason="service startup found a non-terminal task without a live worker",
                database_lease=database_lease,
            )
            recovered.append(self._annotate_trading_status_task(interrupted))
        return recovered

    def _dispatch_trading_status_worker(self, request: Mapping[str, Any]) -> dict[str, Any]:
        database_key = str(Path(self.governance_store.database_path).resolve())
        run_id = str(request["run_id"])
        database_lease: TradingStatusDatabaseLease | None = None
        with self.__class__._trading_status_workers_lock:
            existing = self.__class__._trading_status_workers.get(database_key)
            if existing is not None and existing[1].is_alive():
                raise ValueError(
                    f"another trading status remediation task is running for this database: "
                    f"{existing[0]}"
                )
            self.__class__._trading_status_workers.pop(database_key, None)
            database_lease = acquire_trading_status_database_lease(
                self.governance_store.database_path,
                run_id=run_id,
                holder_kind="web_background",
            )
            try:
                worker = threading.Thread(
                    target=self._run_trading_status_worker,
                    args=(database_key, dict(request), database_lease),
                    daemon=True,
                    name=f"trading-status-remediation-{run_id}",
                )
                self.__class__._trading_status_workers[database_key] = (run_id, worker)
                worker.start()
            except Exception:
                self.__class__._trading_status_workers.pop(database_key, None)
                database_lease.release()
                raise
        return {
            "status": "dispatched", "mode": "background_thread",
            "single_worker_scope": "database",
            "lease_scope": "cross_process_database",
        }

    def _run_trading_status_worker(
        self, database_key: str, request: Mapping[str, Any],
        database_lease: TradingStatusDatabaseLease,
    ) -> None:
        run_id = str(request["run_id"])
        checkpoint = self._trading_status_batch_checkpoint(run_id)
        runtime_error = ""
        try:
            if bool(request.get("resume")):
                clear_batch_pause(checkpoint, database_lease=database_lease)
            prepare_batch_remediation(
                self.governance_store.database_path,
                expected_candidate_set_hash=str(request["expected_candidate_set_hash"]),
                run_id=run_id,
                operator=str(request["operator"]),
                checkpoint_path=checkpoint,
                confirmation=str(request["confirmation"]),
                current_symbols_only=str(request["scope"]) == "current_symbols",
                page_size=1_000,
                authorized_total_writes=int(request["authorized_total_writes"]),
                commit_batch_size=int(request["commit_batch_size"]),
                authorization_reference=str(request["authorization_reference"]),
                database_lease=database_lease,
            )
            with self._trading_status_pending_lock:
                pending = self._trading_status_pending_tasks.get(run_id)
                pause_requested = bool(
                    pending and pending.get("pause_requested")
                )
            if pause_requested:
                request_batch_pause(checkpoint)
                return
            run_batch_remediation(
                self.governance_store.database_path,
                expected_candidate_set_hash=str(request["expected_candidate_set_hash"]),
                run_id=run_id,
                operator=str(request["operator"]),
                checkpoint_path=checkpoint,
                confirmation=str(request["confirmation"]),
                current_symbols_only=str(request["scope"]) == "current_symbols",
                page_size=1_000,
                max_writes=0,
                authorized_total_writes=int(request["authorized_total_writes"]),
                commit_batch_size=int(request["commit_batch_size"]),
                authorization_reference=str(request["authorization_reference"]),
                database_lease=database_lease,
            )
            self._trading_status_worker_errors.pop(run_id, None)
        except Exception as error:
            runtime_error = f"{type(error).__name__}: {error}"
            self._trading_status_worker_errors[run_id] = runtime_error
            if checkpoint.is_file():
                try:
                    mark_batch_interrupted(
                        checkpoint,
                        reason=f"background worker exited after {runtime_error}",
                        database_lease=database_lease,
                    )
                except Exception:
                    pass
            else:
                with self._trading_status_pending_lock:
                    pending = self._trading_status_pending_tasks.get(run_id)
                    if pending is not None:
                        pending["status"] = "failed"
                        pending["last_error"] = runtime_error
                        pending["pause_requested"] = False
        finally:
            with self._trading_status_pending_lock:
                pending = self._trading_status_pending_tasks.get(run_id)
                if checkpoint.is_file():
                    self._trading_status_pending_tasks.pop(run_id, None)
                elif pending is not None and not runtime_error:
                    runtime_error = (
                        "RuntimeError: background worker exited without creating "
                        "its first checkpoint"
                    )
                    self._trading_status_worker_errors[run_id] = runtime_error
                    pending["status"] = "failed"
                    pending["last_error"] = runtime_error
                    pending["pause_requested"] = False
            database_lease.release()
            with self.__class__._trading_status_workers_lock:
                existing = self.__class__._trading_status_workers.get(database_key)
                if existing is not None and existing[0] == run_id:
                    self.__class__._trading_status_workers.pop(database_key, None)

    def _validate_trading_status_task_request(
        self, *, expected_candidate_set_hash: str, run_id: str,
        operator: str, confirmation: str, scope: str,
        authorized_total_writes: int, commit_batch_size: int,
        authorization_reference: str, require_authorization_reference: bool,
    ) -> dict[str, Any]:
        normalized_run_id = self._normalize_trading_status_run_id(run_id)
        normalized_operator = str(operator or "").strip()
        if not normalized_operator or len(normalized_operator) > 120:
            raise ValueError("operator is required and must not exceed 120 characters")
        normalized_hash = str(expected_candidate_set_hash or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_hash):
            raise ValueError("expected_candidate_set_hash must be a SHA-256 hex digest")
        if str(confirmation or "") != TRADING_STATUS_BATCH_CONFIRMATION:
            raise ValueError("exact trading status repair confirmation phrase is required")
        normalized_scope = self._normalize_trading_status_scope(scope)
        total_writes = int(authorized_total_writes)
        if total_writes < 1 or total_writes > TRADING_STATUS_MAX_AUTHORIZED_WRITES:
            raise ValueError(
                "authorized_total_writes must be between 1 and 1000000"
            )
        batch_size = int(commit_batch_size)
        if batch_size < 1 or batch_size > 1_000:
            raise ValueError("commit_batch_size must be between 1 and 1000")
        normalized_reference = str(authorization_reference or "").strip()
        if len(normalized_reference) > 500:
            raise ValueError("authorization_reference must not exceed 500 characters")
        if require_authorization_reference and not normalized_reference:
            raise ValueError(
                "authorization_reference is required for every background remediation task"
            )
        return {
            "expected_candidate_set_hash": normalized_hash,
            "run_id": normalized_run_id,
            "operator": normalized_operator,
            "confirmation": TRADING_STATUS_BATCH_CONFIRMATION,
            "scope": normalized_scope,
            "authorized_total_writes": total_writes,
            "commit_batch_size": batch_size,
            "authorization_reference": normalized_reference,
        }

    @staticmethod
    def _normalize_trading_status_run_id(run_id: str) -> str:
        normalized = str(run_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", normalized):
            raise ValueError(
                "run_id must be 1-80 characters using letters, digits, dot, dash or underscore"
            )
        return normalized

    @staticmethod
    def _normalize_trading_status_scope(scope: str) -> str:
        normalized = str(scope or "all_symbols").strip().lower()
        if normalized not in {"all_symbols", "current_symbols"}:
            raise ValueError("scope must be all_symbols or current_symbols")
        return normalized

    def _trading_status_worker_execution(self, run_id: str) -> dict[str, Any]:
        database_key = str(Path(self.governance_store.database_path).resolve())
        with self.__class__._trading_status_workers_lock:
            existing = self.__class__._trading_status_workers.get(database_key)
            if existing is not None and not existing[1].is_alive():
                self.__class__._trading_status_workers.pop(database_key, None)
                existing = None
            running = existing is not None and existing[0] == str(run_id)
            active_local_run_id = existing[0] if existing is not None else None
        if running:
            return {
                "status": "running",
                "mode": "background_thread",
                "process_scope": "local",
                "single_worker_scope": "database",
                "lease_scope": "cross_process_database",
                "database_busy": True,
                "active_run_id": str(run_id),
            }
        if active_local_run_id is not None:
            return {
                "status": "idle",
                "mode": "background_thread",
                "process_scope": "local",
                "single_worker_scope": "database",
                "lease_scope": "cross_process_database",
                "database_busy": True,
                "active_run_id": str(active_local_run_id),
            }
        try:
            lease_status = inspect_trading_status_database_lease(
                self.governance_store.database_path
            )
        except OSError as error:
            return {
                "status": "idle",
                "mode": "background_thread",
                "process_scope": "unknown",
                "single_worker_scope": "database",
                "lease_scope": "cross_process_database",
                "database_busy": True,
                "lease_probe_error": f"{type(error).__name__}: {error}",
            }
        owner = dict(lease_status.get("owner") or {})
        external_running = bool(
            lease_status.get("status") == "busy"
            and str(owner.get("run_id") or "") == str(run_id)
        )
        return {
            "status": "running" if external_running else "idle",
            "mode": "external_process" if external_running else "background_thread",
            "process_scope": "external" if external_running else "none",
            "single_worker_scope": "database",
            "lease_scope": "cross_process_database",
            "database_busy": lease_status.get("status") == "busy",
            "active_run_id": owner.get("run_id"),
            "lease_owner": owner or None,
        }

    def _annotate_trading_status_task(self, state: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(state)
        version = str(result.get("checkpoint_version") or "1")
        result["checkpoint_version"] = version
        result["read_only"] = version == "1"
        run_id = str(result.get("run_id") or "")
        if (
            version == "2"
            and run_id
            and str(result.get("status") or "")
            not in {"completed", "authorization_exhausted", "failed"}
            and is_batch_pause_requested(
                self._trading_status_batch_checkpoint(run_id)
            )
        ):
            result["pause_requested"] = True
            if str(result.get("status") or "") in {"initializing", "queued"}:
                result["status"] = "paused_by_user"
            elif str(result.get("status") or "") == "running":
                result["status"] = "pause_requested"
        total = int(result.get("authorized_total_writes") or 0)
        consumed = int(result.get("authorization_consumed") or 0)
        result["progress"] = {
            "authorized_total_writes": total,
            "authorization_consumed": consumed,
            "authorization_remaining": max(0, total - consumed),
            "percent": round(consumed * 100 / total, 2) if total else 0.0,
        }
        batches = list(result.get("batches") or [])
        result["throughput_candidates_per_second"] = (
            batches[-1].get("throughput_candidates_per_second") if batches else None
        )
        result["execution"] = self._trading_status_worker_execution(
            str(result.get("run_id") or "")
        )
        runtime_error = self._trading_status_worker_errors.get(
            str(result.get("run_id") or "")
        )
        if runtime_error:
            result["execution"]["last_error"] = runtime_error
        return result

    def _trading_status_state_matches_database(self, state: Mapping[str, Any]) -> bool:
        database = str(state.get("database") or "").strip()
        return bool(database) and Path(database).resolve() == Path(
            self.governance_store.database_path
        ).resolve()

    def _trading_status_batch_checkpoint(self, run_id: str) -> Path:
        return self._trading_status_remediation_dir / f"{run_id}.json"

    @staticmethod
    def _read_trading_status_checkpoint_bytes(path: Path) -> bytes:
        """Read a checkpoint across a bounded Windows replace-sharing window."""

        for attempt in range(_TRADING_STATUS_CHECKPOINT_READ_ATTEMPTS):
            try:
                return path.read_bytes()
            except PermissionError as error:
                winerror = getattr(error, "winerror", None)
                transient_sharing_error = winerror is None or winerror in {
                    5, 32, 33,
                }
                if (
                    not transient_sharing_error
                    or attempt + 1 >= _TRADING_STATUS_CHECKPOINT_READ_ATTEMPTS
                ):
                    raise
                time.sleep(_TRADING_STATUS_CHECKPOINT_READ_DELAY_SECONDS)
        raise AssertionError("unreachable checkpoint read retry state")

    def _trading_status_repair_issue(self, issue_id: str) -> dict[str, Any]:
        issue = self.store.get_issue(str(issue_id))
        if str(issue.get("rule_id") or "") != "trading_status_semantics":
            raise ValueError("quality issue is not a trading status semantic issue")
        if str(issue.get("dataset") or "") != "trading_status":
            raise ValueError("trading status repair requires the trading_status dataset")
        if str(issue.get("status") or "") not in {"open", "quarantined"}:
            raise ValueError(f"quality issue is already resolved: {issue_id}")
        if not str(issue.get("symbol") or "") or not str(
            issue.get("observation_at") or ""
        ):
            raise ValueError("trading status repair requires symbol and trade date")
        return issue

    def bulk_refetch_quality_issues(
        self, issue_ids: Sequence[str], *, reason: str, operator: str, run_now: bool = False,
    ) -> dict[str, Any]:
        if run_now:
            from app.services.selected_quality_repair import execute_selected
            return execute_selected(self, issue_ids, action="refetch", reason=reason, operator=operator)
        ids = list(dict.fromkeys(str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip()))
        if not ids:
            raise ValueError("at least one quality issue is required")
        if len(ids) > 50:
            raise ValueError("at most 50 quality issues can be refetched at once")
        if not reason.strip():
            raise ValueError("bulk refetch reason is required")
        issues = [self.store.get_issue(issue_id) for issue_id in ids]
        cohorts = {(str(issue["dataset"]), str(issue["rule_id"])) for issue in issues}
        if len(cohorts) != 1:
            raise ValueError("bulk refetch cannot mix datasets or quality rules")
        for issue in issues:
            self._validate_quality_refetch_issue(issue)
        results = [self.refetch_quality_issue(issue_id, run_now=False) for issue_id in ids]
        for issue_id, result in zip(ids, results, strict=True):
            self.store.disposition_issue(
                issue_id, action="quarantine", reason=reason,
                operator=operator or "local-user", before=None, after=None,
            )
        return {"processed_count": len(results), "items": results}

    def export_quality_issues(
        self, *, status: str = "", severity: str = "", dataset: str = "",
        source_task_id: str = "", source: str = "", symbol: str = "", rule_id: str = "",
        date_from: str = "", date_to: str = "", limit: int = 500,
    ) -> dict[str, Any]:
        items = self.list_quality_issues(
            status=status, severity=severity, dataset=dataset,
            source_task_id=source_task_id, source=source, symbol=symbol, rule_id=rule_id,
            date_from=date_from, date_to=date_to, limit=limit,
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "issue_id", "dataset", "symbol", "observation_at", "field_name",
            "rule_id", "severity", "status", "source", "source_task_id",
            "created_at", "updated_at",
        ])
        for item in items:
            writer.writerow([item.get(column, "") for column in (
                "issue_id", "dataset", "symbol", "observation_at", "field_name",
                "rule_id", "severity", "status", "source", "source_task_id",
                "created_at", "updated_at",
            )])
        return {
            "filename": f"data-quality-issues-{date.today().isoformat()}.csv",
            "content_type": "text/csv;charset=utf-8", "row_count": len(items),
            "content": "\ufeff" + output.getvalue(),
        }

    def list_asset_registry(self) -> list[dict[str, Any]]:
        return self.asset_governance.list_assets()

    def list_asset_lineage(self, asset_id: str = "") -> list[dict[str, Any]]:
        return self.asset_governance.list_lineage(asset_id)
    def list_assets(self, *, version_id: str = "") -> dict[str, Any]:
        return self.store.list_assets(version_id=version_id)

    def list_versions(self) -> dict[str, Any]:
        return {
            **self.store.list_versions(),
            "release_readiness": self.store.release_readiness(),
        }

    def release_readiness(self, *, version_id: str = "") -> dict[str, Any]:
        return self.store.release_readiness(data_version_id=version_id)

    def publish_version(self, *, task_id: str) -> dict[str, Any]:
        readiness = self.store.release_readiness()
        if readiness["status"] != "ready":
            raise ValueError("data version release is blocked by unresolved quality remediation")
        job = self.scheduler.get_job(task_id, include_items=False)
        if job.get("status") != "published" or not job.get("data_version_id"):
            raise ValueError("only a quality-gated published sync task can be promoted")
        return {
            "status": "already_published",
            "task_id": task_id,
            "data_version_id": job["data_version_id"],
            "quality_report_id": job.get("quality_report_id"),
        }

    def set_default_version(self, version_id: str) -> dict[str, Any]:
        current = self.governance_store.fetch_current_published_data_version()
        if str(current.get('data_version_id') or '') != str(version_id):
            raise ValueError('历史记录没有物理快照，不能切换为当前数据；请重新更新')
        return self.store.set_default_version(version_id)

    def _live_probe(self, route: Mapping[str, Any]) -> dict[str, Any]:
        provider = self.scheduler.governance_provider
        if provider is None:
            raise RuntimeError("configured provider does not expose governance probes")
        source_id = str(route.get("source_id") or route.get("provider") or "")
        dataset = str(route["dataset"])
        endpoint = str(route["endpoint"])
        today = date.today()
        start = (today - timedelta(days=45)).isoformat()
        end = today.isoformat()
        if source_id == "akshare":
            if endpoint == "stock_info_a_code_name":
                probe_catalog = getattr(provider, "probe_symbol_catalog", provider.list_symbols)
                rows = probe_catalog()
            elif endpoint == "stock_zh_a_hist":
                rows = provider.fetch_daily_prices(
                    symbol="000001", adjustment="raw", start_date=start, end_date=end,
                )
            elif endpoint == "tool_trade_date_hist_sina":
                rows = provider.fetch_trade_calendar(start_date=start, end_date=end)
            elif endpoint == "index_zh_a_hist":
                rows = provider.fetch_index_daily_prices(
                    index_symbol="000300", start_date=start, end_date=end,
                )
            elif endpoint == "index_us_stock_sina":
                rows = provider.fetch_global_index_daily_prices(
                    index_symbol="SPX", endpoint=endpoint,
                    start_date=start, end_date=end,
                )
            elif endpoint == "index_global_hist_sina":
                rows = provider.fetch_global_index_daily_prices(
                    index_symbol="FTSE", endpoint=endpoint,
                    start_date=start, end_date=end,
                )
            elif endpoint == "stock_fhps_em":
                rows = provider.fetch_corporate_actions(symbol="000001")
            elif endpoint == "index_stock_cons_csindex":
                snapshot = provider.fetch_index_component_snapshot(index_code="000300")
                rows = list(snapshot.get("rows") or [])
            elif endpoint == "stock_individual_info_em":
                rows = provider.fetch_security_lifecycle_events(symbol="000001")
            elif endpoint in {
                "stock_board_industry_hist_em", "stock_board_concept_hist_em",
                "stock_board_industry_fund_flow_hist", "stock_board_concept_fund_flow_hist",
                "stock_notice_report_and_news",
            }:
                rows = self._probe_panorama_route(
                    endpoint=endpoint, start_date=start, end_date=end,
                )
            else:
                raise NotImplementedError(
                    f"live probe is not implemented for {source_id}/{dataset}/{endpoint}"
                )
        elif source_id == "akshare_ths":
            rows = self._probe_ths_route(endpoint=endpoint, start_date=start, end_date=end)
        elif source_id == "cninfo":
            rows = self._probe_cninfo_route(endpoint=endpoint, end_date=end)
        else:
            raise NotImplementedError(
                f"live probe is not implemented for {source_id}/{dataset}/{endpoint}"
            )
        records = list(rows or [])
        return {"row_count": len(records), "first_row": records[0] if records else None}

    def _probe_panorama_route(
        self, *, endpoint: str, start_date: str, end_date: str,
    ) -> list[dict[str, Any]]:
        panorama = self.panorama_service
        if panorama is None:
            raise RuntimeError("market panorama provider is unavailable")
        if endpoint == "stock_notice_report_and_news":
            return list(panorama._fetch_events("000001", end_date, start_date=start_date))
        dimension = "industry" if "industry" in endpoint else "concept"
        item = (
            {"board_code": "BK0475", "board_name": "银行"}
            if dimension == "industry"
            else {"board_code": "BK0816", "board_name": "5G概念"}
        )
        if "fund_flow" in endpoint:
            return list(panorama._fetch_fund_flow(dimension, item, end_date))
        rows = list(panorama._fetch_board_daily_range(
            dimension, item, start_date, end_date, allow_fallback=False,
        ))
        fallback_rows = [
            row for row in rows
            if not str(row.get("source") or "").startswith("eastmoney.")
        ]
        if fallback_rows:
            raise RuntimeError(
                f"configured eastmoney route used fallback source: {fallback_rows[0].get('source')}"
            )
        return rows

    def _probe_ths_route(
        self, *, endpoint: str, start_date: str, end_date: str,
    ) -> list[dict[str, Any]]:
        panorama = self.panorama_service
        provider = getattr(panorama, "ths_board_provider", None) if panorama else None
        if provider is None:
            raise RuntimeError("THS board provider is unavailable")
        dimension = "industry" if "industry" in endpoint else "concept"
        catalog = list(provider.fetch_catalog(dimension))
        if endpoint.endswith("_name_ths"):
            return catalog
        if not endpoint.endswith("_index_ths"):
            raise NotImplementedError(f"live probe is not implemented for akshare_ths/{endpoint}")
        if not catalog:
            raise RuntimeError(f"empty THS {dimension} board catalog")
        frame = provider.fetch_index(
            dimension,
            board_name=str(catalog[0]["board_name"]),
            board_code=str(catalog[0]["board_code"]),
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        return list(frame.to_dict("records"))

    def _probe_cninfo_route(self, *, endpoint: str, end_date: str) -> list[dict[str, Any]]:
        panorama = self.panorama_service
        provider = getattr(panorama, "cninfo_provider", None) if panorama else None
        if provider is None:
            raise RuntimeError("CNInfo provider is unavailable")
        if endpoint == "stock_industry_category_cninfo":
            return list(provider.fetch_industry_categories())
        if endpoint == "stock_industry_change_cninfo":
            return list(provider.fetch_industry_intervals("000001", "1990-01-01", end_date))
        if endpoint == "stock_share_change_cninfo":
            return list(provider.fetch_share_changes("000001", "2020-01-01", end_date))
        if endpoint == "announcement_search":
            return list(provider.fetch_announcements("000001", "2020-01-01", end_date))
        raise NotImplementedError(f"live probe is not implemented for cninfo/{endpoint}")

    @staticmethod
    def _classify_probe_error(error: Exception) -> tuple[str, str, bool]:
        text = f"{type(error).__name__}: {error}".lower()
        mappings = (
            ("not implemented", "PROBE_NOT_IMPLEMENTED", "implementation", False),
            ("provider is unavailable", "PROBE_PROVIDER_UNAVAILABLE", "implementation", False),
            ("failure when receiving data from the peer", "UPSTREAM_CONNECTION_RESET", "transport", True),
            ("connection reset", "UPSTREAM_CONNECTION_RESET", "transport", True),
            ("peer reset", "UPSTREAM_CONNECTION_RESET", "transport", True),
            ("timeout", "UPSTREAM_TIMEOUT", "timeout", True),
            ("timed out", "UPSTREAM_TIMEOUT", "timeout", True),
            ("name resolution", "DNS_FAILURE", "dns", True),
            ("certificate", "TLS_FAILURE", "tls", False),
            ("401", "AUTHENTICATION_FAILED", "authentication", False),
            ("403", "UPSTREAM_FORBIDDEN", "authorization", False),
            ("429", "UPSTREAM_RATE_LIMITED", "rate_limit", True),
            ("json", "RESPONSE_PARSE_FAILED", "parsing", True),
        )
        for needle, code, error_class, retryable in mappings:
            if needle in text:
                return code, error_class, retryable
        return "UPSTREAM_PROBE_FAILED", "transport", True

    @staticmethod
    def _health(overview: Mapping[str, Any]) -> str:
        issue_counts = dict(overview.get("issue_counts") or {})
        if issue_counts.get("open", 0) or issue_counts.get("quarantined", 0):
            return "needs_attention"
        if overview.get("default_version") is None:
            return "unpublished"
        return "healthy"
