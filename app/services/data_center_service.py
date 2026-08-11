"""Stage-86 data-center application service."""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from data_platform.a_share_sync_scheduler import AShareSyncScheduler
from data_platform.quality_scan_engine import QualityScanEngine
from data_platform.storage.a_share_governance_store import AShareGovernanceStore
from data_platform.storage.data_center_store import DataCenterStore


class DataCenterService:
    """Aggregate existing market governance behind the stage-86 API contract."""

    def __init__(
        self,
        store: DataCenterStore,
        scheduler: AShareSyncScheduler,
        governance_store: AShareGovernanceStore,
        sync_worker_launcher: Any | None = None,
        panorama_service: Any | None = None,
    ) -> None:
        self.store = store
        self.scheduler = scheduler
        self.governance_store = governance_store
        self._sync_worker_launcher = sync_worker_launcher or self._launch_sync_worker
        self.panorama_service = panorama_service
        self._sync_processes: dict[str, subprocess.Popen[str]] = {}
        self._sync_process_lock = threading.Lock()
        self._sync_previews: dict[str, dict[str, Any]] = {}
        self._sync_preview_lock = threading.Lock()
        self.quality_scan_engine = QualityScanEngine(store.database_path, scheduler)
        self._quality_scan_threads: dict[str, threading.Thread] = {}
        self._quality_scan_lock = threading.Lock()
        self.store.ensure_schema()

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
    def latest_sync_target(self) -> dict[str, Any]:
        return self.scheduler.latest_sync_target()


    def list_sources(self) -> list[dict[str, Any]]:
        return self.store.list_sources()

    def get_source(self, source_id: str) -> dict[str, Any]:
        return self.store.get_source(source_id)

    def update_source(self, source_id: str, update: Mapping[str, Any]) -> dict[str, Any]:
        return self.store.update_source(source_id, update)

    def test_source(self, source_id: str, *, live: bool = False) -> dict[str, Any]:
        source = self.store.get_source(source_id)
        if source["verification_status"] != "verified" or not source["enabled"]:
            return {
                "source_id": source_id, "status": "disabled", "writes": 0,
                "message": "????????????????",
            }
        route = next((item for item in self.store.list_routes() if item.get("source_id") == source_id and item["enabled"]), None)
        if route is None:
            raise ValueError("verified source has no enabled controlled route")
        return {"source_id": source_id, **self.test_route(route["route_id"], live=live)}

    def list_datasets(self) -> list[dict[str, Any]]:
        return self.store.list_datasets()

    def list_routes(self) -> list[dict[str, Any]]:
        return self.store.list_routes()

    def update_routes(self, routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return self.store.update_routes(routes)

    def test_route(self, route_id: str, *, live: bool = False) -> dict[str, Any]:
        route = self.store.get_route(route_id)
        result: dict[str, Any] = {
            "route_id": route_id,
            "dataset": route["dataset"],
            "endpoint": route["endpoint"],
            "mode": "contract_only",
            "writes": 0,
            "status": "ready",
        }
        if not live:
            result["message"] = "route contract validated; set live=true for a lightweight upstream read"
            return result
        started = time.monotonic()
        try:
            sample = self._live_probe(route)
        except Exception as error:
            latency = int((time.monotonic() - started) * 1000)
            message = f"{type(error).__name__}: {error}"
            self.store.record_route_probe(route_id, succeeded=False, latency_ms=latency, error=message)
            return {**result, "status": "failed", "mode": "live_read", "latency_ms": latency, "error": message}
        latency = int((time.monotonic() - started) * 1000)
        self.store.record_route_probe(route_id, succeeded=True, latency_ms=latency)
        return {**result, "status": "passed", "mode": "live_read", "latency_ms": latency, "sample": sample}

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
                 "priority": row["priority"], "fallback_policy": row.get("fallback_policy")}
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
            job = self.scheduler.create_job(
                target_trade_date=target_trade_date, symbols=symbols or None,
                all_current=all_current, adjustments=adjustments, mode="data_center",
                selected_shards=selected_shards,
                start_floor=start_trade_date or "2015-01-05",
                gap_scan=mode == "historical_gap",
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
            return self.panorama_service.start_job(task_id)
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
            return self.panorama_service.retry_job(task_id, run_now=run_now)
        job = self.scheduler.retry_quarantined(task_id)
        return self.run_sync_task(task_id) if run_now else job

    def _usable_routes(self, dataset_id: str) -> list[dict[str, Any]]:
        sources = {source["source_id"]: source for source in self.store.list_sources()}
        routes = [
            route for route in self.store.list_routes()
            if route["dataset"] == dataset_id and route["enabled"]
            and sources.get(str(route.get("source_id")), {}).get("enabled")
            and sources.get(str(route.get("source_id")), {}).get("verification_status") == "verified"
        ]
        if not routes:
            raise ValueError(f"dataset has no enabled verified route: {dataset_id}")
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
            return self.panorama_service.get_job(task_id)
        return self.scheduler.get_job(task_id, include_items=False)

    def get_sync_task_items(self, task_id: str) -> list[dict[str, Any]]:
        if task_id.startswith("panorama-sync-"):
            task = self.get_sync_task(task_id)
            return list(task.get("items") or [])
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
        history["refetches"] = reconciled
        return history

    def disposition_quality_issue(
        self, issue_id: str, *, action: str, reason: str, operator: str,
        before: Mapping[str, Any] | None, after: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return self.store.disposition_issue(
            issue_id, action=action, reason=reason, operator=operator,
            before=before, after=after,
        )

    def bulk_disposition_quality_issues(
        self, issue_ids: Sequence[str], *, action: str, reason: str, operator: str,
    ) -> dict[str, Any]:
        items = self.store.bulk_disposition_issues(
            issue_ids, action=action, reason=reason, operator=operator,
        )
        return {"processed_count": len(items), "items": items}

    def _validate_quality_refetch_issue(self, issue: Mapping[str, Any]) -> None:
        if str(issue.get("status")) not in {"open", "quarantined"}:
            raise ValueError(f"quality issue is already resolved: {issue.get('issue_id')}")
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
        if dataset == "a_share_daily":
            evidence = dict(issue.get("evidence") or {})
            rule_id = str(issue.get("rule_id") or "")
            adjustments = [str(evidence.get("adjustment") or "raw")]
            start_floor = target
            gap_scan = False
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
            )
        else:
            symbols = [symbol] if dataset == "events" and symbol else []
            job = self.panorama_service.create_job(
                datasets=[dataset], target_trade_date=target, symbols=symbols,
            )
        task_id = str(job["job_id"])
        snapshot = self.store.freeze_route_snapshot(dataset, task_id=task_id)
        refetch = self.store.record_refetch(issue_id, task_id)
        if run_now:
            job = self.run_sync_task(task_id)
            self.store.update_refetch(str(refetch["refetch_id"]), status=str(job.get("status") or "running"))
        return {**refetch, "job": job, "route_snapshot_id": snapshot["snapshot_id"]}

    def bulk_refetch_quality_issues(
        self, issue_ids: Sequence[str], *, reason: str, operator: str, run_now: bool = False,
    ) -> dict[str, Any]:
        ids = list(dict.fromkeys(str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip()))
        if not ids:
            raise ValueError("at least one quality issue is required")
        if len(ids) > 50:
            raise ValueError("at most 50 quality issues can be refetched at once")
        if not reason.strip():
            raise ValueError("bulk refetch reason is required")
        if run_now:
            raise ValueError("bulk refetch can only create queued tasks; run them after review")
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

    def list_assets(self, *, version_id: str = "") -> dict[str, Any]:
        return self.store.list_assets(version_id=version_id)

    def list_versions(self) -> dict[str, Any]:
        return self.store.list_versions()

    def publish_version(self, *, task_id: str) -> dict[str, Any]:
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
        return self.store.set_default_version(version_id)

    def _live_probe(self, route: Mapping[str, Any]) -> dict[str, Any]:
        provider = self.scheduler.governance_provider
        if provider is None:
            raise RuntimeError("configured provider does not expose governance probes")
        dataset = str(route["dataset"])
        today = date.today()
        start = (today - timedelta(days=10)).isoformat()
        end = today.isoformat()
        if dataset == "a_share_catalog":
            rows = provider.list_symbols()
        elif dataset == "trade_calendar":
            rows = provider.fetch_trade_calendar(start_date=start, end_date=end)
        elif dataset == "index_daily":
            rows = provider.fetch_index_daily_prices(
                index_symbol="000300", start_date=start, end_date=end
            )
        else:
            raise RuntimeError("live probe is not enabled for this route in stage 86")
        sample = list(rows[:1]) if isinstance(rows, list) else []
        return {"row_count": len(rows), "first_row": sample[0] if sample else None}

    @staticmethod
    def _health(overview: Mapping[str, Any]) -> str:
        issue_counts = dict(overview.get("issue_counts") or {})
        if issue_counts.get("open", 0) or issue_counts.get("quarantined", 0):
            return "needs_attention"
        if overview.get("default_version") is None:
            return "unpublished"
        return "healthy"
