"""Governed, persistent factor-analysis application service."""

from __future__ import annotations
from data_platform.maintenance_transaction import guarded_research, require_current_input

import json
import re
import sqlite3
import threading
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from factor_lab.research_core import (
    build_factor_report,
    calculate_factor_definition,
    canonical_hash,
    list_research_factor_definitions,
    preprocess_cross_section,
    spearman,
)
from factor_lab.expression_factor import validate_expression
from factor_lab.optimization import optimize_fixed_artifact
from factor_lab.strategy_export import build_strategy_factor_declaration
from factor_lab.storage.sqlite_research_store import SqliteFactorResearchStore
from data_platform.research_data_version import ResearchDataVersionResolver


_ALLOWED_HORIZONS = {1, 5, 10, 20}
_ALLOWED_ADJUSTMENTS = {"raw", "qfq", "hfq"}
_ALLOWED_INDEX_CODES = {
    "000300.XSHG",
    "000905.XSHG",
    "000906.XSHG",
    "000852.XSHG",
    "000985.XSHG",
}
_REQUIRED_CONTEXT_DATASETS = (
    "market_trade_calendar",
    "security_lifecycle_events",
    "security_trading_status_daily",
)
_FUJING_V7_UNIVERSE_POLICY = "fujing_v7_point_in_time"
_DEFAULT_UNIVERSE_POLICY = "observed_price_with_lifecycle"
_FUJING_V7_EXCLUDED_PREFIXES = ("688", "689", "8", "43", "83", "87", "92", "900", "200")
_FACTOR_ACCEPTANCE_POLICY_V1 = {
    "policy_id": "factor-acceptance-v1",
    "version": 1,
    "minimum_factor_coverage": 0.80,
    "minimum_independent_periods": 60,
    "minimum_direction_aligned_rank_ic": 0.02,
    "minimum_rank_ic_hac_t_value": 1.96,
    "minimum_positive_rank_ic_ratio": 0.55,
    "minimum_net_return_estimate": 0.0,
    "maximum_drawdown_floor": -0.50,
    "sample_split": {"training": 0.60, "validation": 0.20, "out_of_sample": 0.20},
}


class FactorAnalysisService:
    """Run independent factor research against immutable local data releases."""

    def __init__(
        self,
        *,
        market_database_path: str | Path,
        research_store: SqliteFactorResearchStore | None = None,
        classification_store: Any | None = None,
    ) -> None:
        self._market_database_path = Path(market_database_path)
        self._data_version_resolver = ResearchDataVersionResolver(
            self._market_database_path
        )
        self._store = research_store or SqliteFactorResearchStore()
        self._classifications = classification_store
        self._optimization_threads: dict[str, threading.Thread] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._store.save_definitions(list_research_factor_definitions())

    def list_definitions(self) -> dict[str, Any]:
        return {
            "status": "ready",
            "items": self._store.list_definitions(),
            "capabilities": self.capabilities(),
        }

    def list_r3_studies(self) -> dict[str, Any]:
        """Expose external, frozen R3 evidence without making it strategy-eligible."""
        root = self._market_database_path.parent.parent / "research"
        candidates = (root / "r3-standard-v1-20260914-verified", root / "r3-standard-v1-20260914")
        result_file = next((p / "results.json" for p in candidates if (p / "results.json").is_file()), None)
        if result_file is None:
            return {"status": "empty", "items": [], "message": "尚未生成 R3 研究证据"}
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            return {"status": "unavailable", "items": [], "message": f"R3 证据读取失败：{type(error).__name__}"}
        items = []
        for factor_id, item in dict(payload.get("factors") or {}).items():
            holdout = dict(item.get("holdout") or {})
            items.append({
                "factor_id": factor_id,
                "name": item.get("name") or factor_id,
                "status": "研究完成·未验收",
                "accepted": bool(item.get("accepted")),
                "holdout": {
                    "periods": holdout.get("periods"),
                    "known_periods": holdout.get("known_periods"),
                    "mean_net_excess": holdout.get("mean_net_excess"),
                    "mean_stress_excess": holdout.get("mean_stress_excess"),
                    "rank_ic": holdout.get("mean_rank_ic_complete_fills_only"),
                    "unknown_exits": holdout.get("unknown_exit_observations"),
                    "holm_p": holdout.get("holm_p"),
                },
                "source": str(result_file.relative_to(self._market_database_path.parent.parent)),
                "data_version_id": payload.get("data_version_id"),
            })
        return {"status": "ready", "items": items, "accepted_patterns": payload.get("accepted_patterns", 0),
                "sample_count": payload.get("sample_count"), "message": "仅供研究查看；未注册为策略可用因子"}

    def get_definition(
        self, factor_id: str, factor_version: str | None = None,
    ) -> dict[str, Any]:
        definition = self._resolve_definition(factor_id, factor_version)
        return {
            "status": "ready",
            "definition": definition,
            "versions": [
                item for item in self._store.list_definitions(latest_only=False)
                if item.get("factor_id") == definition["factor_id"]
            ],
            "capabilities": self.capabilities(),
        }

    def validate_definition(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        factor_id = _factor_id(raw.get("factor_id"))
        name = str(raw.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("name must contain 1 to 80 characters")
        direction = str(raw.get("direction") or "positive").strip().lower()
        if direction not in {"positive", "negative"}:
            raise ValueError("direction must be positive or negative")
        validation = validate_expression(str(raw.get("expression") or ""))
        return {
            "status": "valid",
            "definition": {
                "factor_id": factor_id,
                "name": name,
                "category": str(raw.get("category") or "自定义").strip()[:40] or "自定义",
                "description": str(raw.get("description") or "").strip()[:500],
                "direction": direction,
                "definition_type": "expression",
                "expression": validation["expression"],
                "formula": validation["expression"],
                "input_fields": validation["input_fields"],
                "minimum_history": validation["minimum_history"],
                "parameters": {},
                "stage": "87.3-controlled-expression",
                "status": "draft",
                "expression_hash": canonical_hash(validation["expression"]),
            },
            "validation": validation,
            "capabilities": self.capabilities(),
        }

    def create_definition(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        validated = self.validate_definition(raw)
        definition = dict(validated["definition"])
        existing = [
            item for item in self._store.list_definitions(latest_only=False)
            if item.get("factor_id") == definition["factor_id"]
        ]
        if any(item.get("definition_type") == "builtin" for item in existing):
            raise ValueError("built-in factor_id cannot be replaced")
        next_version = max(
            [_factor_version_number(item.get("factor_version")) for item in existing] or [0]
        ) + 1
        definition["factor_version"] = f"v{next_version}"
        definition["status"] = "frozen"
        created = self._store.create_definition(definition)
        return {
            "status": "frozen",
            "definition": created,
            "validation": validated["validation"],
            "capabilities": self.capabilities(),
        }

    def _resolve_definition(
        self, factor_id: str, factor_version: str | None = None,
    ) -> dict[str, Any]:
        normalized = _factor_id(factor_id)
        definition = self._store.get_definition(normalized, factor_version)
        if definition is None:
            suffix = f" version={factor_version}" if factor_version else ""
            raise ValueError(f"unsupported factor_id: {normalized}{suffix}")
        if definition.get("status") not in {"published", "frozen"}:
            raise ValueError("factor definition is not frozen")
        return definition

    def capabilities(self) -> dict[str, Any]:
        classification = (
            self._classifications.coverage()
            if self._classifications is not None
            and hasattr(self._classifications, "coverage")
            else {"status": "unavailable", "dimensions": {}}
        )
        index_coverage = self._store.index_component_coverage()
        industry = dict(classification.get("dimensions") or {}).get("industry") or {}
        return {
            "p0_factor_research": {"status": "ready", "stage": "87.1"},
            "governed_research": {
                "status": "ready",
                "modes": ["exploratory", "governed"],
                "acceptance_policy": _FACTOR_ACCEPTANCE_POLICY_V1,
                "exploratory_strategy_eligible": False,
            },
            "controlled_expression_factors": {
                "status": "ready",
                "stage": "87.3",
                "fields": ["open", "high", "low", "close", "volume", "amount"],
                "functions": ["lag", "mean", "std", "min", "max", "abs"],
                "immutable_versions": True,
            },
            "industry_neutralization": {
                "status": "ready" if int(industry.get("symbol_count") or 0) > 0 else "unavailable",
                "reason": None if int(industry.get("symbol_count") or 0) > 0 else "industry_facts_unavailable",
                "coverage": industry,
            },
            "index_pools": index_coverage,
            "pool_comparison": {"status": "ready", "stage": "87.2"},
            "execution_estimate": {"status": "ready", "stage": "87.2", "estimate_only": True},
            "factor_optimization": {
                "status": "ready",
                "stage": "FA-OPT-0-3",
                "business_name": "parameter_sensitivity_analysis",
                "artifact_binding": "immutable_exact_id",
                "artifact_gate": "approved_and_registered",
                "default_value_field": "aligned_value",
                "explicit_start_required": True,
                "market_data_access": "none",
            },
            "strategy_factor_export": {
                "status": "ready",
                "artifact_binding": "immutable_exact_id",
                "artifact_gate": "approved_and_registered",
                "default_value_field": "aligned_value",
                "execution_policy": "explicit_start_required",
                "writes": 0,
            },
            "multi_factor_research": {
                "status": "ready",
                "methods": ["equal_rank", "fixed_weight_rank"],
                "component_gate": "approved_registered_same_context",
                "evidence": ["correlation", "redundancy", "out_of_sample", "ablation", "incremental_contribution"],
            },
            "post_release_monitoring": {
                "status": "ready",
                "checks": ["content_hash", "source_task", "data_version", "coverage", "rank_ic_decay"],
            },
            "external_sync": {"status": "disabled", "reason": "research_endpoints_are_read_only_to_market_data"},
        }

    def preflight(self, raw_config: Mapping[str, Any]) -> dict[str, Any]:
        config = _normalize_config(raw_config)
        definition = self._resolve_definition(
            config["factor_id"], config.get("factor_version")
        )
        config["factor_version"] = definition["factor_version"]
        if definition.get("required_adjustment") and config["factor_adjustment"] != definition["required_adjustment"]:
            raise ValueError("指标衍生因子的复权口径与原指标配置不一致")
        version = self._resolve_data_version(
            data_version_id=config.get("data_version_id"),
            factor_adjustment=config["factor_adjustment"],
            outcome_adjustment=config["outcome_adjustment"],
            universe_policy=config["universe_policy"],
        )
        if version["status"] != "ready":
            return _preflight_unavailable(config, version["reason"], evidence={"data_version": version})

        requested = config["requested_range"]
        effective_start = max(
            [requested["start_date"]]
            + [str(item.get("min_date") or requested["start_date"]) for item in version["required_members"]]
        )
        coverage_end = min(
            [str(item.get("max_date") or requested["end_date"]) for item in version["required_members"]]
        )
        if effective_start > min(requested["end_date"], coverage_end):
            return _preflight_unavailable(
                config,
                "required_dataset_coverage_does_not_overlap_requested_range",
                evidence={"data_version": version},
            )
        trade_dates = self._trade_dates(effective_start, coverage_end)
        requested_trade_dates = [item for item in trade_dates if item <= requested["end_date"]]
        max_horizon = max(config["forward_horizons"])
        if len(trade_dates) <= max_horizon or not requested_trade_dates:
            return _preflight_unavailable(
                config,
                "not_enough_trade_dates_for_forward_return",
                evidence={"data_version": version, "trade_date_count": len(trade_dates)},
            )
        last_with_outcome = trade_dates[-(max_horizon + 1)]
        effective_end = min(requested["end_date"], last_with_outcome)
        if effective_start > effective_end:
            return _preflight_unavailable(
                config,
                "not_enough_forward_outcome_coverage",
                evidence={"data_version": version, "last_factor_date": last_with_outcome},
            )

        pool = self._resolve_pool(
            config,
            effective_start=effective_start,
            effective_end=effective_end,
        )
        if pool["status"] != "ready":
            return _preflight_unavailable(
                config,
                str(pool.get("reason") or "pool_unavailable"),
                evidence={"data_version": version, "pool": pool},
            )

        if config["preprocessing"]["industry_neutral"]:
            industry_capability = self.capabilities()["industry_neutralization"]
            if industry_capability["status"] != "ready":
                return _preflight_unavailable(
                    config,
                    "industry_facts_unavailable",
                    evidence={
                        "data_version": version,
                        "pool": pool,
                        "industry": industry_capability,
                    },
                )

        pool_snapshot = {
            "pool_type": config["pool_type"],
            "universe_policy": config["universe_policy"],
            "pool_code": config.get("pool_code"),
            "as_of_date": config["pool_as_of_date"],
            "symbols": pool["symbols"],
            "source": pool["source"],
            "source_version": pool.get("source_version"),
            "point_in_time_policy": pool["point_in_time_policy"],
            "membership_intervals": pool.get("membership_intervals", []),
        }
        pool_snapshot["content_hash"] = canonical_hash(pool_snapshot)
        effective_range = {
            "start_date": effective_start,
            "end_date": effective_end,
            "outcome_coverage_end": coverage_end,
        }
        effective_trade_dates = [
            item for item in trade_dates if effective_start <= item <= effective_end
        ]
        frozen_sample_split = _freeze_factor_sample_split(
            effective_trade_dates,
            mode=config["research_mode"],
            ratios=config["sample_split"],
        )
        context = {
            "factor_id": definition["factor_id"],
            "factor_version": definition["factor_version"],
            "definition_hash": canonical_hash(definition),
            "expression_hash": definition.get("expression_hash"),
            "parameters": definition["parameters"],
            "pool_type": config["pool_type"],
            "universe_policy": config["universe_policy"],
            "pool_code": config.get("pool_code"),
            "pool_as_of_policy": pool["point_in_time_policy"],
            "pool_snapshot_hash": pool_snapshot["content_hash"],
            "data_version_id": version["data_version_id"],
            "quality_report_id": version["quality_report_id"],
            "requested_range": requested,
            "effective_range": effective_range,
            "factor_adjustment": config["factor_adjustment"],
            "outcome_adjustment": config["outcome_adjustment"],
            "forward_horizons": config["forward_horizons"],
            "preprocessing": config["preprocessing"],
            "group_count": config["group_count"],
            "rebalance_frequency": config["rebalance_frequency"],
            "cost_assumption": config["cost_assumption"],
            "research_mode": config["research_mode"],
            "sample_split": frozen_sample_split,
            "acceptance_policy_id": config["acceptance_policy_id"],
            "acceptance_policy_hash": canonical_hash(_FACTOR_ACCEPTANCE_POLICY_V1),
        }
        context_hash = canonical_hash(context)
        reasons: list[str] = []
        if effective_start != requested["start_date"] or effective_end != requested["end_date"]:
            reasons.append("effective_range_clipped_to_required_dataset_intersection")
        return {
            "status": "ready",
            "capabilities": self.capabilities(),
            "config": config,
            "context": context,
            "context_hash": context_hash,
            "data_version": version,
            "requested_range": requested,
            "effective_range": effective_range,
            "pool_snapshot": pool_snapshot,
            "evidence": {
                "market_database": str(self._market_database_path.resolve()),
                "market_database_access": "read_only",
                "required_members": version["required_members"],
                "pool_member_count": len(pool_snapshot["symbols"]),
                "trade_date_count": len(
                    effective_trade_dates
                ),
                "sample_split": frozen_sample_split,
                "acceptance_policy": _FACTOR_ACCEPTANCE_POLICY_V1,
            },
            "reasons": reasons,
        }

    @guarded_research
    def create_task(self, raw_config: Mapping[str, Any]) -> dict[str, Any]:
        preflight = self.preflight(raw_config)
        if preflight["status"] != "ready":
            raise ValueError(
                "factor research preflight unavailable: "
                + ",".join(preflight.get("reasons") or ["unknown"])
            )
        task_id = _normalize_id(
            str(raw_config.get("task_id") or f"factor-{uuid4().hex[:12]}")
        )
        config = dict(preflight["config"])
        return self._store.create_task(
            task_id=task_id,
            config=config,
            context=preflight["context"],
            context_hash=str(preflight["context_hash"]),
            preflight=preflight,
            data_version_id=str(preflight["data_version"]["data_version_id"]),
            quality_report_id=str(preflight["data_version"]["quality_report_id"]),
            pool_snapshot=preflight["pool_snapshot"],
        )

    def start_task(self, task_id: str, *, wait: bool = False) -> dict[str, Any]:
        task = self._store.get_task(task_id)
        if task["status"] == "not_found":
            return task
        if task["status"] in {"completed", "running", "stop_requested"}:
            return task
        if task["status"] not in {
            "ready",
            "failed",
            "partial_completed",
            "interrupted",
            "stopped",
        }:
            raise ValueError(f"task cannot start from status: {task['status']}")
        with self._lock:
            active = self._threads.get(task_id)
            if active is None or not active.is_alive():
                thread = threading.Thread(
                    target=self._execute_task,
                    args=(task_id,),
                    name=f"factor-research-{task_id}",
                    daemon=True,
                )
                self._threads[task_id] = thread
                thread.start()
                active = thread
        if wait:
            active.join()
        return self._store.get_task(task_id)

    def stop_task(self, task_id: str) -> dict[str, Any]:
        task = self._store.get_task(task_id)
        if task["status"] == "not_found":
            return task
        if task["status"] in {"completed", "failed", "stopped"}:
            return task
        if task["status"] == "running":
            self._store.update_task(task_id, status="stop_requested")
        else:
            self._store.update_task(
                task_id,
                status="stopped",
                finished_at=_utc_now(),
                progress_json=_dump(
                    {**dict(task.get("progress") or {}), "phase": "stopped"}
                ),
            )
        return self._store.get_task(task_id)

    def retry_failed(self, task_id: str, *, wait: bool = False) -> dict[str, Any]:
        task = self._store.get_task(task_id)
        if task["status"] == "not_found":
            return task
        if task["status"] not in {
            "failed",
            "partial_completed",
            "interrupted",
            "stopped",
        }:
            raise ValueError("only failed, partial, interrupted or stopped tasks can retry")
        self._store.update_task(
            task_id,
            status="ready",
            error_json="{}",
            progress_json=_dump(
                {
                    **dict(task.get("progress") or {}),
                    "resume_requested": True,
                }
            ),
            finished_at=None,
        )
        return self.start_task(task_id, wait=wait)

    def list_tasks(self, *, status: str = "", limit: int = 50) -> dict[str, Any]:
        items = self._store.list_tasks(status=status, limit=limit)
        return {
            "status": "ready",
            "items": items,
            "summary": {
                "total": len(items),
                "status_counts": _status_counts(items),
            },
            "capabilities": self.capabilities(),
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._store.get_task(task_id)

    def get_report(self, report_id: str) -> dict[str, Any]:
        report = self._store.get_report(report_id)
        if report.get("status") != "ready":
            return report
        payload = dict(report.get("payload") or {})
        artifact = self._store.get_artifact_for_task(str(report.get("task_id") or ""))
        if artifact.get("status") != "not_found":
            payload["artifact"] = artifact
            credibility = dict(payload.get("credibility") or {})
            credibility["factor_artifact_id"] = artifact.get("artifact_id")
            payload["credibility"] = credibility
        reveal = self._store.get_out_of_sample_reveal(report_id)
        if str(payload.get("config", {}).get("research_mode") or "") == "governed":
            payload["oos_reveal"] = reveal
            if reveal.get("status") != "revealed":
                payload = _seal_out_of_sample_payload(payload)
        return {**report, "payload": payload}

    def reveal_out_of_sample(
        self, report_id: str, *, reason: str, actor: str,
    ) -> dict[str, Any]:
        normalized_reason = str(reason or "").strip()
        normalized_actor = str(actor or "").strip()
        if not normalized_reason:
            raise ValueError("out-of-sample reveal reason is required")
        if not normalized_actor:
            raise ValueError("out-of-sample reveal actor is required")
        report = self._store.get_report(str(report_id).strip())
        if report.get("status") != "ready":
            raise ValueError("factor report not found")
        payload = dict(report.get("payload") or {})
        if str(payload.get("config", {}).get("research_mode") or "") != "governed":
            raise ValueError("exploratory research has no sealed out-of-sample segment")
        reveal = self._store.reveal_out_of_sample(
            str(report_id).strip(), actor=normalized_actor, reason=normalized_reason,
        )
        return {"status": "ready", "reveal": reveal, "report": self.get_report(report_id)}

    def list_artifacts(self, *, factor_id: str = "", limit: int = 100) -> dict[str, Any]:
        items = self._store.list_artifacts(factor_id=factor_id, limit=limit)
        return {
            "status": "ready",
            "items": items,
            "summary": {"total": len(items), "factor_id": factor_id or None},
        }

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        return self._store.get_artifact(artifact_id)

    def get_artifact_governance(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._store.get_artifact(str(artifact_id).strip())
        if artifact.get("status") == "not_found":
            return artifact
        return {
            "status": "ready",
            "artifact": artifact,
            "governance": self._store.get_artifact_governance(str(artifact_id).strip()),
        }

    def review_artifact(
        self, artifact_id: str, *, decision: str, note: str, reviewer: str,
    ) -> dict[str, Any]:
        normalized_note = str(note or "").strip()
        normalized_reviewer = str(reviewer or "").strip()
        if not normalized_note:
            raise ValueError("factor review note is required")
        if not normalized_reviewer:
            raise ValueError("factor reviewer is required")
        artifact = self._store.get_artifact(str(artifact_id).strip())
        if artifact.get("status") not in {"research_ready", "ready"}:
            raise ValueError("factor artifact is not research-ready")
        task = self._store.get_task(str(artifact.get("source_task_id") or ""))
        if task.get("status") != "completed" or not task.get("report_id"):
            raise ValueError("factor research task is not completed")
        report = self.get_report(str(task["report_id"]))
        payload = dict(report.get("payload") or {})
        acceptance = dict(payload.get("acceptance") or {})
        if str(decision).strip().lower() == "approved":
            reveal = self._store.get_out_of_sample_reveal(str(task["report_id"]))
            if reveal.get("status") != "revealed":
                raise ValueError("out-of-sample evidence must be explicitly revealed before review")
            if str(payload.get("config", {}).get("research_mode") or "") != "governed":
                raise ValueError("exploratory research cannot be approved")
            if acceptance.get("decision") != "approved":
                raise ValueError("factor acceptance policy did not approve this artifact")
        governance = self._store.review_artifact(
            str(artifact_id).strip(),
            decision=str(decision).strip().lower(),
            policy_id=str(acceptance.get("policy_id") or ""),
            reviewer=normalized_reviewer,
            note=normalized_note,
        )
        return {"status": "ready", "artifact": self._store.get_artifact(artifact_id), "governance": governance}

    def register_artifact(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._store.get_artifact(str(artifact_id).strip())
        task = self._store.get_task(str(artifact.get("source_task_id") or ""))
        if task.get("status") != "completed":
            raise ValueError("only completed research artifacts can be registered")
        governance = self._store.register_artifact(str(artifact_id).strip())
        return {
            "status": "ready",
            "artifact": self._store.get_artifact(str(artifact_id).strip()),
            "governance": governance,
        }

    def suspend_artifact(self, artifact_id: str, *, note: str) -> dict[str, Any]:
        normalized_note = str(note or "").strip()
        if not normalized_note:
            raise ValueError("suspension note is required")
        governance = self._store.suspend_artifact(str(artifact_id).strip(), note=normalized_note)
        return {
            "status": "ready",
            "artifact": self._store.get_artifact(str(artifact_id).strip()),
            "governance": governance,
        }

    def create_multi_factor_research(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        artifact_ids = list(dict.fromkeys(
            str(item).strip() for item in raw.get("artifact_ids") or [] if str(item).strip()
        ))
        if len(artifact_ids) < 2:
            raise ValueError("multi-factor research requires at least two artifact_ids")
        method = str(raw.get("method") or "equal_rank").strip().lower()
        if method not in {"equal_rank", "fixed_weight_rank"}:
            raise ValueError("multi-factor method must be equal_rank or fixed_weight_rank")
        factor_id = _factor_id(raw.get("factor_id"))
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError("multi-factor name is required")
        artifacts = [self._store.get_artifact(item) for item in artifact_ids]
        for artifact in artifacts:
            if artifact.get("status") != "ready":
                raise ValueError("multi-factor components must be approved and registered")
            self._store.require_artifact_registration(str(artifact["artifact_id"]))
        source_tasks = [
            self._store.get_task(str(artifact["source_task_id"])) for artifact in artifacts
        ]
        source_reports = [
            self.get_report(str(task.get("report_id") or "")) for task in source_tasks
        ]
        comparison_contexts = [
            _factor_comparison_context(dict(report.get("payload") or {}))
            for report in source_reports
        ]
        comparison_hashes = {canonical_hash(item) for item in comparison_contexts}
        if len(comparison_hashes) != 1:
            raise ValueError("multi-factor component research contexts are incompatible")
        weights = _normalize_composite_weights(
            raw.get("weights") or [], count=len(artifacts), method=method,
        )
        existing = [
            item for item in self._store.list_definitions(latest_only=False)
            if item.get("factor_id") == factor_id
        ]
        if any(item.get("definition_type") != "composite" for item in existing):
            raise ValueError("factor_id is already used by a non-composite definition")
        factor_version = f"v{max([_factor_version_number(item.get('factor_version')) for item in existing] or [0]) + 1}"
        recipe = {
            "method": method,
            "component_artifact_ids": artifact_ids,
            "component_factor_ids": [str(item["factor_id"]) for item in artifacts],
            "weights": weights,
            "ranking": "cross_section_percentile_centered",
        }
        definition = self._store.create_definition({
            "factor_id": factor_id,
            "factor_version": factor_version,
            "name": name[:80],
            "category": "多因子",
            "description": str(raw.get("description") or "").strip()[:500],
            "direction": "positive",
            "definition_type": "composite",
            "formula": " + ".join(
                f"{weight:.8g}*rank({artifact['factor_id']}@{artifact['artifact_id']})"
                for weight, artifact in zip(weights, artifacts, strict=True)
            ),
            "input_fields": [],
            "minimum_history": max(
                int(dict(report.get("payload") or {}).get("definition", {}).get("minimum_history") or 1)
                for report in source_reports
            ),
            "parameters": {"recipe": recipe},
            "stage": "multi-factor-v1",
            "status": "frozen",
            "recipe_hash": canonical_hash(recipe),
        })
        base_task = source_tasks[0]
        base_report_payload = dict(source_reports[0].get("payload") or {})
        base_config = dict(base_task.get("config") or {})
        config = {
            **base_config,
            "factor_id": factor_id,
            "factor_version": factor_version,
            "name": name[:80],
            "research_mode": "governed",
            "composite_recipe": recipe,
        }
        context = {
            **dict(base_task.get("context") or {}),
            "factor_id": factor_id,
            "factor_version": factor_version,
            "definition_hash": canonical_hash(definition),
            "expression_hash": None,
            "parameters": definition["parameters"],
            "composite_recipe": recipe,
            "component_context_hashes": [str(item.get("context_hash") or "") for item in artifacts],
        }
        context_hash = canonical_hash(context)
        task_id = f"factor-multi-{uuid4().hex[:12]}"
        pool_snapshot_wrapper = next(
            (
                item for item in base_task.get("snapshots") or []
                if item.get("snapshot_type") == "pool"
            ),
            None,
        )
        if not pool_snapshot_wrapper:
            raise ValueError("multi-factor source pool snapshot is unavailable")
        pool_snapshot = dict(pool_snapshot_wrapper.get("payload") or {})
        preflight = {
            **dict(base_task.get("preflight") or {}),
            "status": "ready",
            "config": config,
            "context": context,
            "context_hash": context_hash,
            "reasons": [],
        }
        self._store.create_task(
            task_id=task_id,
            config=config,
            context=context,
            context_hash=context_hash,
            preflight=preflight,
            data_version_id=str(base_task["data_version_id"]),
            quality_report_id=str(base_task["quality_report_id"]),
            pool_snapshot=pool_snapshot,
        )
        self._store.update_task(
            task_id, status="running", started_at=_utc_now(),
            progress_json=_dump({"phase": "composite_alignment", "percent": 20.0}),
        )
        component_values = [
            {
                (str(row["trade_date"]), str(row["symbol"])): float(row["aligned_value"])
                for row in self._store.fetch_artifact_values(str(artifact["artifact_id"]))
                if row.get("aligned_value") is not None
            }
            for artifact in artifacts
        ]
        common_keys = set(component_values[0])
        for values in component_values[1:]:
            common_keys &= set(values)
        if not common_keys:
            raise ValueError("multi-factor components have no aligned observations in common")
        base_observations = {
            (str(row["trade_date"]), str(row["symbol"])): row
            for row in self._store.fetch_observations(str(base_task["task_id"]))
        }
        rank_maps = _component_rank_maps(component_values, common_keys)
        observations = _composite_observations(
            common_keys, rank_maps, weights, base_observations,
            component_artifact_ids=artifact_ids,
        )
        self._store.append_observations(task_id, observations)
        universe_counts = dict(base_report_payload.get("analysis", {}).get("coverage") or {})
        universe_by_date = {
            str(item["trade_date"]): int(item.get("universe_count") or 0)
            for item in universe_counts.get("series") or []
        }
        self._store.add_universe_counts(task_id, universe_by_date)
        analysis = build_factor_report(
            observations=observations,
            universe_count_by_date=universe_by_date,
            horizons=config["forward_horizons"],
            group_count=config["group_count"],
            direction="positive",
            cost_rate=float(config["cost_assumption"]["one_side_rate"]),
        )
        for row in observations:
            if row.get("group_no") is not None:
                self._store.update_group_numbers(task_id, [row])
        analysis["sample_analysis"] = _sample_analysis_for_observations(
            observations,
            universe_by_date=universe_by_date,
            sample_split=dict(context.get("sample_split") or {}),
            horizons=config["forward_horizons"],
            group_count=config["group_count"],
            cost_rate=float(config["cost_assumption"]["one_side_rate"]),
        )
        analysis["multi_factor"] = _multi_factor_evidence(
            component_values=component_values,
            common_keys=common_keys,
            artifact_ids=artifact_ids,
            factor_ids=[str(item["factor_id"]) for item in artifacts],
            weights=weights,
            observations=observations,
            base_observations=base_observations,
            rank_maps=rank_maps,
            source_reports=source_reports,
            universe_by_date=universe_by_date,
            context=context,
            config=config,
        )
        primary_horizon = int(config["forward_horizons"][0])
        acceptance = _evaluate_factor_acceptance(
            analysis, mode="governed", primary_horizon=primary_horizon,
            policy=_FACTOR_ACCEPTANCE_POLICY_V1,
        )
        acceptance = _apply_multi_factor_acceptance(acceptance, analysis, primary_horizon)
        report_id = f"factor-report-{task_id}"
        report_payload = {
            "status": "ready",
            "task_id": task_id,
            "definition": definition,
            "config": config,
            "context": context,
            "context_hash": context_hash,
            "data_version": base_report_payload.get("data_version"),
            "requested_range": context.get("requested_range"),
            "effective_range": context.get("effective_range"),
            "evidence": {
                "market_database_access": "none",
                "component_artifact_ids": artifact_ids,
                "component_content_hashes": [item["content_hash"] for item in artifacts],
                "common_observation_count": len(observations),
                "recipe_hash": definition["recipe_hash"],
            },
            "analysis": analysis,
            "acceptance": acceptance,
            "artifact": {"status": "pending_publication", "source_task_id": task_id},
            "credibility": {
                "evidence_level": "historical_multi_factor_research_only",
                "conclusion_scope": "fixed composite factor evidence; not a trading recommendation",
                "data_version_id": base_task["data_version_id"],
                "quality_report_id": base_task["quality_report_id"],
                "factor_artifact_id": None,
                "execution_model": "symmetric top-bottom membership turnover with fixed one-side cost",
                "market_impact_model": "not modeled",
                "paper_or_live_validation": "not performed",
            },
            "reasons": [],
        }
        self._store.save_report(
            report_id=report_id, task_id=task_id, context_hash=context_hash,
            payload=report_payload,
        )
        artifact = self._store.publish_artifact(task_id)
        self._store.update_task(
            task_id,
            status="completed",
            report_id=report_id,
            finished_at=_utc_now(),
            progress_json=_dump({
                "phase": "completed", "percent": 100.0,
                "observation_count": len(observations),
                "component_count": len(artifacts),
            }),
        )
        return {
            "status": "ready",
            "task": self._store.get_task(task_id),
            "report": self.get_report(report_id),
            "artifact": artifact,
        }

    def monitor_artifact(self, artifact_id: str, *, lookback_periods: int = 22) -> dict[str, Any]:
        selected_lookback = max(5, min(int(lookback_periods), 252))
        artifact = self._store.get_artifact(str(artifact_id).strip())
        if artifact.get("status") == "not_found":
            raise ValueError("factor artifact not found")
        governance = self._store.get_artifact_governance(
            str(artifact_id).strip(), include_events=False
        )
        if governance.get("review_status") != "approved" or governance.get(
            "registration_status"
        ) not in {"registered", "suspended"}:
            raise ValueError("only approved factor artifacts can be monitored")
        task = self._store.get_task(str(artifact.get("source_task_id") or ""))
        report = self.get_report(str(task.get("report_id") or ""))
        payload = dict(report.get("payload") or {})
        analysis = dict(payload.get("analysis") or {})
        horizon = str((payload.get("config", {}).get("forward_horizons") or [5])[0])
        primary = dict(analysis.get("ic") or {}).get(horizon, {}) or {}
        recent_ic_rows = [
            item for item in primary.get("series") or []
            if _float_or_none(item.get("direction_aligned_rank_ic")) is not None
        ][-selected_lookback:]
        recent_ic_values = [
            float(item["direction_aligned_rank_ic"]) for item in recent_ic_rows
        ]
        recent_rank_ic = (
            sum(recent_ic_values) / len(recent_ic_values) if recent_ic_values else None
        )
        baseline_rank_ic = _float_or_none(primary.get("direction_aligned_rank_ic_mean"))
        coverage_rows = list(dict(analysis.get("coverage") or {}).get("series") or [])[
            -selected_lookback:
        ]
        coverage_values = [
            float(item["factor_coverage"])
            for item in coverage_rows
            if _float_or_none(item.get("factor_coverage")) is not None
        ]
        recent_coverage = sum(coverage_values) / len(coverage_values) if coverage_values else None
        config = dict(task.get("config") or {})
        try:
            data_version = self._resolve_data_version(
                data_version_id=str(artifact.get("data_version_id") or ""),
                factor_adjustment=str(config.get("factor_adjustment") or "raw"),
                outcome_adjustment=str(config.get("outcome_adjustment") or "qfq"),
                universe_policy=str(config.get("universe_policy") or _DEFAULT_UNIVERSE_POLICY),
            )
        except Exception as error:  # noqa: BLE001 - monitoring records the dependency failure
            data_version = {"status": "unavailable", "reason": str(error)[:500]}
        checks = [
            {
                "check": "artifact_content_hash",
                "status": "passed" if governance.get("artifact_content_hash") == artifact.get("content_hash") else "critical",
            },
            {
                "check": "source_task",
                "status": "passed" if task.get("status") == "completed" else "critical",
                "actual": task.get("status"),
            },
            {
                "check": "data_version_dependency",
                "status": "passed" if data_version.get("status") == "ready" else "critical",
                "actual": data_version.get("status"),
                "reason": data_version.get("reason"),
            },
            {
                "check": "recent_factor_coverage",
                "status": (
                    "passed" if recent_coverage is not None
                    and recent_coverage >= _FACTOR_ACCEPTANCE_POLICY_V1["minimum_factor_coverage"]
                    else "warning"
                ),
                "actual": recent_coverage,
                "threshold": _FACTOR_ACCEPTANCE_POLICY_V1["minimum_factor_coverage"],
            },
            {
                "check": "recent_direction_aligned_rank_ic",
                "status": (
                    "passed" if recent_rank_ic is not None
                    and recent_rank_ic > 0
                    and (baseline_rank_ic is None or recent_rank_ic >= baseline_rank_ic * 0.5)
                    else "warning"
                ),
                "actual": recent_rank_ic,
                "baseline": baseline_rank_ic,
            },
        ]
        if any(item["status"] == "critical" for item in checks):
            status = "action_required"
            recommended_action = "suspend_new_use_and_create_new_version_research"
        elif any(item["status"] == "warning" for item in checks):
            status = "review_required"
            recommended_action = "manual_review"
        else:
            status = "healthy"
            recommended_action = "continue_monitoring"
        snapshot_payload = {
            "artifact_id": artifact_id,
            "artifact_content_hash": artifact.get("content_hash"),
            "registration_status": governance.get("registration_status"),
            "lookback_periods": selected_lookback,
            "latest_evidence_date": recent_ic_rows[-1].get("trade_date") if recent_ic_rows else None,
            "checks": checks,
            "recommended_action": recommended_action,
            "monitoring_boundary": "frozen artifact evidence; new market data requires a new factor version research task",
        }
        snapshot = self._store.save_monitoring_snapshot(
            str(artifact_id).strip(), status=status, payload=snapshot_payload,
        )
        return {"status": status, "snapshot": snapshot, "artifact": artifact}

    def list_artifact_monitoring(self, artifact_id: str, *, limit: int = 20) -> dict[str, Any]:
        return {
            "status": "ready",
            "artifact_id": artifact_id,
            "items": self._store.list_monitoring_snapshots(artifact_id, limit=limit),
        }

    def export_strategy_factor_declaration(self, artifact_id: str) -> dict[str, Any]:
        artifact = self._store.get_artifact(str(artifact_id).strip())
        if artifact.get("status") != "ready":
            raise ValueError(f"ready factor artifact not found: {artifact_id}")
        self._store.require_artifact_registration(str(artifact_id).strip())
        task = self._store.get_task(str(artifact.get("source_task_id") or ""))
        if task.get("status") == "not_found":
            raise ValueError("factor artifact source task is unavailable")
        values = self._store.fetch_artifact_values(str(artifact["artifact_id"]))
        missing_aligned = sum(item.get("aligned_value") is None for item in values)
        if not values or missing_aligned:
            raise ValueError(
                "factor artifact cannot use default aligned_value: "
                f"missing {missing_aligned} of {len(values)} rows"
            )
        result = build_strategy_factor_declaration(artifact, task)
        result["coverage"] = {
            "start_date": artifact.get("start_date"),
            "end_date": artifact.get("end_date"),
            "row_count": len(values),
            "aligned_value_count": len(values) - missing_aligned,
        }
        result["capabilities"] = self.capabilities()
        return result

    def preflight_optimization(self, raw_config: Mapping[str, Any]) -> dict[str, Any]:
        config = _normalize_optimization_config(raw_config)
        artifact = self._store.get_artifact(config["artifact_id"])
        if artifact.get("status") != "ready":
            raise ValueError("factor optimization requires a ready artifact_id")
        values = self._store.fetch_artifact_values(config["artifact_id"])
        observations = self._store.fetch_observations(str(artifact["source_task_id"]))
        observation_map = {
            (str(row["trade_date"]), str(row["symbol"])): row for row in observations
        }
        usable_count = sum(
            1
            for row in values
            if row.get(config["value_field"]) is not None
            and (str(row["trade_date"]), str(row["symbol"])) in observation_map
        )
        if usable_count == 0:
            raise ValueError("artifact has no values with source research observations")
        source_task = self._store.get_task(str(artifact["source_task_id"]))
        source_horizons = [
            int(item)
            for item in dict(source_task.get("config") or {}).get("forward_horizons") or []
        ]
        if not config["forward_horizons"]:
            config["forward_horizons"] = source_horizons or [5]
        unavailable = sorted(set(config["forward_horizons"]) - set(source_horizons))
        if unavailable:
            raise ValueError(
                "forward_horizons are not frozen in the source artifact task: "
                + ",".join(str(item) for item in unavailable)
            )
        context = {
            "artifact_id": str(artifact["artifact_id"]),
            "artifact_content_hash": str(artifact["content_hash"]),
            "source_task_id": str(artifact["source_task_id"]),
            "factor_id": str(artifact["factor_id"]),
            "factor_version": str(artifact["factor_version"]),
            "data_version_id": str(artifact["data_version_id"]),
            "quality_report_id": str(artifact["quality_report_id"]),
            "value_field": config["value_field"],
            "forward_horizons": config["forward_horizons"],
            "group_counts": config["group_counts"],
            "one_side_rates": config["one_side_rates"],
            "min_cross_section_size": config["min_cross_section_size"],
        }
        context_hash = canonical_hash(context)
        return {
            "status": "ready",
            "config": config,
            "context": context,
            "context_hash": context_hash,
            "artifact": artifact,
            "evidence": {
                "artifact_binding": "immutable_exact_id",
                "artifact_value_count": len(values),
                "usable_observation_count": usable_count,
                "source_forward_horizons": source_horizons,
                "market_database_access": "none",
                "explicit_start_required": True,
            },
            "capabilities": self.capabilities(),
        }

    def create_optimization_task(
        self, raw_config: Mapping[str, Any]
    ) -> dict[str, Any]:
        preflight = self.preflight_optimization(raw_config)
        config = dict(preflight["config"])
        task_id = _normalize_id(
            str(config.get("task_id") or f"fa-opt-{uuid4().hex[:12]}")
        )
        return self._store.create_optimization_task(
            task_id=task_id,
            artifact=preflight["artifact"],
            value_field=str(config["value_field"]),
            config=config,
            context=preflight["context"],
            context_hash=str(preflight["context_hash"]),
        )

    def start_optimization_task(
        self, task_id: str, *, wait: bool = False
    ) -> dict[str, Any]:
        task = self._store.get_optimization_task(task_id)
        if task["status"] == "not_found":
            return task
        if task["status"] in {"completed", "running"}:
            return task
        if task["status"] not in {"ready", "failed", "interrupted"}:
            raise ValueError(f"optimization task cannot start from status: {task['status']}")
        with self._lock:
            active = self._optimization_threads.get(task_id)
            if active is None or not active.is_alive():
                thread = threading.Thread(
                    target=self._execute_optimization_task,
                    args=(task_id,),
                    name=f"factor-optimization-{task_id}",
                    daemon=True,
                )
                self._optimization_threads[task_id] = thread
                thread.start()
                active = thread
        if wait:
            active.join()
        return self._store.get_optimization_task(task_id)

    def retry_optimization_task(
        self, task_id: str, *, wait: bool = False
    ) -> dict[str, Any]:
        task = self._store.get_optimization_task(task_id)
        if task["status"] == "not_found":
            return task
        if task["status"] not in {"failed", "interrupted"}:
            raise ValueError("only failed or interrupted optimization tasks can retry")
        self._store.update_optimization_task(
            task_id,
            status="ready",
            progress_json=_dump({"phase": "ready", "percent": 0.0}),
            error_json="{}",
            finished_at=None,
        )
        return self.start_optimization_task(task_id, wait=wait)

    def list_optimization_tasks(
        self, *, status: str = "", limit: int = 50
    ) -> dict[str, Any]:
        items = self._store.list_optimization_tasks(status=status, limit=limit)
        return {
            "status": "ready",
            "items": items,
            "summary": {"total": len(items), "status_counts": _status_counts(items)},
            "capabilities": self.capabilities(),
        }

    def get_optimization_task(self, task_id: str) -> dict[str, Any]:
        return self._store.get_optimization_task(task_id)

    def get_optimization_report(self, report_id: str) -> dict[str, Any]:
        return self._store.get_optimization_report(report_id)

    def _execute_optimization_task(self, task_id: str) -> None:
        task = self._store.get_optimization_task(task_id)
        self._store.update_optimization_task(
            task_id,
            status="running",
            started_at=_utc_now(),
            finished_at=None,
            error_json="{}",
            progress_json=_dump({"phase": "loading_artifact", "percent": 10.0}),
        )
        try:
            artifact = self._store.get_artifact(str(task["artifact_id"]))
            if artifact.get("status") != "ready":
                raise ValueError("frozen factor artifact is no longer ready")
            if str(artifact.get("content_hash")) != str(task["artifact_content_hash"]):
                raise ValueError("frozen factor artifact content hash changed")
            values = self._store.fetch_artifact_values(str(task["artifact_id"]))
            observations = self._store.fetch_observations(str(task["source_task_id"]))
            observation_map = {
                (str(row["trade_date"]), str(row["symbol"])): row
                for row in observations
            }
            rows = [
                {
                    **dict(value),
                    "forward_returns": dict(
                        observation_map.get(
                            (str(value["trade_date"]), str(value["symbol"])), {}
                        ).get("forward_returns")
                        or {}
                    ),
                }
                for value in values
            ]
            self._store.update_optimization_task(
                task_id,
                progress_json=_dump(
                    {
                        "phase": "candidate_evaluation",
                        "artifact_value_count": len(values),
                        "percent": 50.0,
                    }
                ),
            )
            config = dict(task["config"])
            result = optimize_fixed_artifact(
                rows,
                value_field=str(task["value_field"]),
                forward_horizons=config["forward_horizons"],
                group_counts=config["group_counts"],
                one_side_rates=config["one_side_rates"],
                min_cross_section_size=int(config["min_cross_section_size"]),
            )
            report_id = f"factor-optimization-report-{task_id}"
            payload = {
                "status": "ready",
                "task_id": task_id,
                "artifact": {
                    "artifact_id": artifact["artifact_id"],
                    "content_hash": artifact["content_hash"],
                    "factor_id": artifact["factor_id"],
                    "factor_version": artifact["factor_version"],
                    "data_version_id": artifact["data_version_id"],
                    "quality_report_id": artifact["quality_report_id"],
                },
                "value_field": task["value_field"],
                "config": config,
                "context": task["context"],
                "context_hash": task["context_hash"],
                "optimization": result,
                "credibility": {
                    "evidence_level": "historical_research_only",
                    "artifact_binding": "immutable_exact_id",
                    "market_data_access": "none",
                    "paper_or_live_validation": "not performed",
                    "disclaimer": "local factor research only; not investment advice",
                },
            }
            self._store.save_optimization_report(
                report_id=report_id,
                task_id=task_id,
                artifact_id=str(task["artifact_id"]),
                context_hash=str(task["context_hash"]),
                payload=payload,
            )
            self._store.update_optimization_task(
                task_id,
                status="completed",
                report_id=report_id,
                finished_at=_utc_now(),
                progress_json=_dump(
                    {
                        "phase": "completed",
                        "artifact_value_count": len(values),
                        "candidate_count": result["candidate_count"],
                        "percent": 100.0,
                    }
                ),
            )
        except Exception as error:  # noqa: BLE001 - task boundary persists diagnostics
            self._store.update_optimization_task(
                task_id,
                status="failed",
                finished_at=_utc_now(),
                error_json=_dump(
                    {
                        "stage": "factor_optimization",
                        "code": "factor_optimization_execution_failed",
                        "type": type(error).__name__,
                        "message": str(error)[:2000],
                        "retryable": True,
                    }
                ),
            )


    def dashboard(
        self, *, factor_id: str = "", pool_type: str = "", context_id: str = "",
    ) -> dict[str, Any]:
        definitions = self._store.list_definitions()
        reports = self._store.list_reports()
        eligible_reports = [
            report for report in reports
            if not pool_type
            or report.get("payload", {}).get("config", {}).get("pool_type") == pool_type
        ]
        contexts: list[dict[str, Any]] = []
        seen_contexts: set[str] = set()
        for report in eligible_reports:
            comparison = _factor_comparison_context(report.get("payload") or {})
            comparison_id = canonical_hash(comparison)[:20]
            if comparison_id in seen_contexts:
                continue
            seen_contexts.add(comparison_id)
            contexts.append(
                {
                    "context_id": comparison_id,
                    "label": _factor_comparison_context_label(comparison),
                    "context": comparison,
                    "latest_report_id": report.get("report_id"),
                }
            )
        selected_context_id = context_id or (contexts[0]["context_id"] if contexts else "")
        if selected_context_id and selected_context_id not in seen_contexts:
            selected_context_id = contexts[0]["context_id"] if contexts else ""
        rows: list[dict[str, Any]] = []
        for definition in definitions:
            if factor_id and definition["factor_id"] != factor_id:
                continue
            candidates = [
                report
                for report in reports
                if report.get("payload", {}).get("definition", {}).get("factor_id")
                == definition["factor_id"]
                and report in eligible_reports
                and (
                    not selected_context_id
                    or canonical_hash(_factor_comparison_context(report.get("payload") or {}))[:20]
                    == selected_context_id
                )
            ]
            latest = candidates[0] if candidates else None
            analysis = dict(latest.get("payload", {}).get("analysis") or {}) if latest else {}
            primary = (
                dict(analysis.get("ic") or {}).get(
                    str(latest.get("payload", {}).get("config", {}).get("forward_horizons", [5])[0])
                )
                if latest
                else None
            ) or {}
            rows.append(
                {
                    **definition,
                    "latest_report_id": latest.get("report_id") if latest else None,
                    "latest_status": "ready" if latest else "not_run",
                    "rank_ic_mean": primary.get("rank_ic_mean"),
                    "direction_aligned_rank_ic_mean": primary.get(
                        "direction_aligned_rank_ic_mean"
                    ),
                    "icir": primary.get("icir"),
                    "factor_coverage": dict(analysis.get("coverage") or {}).get(
                        "average_factor_coverage"
                    ),
                    "max_drawdown": dict(analysis.get("group_analysis") or {}).get(
                        "max_drawdown"
                    ),
                    "turnover": _latest_top_turnover(analysis),
                }
            )
        return {
            "status": "ready",
            "items": rows,
            "filters": {
                "factor_id": factor_id,
                "pool_type": pool_type,
                "context_id": selected_context_id,
                "contexts": contexts,
                "supported_pool_types": ["all_a", "index"],
                "supported_index_codes": sorted(_ALLOWED_INDEX_CODES),
            },
            "capabilities": self.capabilities(),
        }

    def compare_reports(
        self,
        report_id: str,
        comparison_report_ids: Sequence[str],
    ) -> dict[str, Any]:
        base = self._store.get_report(report_id)
        if base["status"] == "not_found":
            return base
        selected = [base]
        for other_id in comparison_report_ids:
            item = self._store.get_report(str(other_id))
            if item["status"] == "ready":
                selected.append(item)
        base_payload = dict(base["payload"])
        base_context = dict(base_payload.get("context") or {})
        comparable: list[dict[str, Any]] = []
        incompatible: list[dict[str, Any]] = []
        identity_fields = (
            "factor_id",
            "factor_version",
            "data_version_id",
            "requested_range",
            "effective_range",
            "forward_horizons",
            "preprocessing",
            "factor_adjustment",
            "outcome_adjustment",
            "group_count",
            "rebalance_frequency",
            "cost_assumption",
        )
        for item in selected:
            payload = dict(item["payload"])
            context = dict(payload.get("context") or {})
            mismatches = [
                field for field in identity_fields
                if context.get(field) != base_context.get(field)
            ]
            summary = {
                "report_id": item["report_id"],
                "pool_type": payload.get("config", {}).get("pool_type"),
                "pool_code": payload.get("config", {}).get("pool_code"),
                "context_hash": item["context_hash"],
                "rank_ic_mean": _primary_metric(payload, "rank_ic_mean"),
                "icir": _primary_metric(payload, "icir"),
                "factor_coverage": payload.get("analysis", {})
                .get("coverage", {})
                .get("average_factor_coverage"),
                "final_nav": payload.get("analysis", {})
                .get("group_analysis", {})
                .get("final_nav"),
                "net_return_estimate": payload.get("analysis", {})
                .get("execution_estimate", {})
                .get("net_return_estimate"),
            }
            if mismatches:
                incompatible.append({**summary, "mismatches": mismatches})
            else:
                comparable.append(summary)
        return {
            "status": "ready",
            "base_report_id": report_id,
            "items": comparable,
            "incompatible": incompatible,
            "comparison_contract": {
                "identity_fields": list(identity_fields),
                "allowed_difference": ["pool_type", "pool_code", "pool_snapshot_hash"],
            },
        }

    def upsert_index_components(self, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        count = self._store.upsert_index_components(rows)
        return {
            "status": "ready",
            "written_count": count,
            "coverage": self._store.index_component_coverage(),
        }

    @guarded_research
    def _execute_task(self, task_id: str) -> None:
        task = self._store.get_task(task_id)
        config = dict(task.get("config") or {})
        context = dict(task.get("context") or {})
        pool_snapshot = next(
            (
                snapshot["payload"]
                for snapshot in task.get("snapshots", [])
                if snapshot.get("snapshot_type") == "pool"
            ),
            {},
        )
        symbols = list(pool_snapshot.get("symbols", []))
        membership_intervals = _index_intervals_by_symbol(
            pool_snapshot.get("membership_intervals", [])
        )
        self._store.update_task(
            task_id,
            status="running",
            started_at=_utc_now(),
            finished_at=None,
            error_json="{}",
        )
        try:
            definition = self._resolve_definition(
                config["factor_id"], config.get("factor_version")
            )
            require_current_input(self, task)
            effective = context["effective_range"]
            lookback_start = self._lookback_start(
                effective["start_date"], int(definition["minimum_history"])
            )
            if definition.get("definition_type") == "indicator":
                lookback_start = "1900-01-01"
            outcome_end = effective["outcome_coverage_end"]
            progress = dict(task.get("progress") or {})
            resumable = progress.get("streaming_contract") == "sqlite-batched-v1"
            phase = str(progress.get("phase") or "ready") if resumable else "ready"
            completed_symbols = (
                int(progress.get("processed_symbols") or 0)
                if phase in {"factor_calculation", "preprocessing", "report", "artifact"}
                else 0
            )
            if not resumable:
                self._store.clear_streaming_observations(task_id)
                progress = {}
                phase = "factor_calculation"
                completed_symbols = 0
            industry_intervals = self._load_industry_intervals(symbols)
            for offset in range(completed_symbols, len(symbols), 100):
                current = self._store.get_task(task_id)
                if current["status"] == "stop_requested":
                    self._store.update_task(
                        task_id,
                        status="stopped",
                        finished_at=_utc_now(),
                        progress_json=_dump(
                            {
                                **dict(current.get("progress") or {}),
                                "phase": "stopped",
                            }
                        ),
                    )
                    return
                batch = symbols[offset : offset + 100]
                factor_rows = self._load_prices(
                    batch,
                    adjustment=config["factor_adjustment"],
                    start_date=lookback_start,
                    end_date=effective["end_date"],
                    fields=tuple(definition.get("input_fields") or ["close"]),
                )
                outcome_rows = self._load_prices(
                    batch,
                    adjustment=config["outcome_adjustment"],
                    start_date=effective["start_date"],
                    end_date=outcome_end,
                    fields=("close",),
                )
                batch_universe: dict[str, int] = defaultdict(int)
                for symbol in batch:
                    raw_values = calculate_factor_definition(
                        definition, factor_rows.get(symbol, [])
                    )
                    outcomes = _forward_returns(
                        outcome_rows.get(symbol, []), config["forward_horizons"]
                    )
                    available_factor_dates = {
                        str(row["date"])
                        for row in factor_rows.get(symbol, [])
                        if effective["start_date"]
                        <= str(row["date"])
                        <= effective["end_date"]
                    }
                    for trade_date in available_factor_dates:
                        if self._symbol_in_pool_on_date(
                            config, membership_intervals, symbol, trade_date
                        ):
                            batch_universe[trade_date] += 1
                    symbol_observations: list[dict[str, Any]] = []
                    for trade_date, raw_value in raw_values.items():
                        if not (
                            effective["start_date"]
                            <= trade_date
                            <= effective["end_date"]
                        ):
                            continue
                        if not self._symbol_in_pool_on_date(
                            config, membership_intervals, symbol, trade_date
                        ):
                            continue
                        symbol_observations.append(
                            {
                                "trade_date": trade_date,
                                "symbol": symbol,
                                "raw_value": raw_value,
                                "forward_returns": outcomes.get(trade_date, {}),
                                "industry": _resolve_industry(
                                    industry_intervals.get(symbol, []), trade_date
                                ),
                            }
                        )
                    self._store.append_observations(task_id, symbol_observations)
                self._store.add_universe_counts(
                    task_id, batch_universe, batch_offset=offset,
                )
                processed_count = min(offset + len(batch), len(symbols))
                observation_count = self._store.observation_count(task_id)
                self._store.update_task(
                    task_id,
                    progress_json=_dump(
                        {
                            "streaming_contract": "sqlite-batched-v1",
                            "phase": "factor_calculation",
                            "total_symbols": len(symbols),
                            "processed_symbols": processed_count,
                            "observation_count": observation_count,
                            "percent": (
                                round(processed_count / len(symbols) * 100, 4)
                                if symbols
                                else 100.0
                            ),
                        }
                    ),
                )
            dates = self._store.observation_dates(task_id)
            last_preprocessed = (
                str(progress.get("last_preprocessed_date") or "")
                if phase == "preprocessing" else ""
            )
            for date_index, trade_date in enumerate(dates):
                if trade_date <= last_preprocessed:
                    continue
                current = self._store.get_task(task_id)
                if current["status"] == "stop_requested":
                    self._store.update_task(
                        task_id, status="stopped", finished_at=_utc_now(),
                        progress_json=_dump({
                            **dict(current.get("progress") or {}), "phase": "stopped",
                        }),
                    )
                    return
                rows = self._store.fetch_observations_for_date(task_id, trade_date)
                raw_map = {
                    str(row["symbol"]): float(row["raw_value"]) for row in rows
                }
                industries = {
                    str(row["symbol"]): str(row.get("industry") or "")
                    for row in rows
                }
                result = preprocess_cross_section(
                    raw_map,
                    industries=industries,
                    winsor_mad=float(
                        config["preprocessing"].get("winsor_mad") or 0.0
                    ),
                    industry_neutral=bool(
                        config["preprocessing"].get("industry_neutral")
                    ),
                    standardize=bool(
                        config["preprocessing"].get("standardize", True)
                    ),
                    direction=str(definition["direction"]),
                )
                processed_rows: list[dict[str, Any]] = []
                for source_row in rows:
                    symbol = str(source_row["symbol"])
                    row = dict(source_row)
                    row["processed_value"] = result["processed"].get(symbol)
                    row["aligned_value"] = result["aligned"].get(symbol)
                    row["evidence"] = {
                        "preprocessing_hash": result["content_hash"],
                        "preprocessing_status": result["status"],
                        "preprocessing_reason": result["reason"],
                        "preprocessing_steps": result["steps"],
                        "data_version_id": context["data_version_id"],
                    }
                    processed_rows.append(row)
                self._store.update_processed_observations(task_id, processed_rows)
                self._store.update_task(
                    task_id,
                    progress_json=_dump({
                        "streaming_contract": "sqlite-batched-v1",
                        "phase": "preprocessing",
                        "total_symbols": len(symbols),
                        "processed_symbols": len(symbols),
                        "observation_count": self._store.observation_count(task_id),
                        "processed_dates": date_index + 1,
                        "total_dates": len(dates),
                        "last_preprocessed_date": trade_date,
                        "percent": round((date_index + 1) / max(1, len(dates)) * 100, 4),
                    }),
                )
            universe_by_date = self._store.fetch_universe_counts(task_id)
            primary_horizon = int(config["forward_horizons"][0])
            industry_ic_summary: list[dict[str, Any]] = []
            for industry in self._store.observation_industries(task_id):
                industry_rows = self._store.industry_observations(task_id, industry)
                pairs = [
                    (float(row["aligned_value"]), float(value))
                    for row in industry_rows
                    if row.get("aligned_value") is not None
                    for value in [dict(row.get("forward_returns") or {}).get(str(primary_horizon))]
                    if value is not None
                ]
                industry_ic_summary.append({
                    "industry": industry,
                    "sample_count": len(pairs),
                    "rank_ic": spearman(
                        [item[0] for item in pairs], [item[1] for item in pairs]
                    ),
                })

            def report_batches():
                for trade_date in dates:
                    rows = self._store.fetch_observations_for_date(task_id, trade_date)
                    yield trade_date, rows
                    self._store.update_group_numbers(task_id, rows)

            observation_count = self._store.observation_count(task_id)
            self._store.update_task(
                task_id,
                progress_json=_dump({
                    "streaming_contract": "sqlite-batched-v1", "phase": "report",
                    "total_symbols": len(symbols), "processed_symbols": len(symbols),
                    "observation_count": observation_count, "percent": 100.0,
                }),
            )
            analysis = build_factor_report(
                universe_count_by_date=universe_by_date,
                horizons=config["forward_horizons"],
                group_count=config["group_count"],
                direction=definition["direction"],
                cost_rate=float(config["cost_assumption"]["one_side_rate"]),
                observation_batches=report_batches(),
                distribution_summary=self._store.processed_distribution(task_id),
                industry_ic_summary=industry_ic_summary,
                observation_count=observation_count,
            )
            sample_analysis: dict[str, Any] = {}
            for sample_name, sample_range in dict(
                context.get("sample_split", {}).get("segments") or {}
            ).items():
                sample_dates = [
                    item for item in dates
                    if str(sample_range.get("start_date") or "") <= item
                    <= str(sample_range.get("end_date") or "")
                ]
                if not sample_dates:
                    sample_analysis[sample_name] = {
                        "status": "unavailable", "reason": "sample_has_no_observations",
                    }
                    continue

                def sample_batches(selected_dates=tuple(sample_dates)):
                    for selected_date in selected_dates:
                        yield selected_date, self._store.fetch_observations_for_date(
                            task_id, selected_date
                        )

                sample_analysis[sample_name] = build_factor_report(
                    universe_count_by_date={
                        item: universe_by_date.get(item, 0) for item in sample_dates
                    },
                    horizons=config["forward_horizons"],
                    group_count=config["group_count"],
                    direction=definition["direction"],
                    cost_rate=float(config["cost_assumption"]["one_side_rate"]),
                    observation_batches=sample_batches(),
                )
            analysis["sample_analysis"] = sample_analysis
            acceptance = _evaluate_factor_acceptance(
                analysis,
                mode=str(config.get("research_mode") or "exploratory"),
                primary_horizon=primary_horizon,
                policy=_FACTOR_ACCEPTANCE_POLICY_V1,
            )
            preprocessing_evidence = []
            for trade_date in dates:
                rows = self._store.fetch_observations_for_date(task_id, trade_date)
                evidence = dict(rows[0].get("evidence") or {}) if rows else {}
                preprocessing_evidence.append({
                    "trade_date": trade_date,
                    "status": evidence.get("preprocessing_status"),
                    "reason": evidence.get("preprocessing_reason"),
                    "steps": evidence.get("preprocessing_steps") or [],
                    "content_hash": evidence.get("preprocessing_hash"),
                })
            report_id = f"factor-report-{task_id}"
            report_payload = {
                "status": "ready",
                "task_id": task_id,
                "definition": definition,
                "config": config,
                "context": context,
                "context_hash": task["context_hash"],
                "data_version": task["preflight"]["data_version"],
                "requested_range": context["requested_range"],
                "effective_range": context["effective_range"],
                "evidence": {
                    "market_database_access": "read_only",
                    "pool_snapshot": next(
                        (
                            snapshot
                            for snapshot in task.get("snapshots", [])
                            if snapshot.get("snapshot_type") == "pool"
                        ),
                        None,
                    ),
                    "preprocessing": preprocessing_evidence,
                    "observation_count": observation_count,
                    "streaming_contract": "sqlite-batched-v1",
                },
                "analysis": analysis,
                "acceptance": acceptance,
                "artifact": {"status": "pending_publication", "source_task_id": task_id},
                "credibility": {
                    "evidence_level": "historical_research_only",
                    "conclusion_scope": "factor screening evidence; not a trading recommendation",
                    "data_version_id": task["data_version_id"],
                    "quality_report_id": task["quality_report_id"],
                    "factor_artifact_id": None,
                    "execution_model": "symmetric top-bottom membership turnover with fixed one-side cost",
                    "market_impact_model": "not modeled",
                    "paper_or_live_validation": "not performed",
                    "limitations": [
                        "historical simulation cannot establish future performance",
                        "fixed transaction costs do not model liquidity or market impact",
                        "index universes require authorized point-in-time snapshots",
                    ],
                },
                "reasons": task["preflight"].get("reasons", []),
            }
            self._store.save_report(
                report_id=report_id,
                task_id=task_id,
                context_hash=str(task["context_hash"]),
                payload=report_payload,
            )
            self._store.update_task(
                task_id,
                progress_json=_dump({
                    "streaming_contract": "sqlite-batched-v1", "phase": "artifact",
                    "total_symbols": len(symbols), "processed_symbols": len(symbols),
                    "observation_count": observation_count, "percent": 100.0,
                }),
            )
            self._store.publish_artifact(task_id)
            self._store.update_task(
                task_id,
                status="completed",
                report_id=report_id,
                finished_at=_utc_now(),
                progress_json=_dump(
                    {
                        "phase": "completed",
                        "streaming_contract": "sqlite-batched-v1",
                        "total_symbols": len(symbols),
                        "processed_symbols": len(symbols),
                        "observation_count": observation_count,
                        "percent": 100.0,
                    }
                ),
            )
        except Exception as error:  # noqa: BLE001 - task boundary persists diagnostics
            current = self._store.get_task(task_id)
            processed = int(current.get("progress", {}).get("processed_symbols") or 0)
            status = "partial_completed" if processed > 0 else "failed"
            self._store.update_task(
                task_id,
                status=status,
                finished_at=_utc_now(),
                error_json=_dump(
                    {
                        "stage": str(current.get("progress", {}).get("phase") or "execution"),
                        "code": "factor_research_execution_failed",
                        "type": type(error).__name__,
                        "message": str(error)[:2000],
                        "retryable": True,
                    }
                ),
            )

    def _resolve_data_version(
        self,
        *,
        data_version_id: str | None,
        factor_adjustment: str,
        outcome_adjustment: str,
        universe_policy: str = _DEFAULT_UNIVERSE_POLICY,
    ) -> dict[str, Any]:
        requirements = [
            ("market_daily_prices", adjustment)
            for adjustment in sorted({factor_adjustment, outcome_adjustment})
        ]
        requirements.extend((dataset, "") for dataset in _REQUIRED_CONTEXT_DATASETS)
        if universe_policy == _FUJING_V7_UNIVERSE_POLICY:
            requirements.append(("security_master_intervals", ""))
        return self._data_version_resolver.resolve(
            data_version_id=data_version_id,
            required_members=requirements,
        )
    def _resolve_pool(
        self,
        config: Mapping[str, Any],
        *,
        effective_start: str,
        effective_end: str,
    ) -> dict[str, Any]:
        requested_symbols = sorted(
            {_symbol(item) for item in config.get("symbols") or [] if _symbol(item)}
        )
        if config["pool_type"] == "index":
            index = self._store.resolve_index_component_window(
                str(config["pool_code"]), effective_start, effective_end
            )
            if index["status"] != "ready":
                return index
            symbols = list(index["symbols"])
            membership_intervals = list(index["intervals"])
            source: Any = index.get("source")
            source_version: Any = index.get("source_version")
            policy = "effective_interval_by_trade_date"
        elif config["universe_policy"] == _FUJING_V7_UNIVERSE_POLICY:
            governed = self._resolve_fujing_v7_point_in_time_pool(
                data_version_id=str(config.get("data_version_id") or ""),
                adjustment=str(config["factor_adjustment"]),
                start_date=effective_start,
                end_date=effective_end,
            )
            if governed["status"] != "ready":
                return governed
            symbols = list(governed["symbols"])
            membership_intervals = list(governed["membership_intervals"])
            source = "security_master_intervals"
            source_version = str(config.get("data_version_id") or "")
            policy = _FUJING_V7_UNIVERSE_POLICY
        else:
            membership_intervals = []
            symbols = requested_symbols or self._symbols_with_price_coverage(
                adjustment=str(config["factor_adjustment"]),
                start_date=effective_start,
                end_date=effective_end,
            )
            source = "canonical_a_share_sqlite.market_daily_prices"
            source_version = config.get("data_version_id") or "global_default_version"
            policy = "observed_price_on_trade_date_with_lifecycle_boundary"
        if requested_symbols:
            requested_set = set(requested_symbols)
            symbols = [symbol for symbol in symbols if symbol in requested_set]
        symbol_limit = int(config.get("symbol_limit") or 0)
        if symbol_limit > 0:
            symbols = symbols[:symbol_limit]
        if not symbols:
            return {
                "status": "unavailable",
                "reason": "pool_has_no_locally_covered_members",
                "symbols": [],
            }
        return {
            "status": "ready",
            "symbols": symbols,
            "source": source,
            "source_version": source_version,
            "point_in_time_policy": policy,
            "membership_intervals": [
                row for row in membership_intervals
                if str(row.get("symbol") or "") in set(symbols)
            ],
        }

    def _resolve_fujing_v7_point_in_time_pool(
        self,
        *,
        data_version_id: str,
        adjustment: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        if not data_version_id:
            return {"status": "unavailable", "reason": "point_in_time_pool_requires_data_version"}
        with closing(self._market_connect()) as connection:
            member = connection.execute(
                """
                SELECT m.sync_run_ref, m.details_json
                FROM data_version_members m
                JOIN data_versions v ON v.data_version_id=m.data_version_id
                WHERE m.data_version_id=? AND m.dataset='security_master_intervals'
                  AND m.adjustment='' AND m.quality_status='passed'
                  AND v.status IN ('published','superseded')
                """,
                (data_version_id,),
            ).fetchone()
            if member is None:
                return {"status": "unavailable", "reason": "point_in_time_security_master_not_published"}
            try:
                details = json.loads(str(member["details_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                return {"status": "unavailable", "reason": "point_in_time_snapshot_refs_invalid"}
            snapshot_refs = {
                str(item) for item in dict(details).get("snapshot_refs") or [] if str(item)
            }
            if member["sync_run_ref"]:
                snapshot_refs.add(str(member["sync_run_ref"]))
            if not snapshot_refs:
                return {"status": "unavailable", "reason": "point_in_time_snapshot_refs_missing"}
            placeholders = ",".join("?" for _ in snapshot_refs)
            rows = connection.execute(
                f"""
                SELECT symbol, valid_from, valid_to, listing_status, risk_warning,
                       available_at, source, source_observed_at, source_payload_hash,
                       json_extract(evidence_json, '$.job_id') AS snapshot_ref
                FROM security_master_intervals
                WHERE json_extract(evidence_json, '$.job_id') IN ({placeholders})
                  AND valid_from<=? AND COALESCE(valid_to, valid_from)>=?
                  AND risk_warning=0
                  AND LOWER(listing_status) IN ('listed','active','normal')
                ORDER BY symbol, valid_from
                """,
                (*sorted(snapshot_refs), end_date, start_date),
            ).fetchall()
        intervals = [dict(row) for row in rows]
        price_symbols = set(self._symbols_with_price_coverage(
            adjustment=adjustment, start_date=start_date, end_date=end_date,
        ))
        symbols = sorted({
            str(row["symbol"])
            for row in intervals
            if str(row["symbol"]) in price_symbols
            and not str(row["symbol"]).startswith(_FUJING_V7_EXCLUDED_PREFIXES)
        })
        selected = set(symbols)
        intervals = [row for row in intervals if str(row["symbol"]) in selected]
        return {
            "status": "ready" if symbols else "unavailable",
            "reason": "" if symbols else "point_in_time_pool_has_no_eligible_members",
            "symbols": symbols,
            "membership_intervals": intervals,
        }

    def _symbols_with_price_coverage(
        self,
        *,
        adjustment: str,
        start_date: str,
        end_date: str,
    ) -> list[str]:
        with closing(self._market_connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT p.symbol FROM market_daily_prices p
                WHERE p.adjustment=? AND p.trade_date BETWEEN ? AND ?
                  AND EXISTS (
                      SELECT 1 FROM security_lifecycle_events l
                      WHERE l.symbol=p.symbol
                        AND l.event_type IN ('listed','listed_source_observation')
                        AND COALESCE(l.effective_from, '')<=p.trade_date
                        AND (l.effective_to IS NULL OR l.effective_to='' OR l.effective_to>=p.trade_date)
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM security_lifecycle_events l
                      WHERE l.symbol=p.symbol AND LOWER(l.event_type) LIKE 'delist%'
                        AND COALESCE(l.effective_from, '')<=p.trade_date
                  )
                ORDER BY p.symbol
                """,
                (adjustment, start_date, end_date),
            ).fetchall()
        return [str(row["symbol"]) for row in rows]

    def _trade_dates(self, start_date: str, end_date: str) -> list[str]:
        with closing(self._market_connect()) as connection:
            rows = connection.execute(
                """SELECT trade_date FROM market_trade_calendar
                   WHERE market='CN' AND is_open=1
                     AND trade_date BETWEEN ? AND ?
                   ORDER BY trade_date""",
                (start_date, end_date),
            ).fetchall()
        return [str(row["trade_date"]) for row in rows]

    def _lookback_start(self, start_date: str, minimum_history: int) -> str:
        with closing(self._market_connect()) as connection:
            rows = connection.execute(
                """SELECT trade_date FROM market_trade_calendar
                   WHERE market='CN' AND is_open=1 AND trade_date<?
                   ORDER BY trade_date DESC LIMIT ?""",
                (start_date, max(0, minimum_history - 1)),
            ).fetchall()
        dates = [str(row["trade_date"]) for row in rows]
        return min(dates) if dates else start_date

    def _load_prices(
        self,
        symbols: Sequence[str],
        *,
        adjustment: str,
        start_date: str,
        end_date: str,
        fields: Sequence[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not symbols:
            return {}
        safe_fields = [
            field for field in fields
            if field in {"open", "high", "low", "close", "volume", "amount"}
        ]
        placeholders = ",".join("?" for _ in symbols)
        selected = ", ".join(["symbol", "trade_date AS date", *safe_fields])
        with closing(self._market_connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT {selected}
                FROM market_daily_prices p
                WHERE p.symbol IN ({placeholders})
                  AND p.adjustment=?
                  AND p.trade_date BETWEEN ? AND ?
                  AND NOT EXISTS (
                      SELECT 1 FROM security_trading_status_daily s
                      WHERE s.symbol=p.symbol AND s.trade_date=p.trade_date
                        AND s.is_tradable=0
                  )
                  AND EXISTS (
                      SELECT 1 FROM security_lifecycle_events l
                      WHERE l.symbol=p.symbol
                        AND l.event_type IN ('listed','listed_source_observation')
                        AND COALESCE(l.effective_from, '')<=p.trade_date
                        AND (l.effective_to IS NULL OR l.effective_to='' OR l.effective_to>=p.trade_date)
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM security_lifecycle_events l
                      WHERE l.symbol=p.symbol AND LOWER(l.event_type) LIKE 'delist%'
                        AND COALESCE(l.effective_from, '')<=p.trade_date
                  )
                ORDER BY p.symbol, p.trade_date
                """,
                (*symbols, adjustment, start_date, end_date),
            ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["symbol"])].append(dict(row))
        return grouped

    def _load_industry_intervals(
        self, symbols: Sequence[str]
    ) -> dict[str, list[dict[str, Any]]]:
        if (
            self._classifications is None
            or not hasattr(self._classifications, "fetch_intervals")
        ):
            return {}
        rows = self._classifications.fetch_intervals(symbols, dimension="industry")
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["symbol"])].append(dict(row))
        return grouped

    def _symbol_in_pool_on_date(
        self,
        config: Mapping[str, Any],
        membership_intervals: Mapping[str, Sequence[Mapping[str, Any]]],
        symbol: str,
        trade_date: str,
    ) -> bool:
        if config.get("universe_policy") == _FUJING_V7_UNIVERSE_POLICY:
            return any(
                str(row.get("valid_from") or "") <= trade_date
                and str(row.get("available_at") or "")[:10] <= trade_date
                and (
                    not str(row.get("valid_to") or "")
                    or str(row.get("valid_to")) >= trade_date
                )
                and not bool(row.get("risk_warning"))
                and str(row.get("listing_status") or "").lower()
                in {"listed", "active", "normal"}
                for row in membership_intervals.get(symbol, [])
            )
        if config["pool_type"] != "index":
            return True
        return any(
            str(row.get("valid_from") or "") <= trade_date
            and (
                not str(row.get("valid_to") or "")
                or str(row.get("valid_to")) >= trade_date
            )
            for row in membership_intervals.get(symbol, [])
        )

    def _market_connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self._market_database_path.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=30,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection



def _index_intervals_by_symbol(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("symbol") or "")].append(dict(row))
    return grouped


def _normalize_optimization_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    artifact_id = str(raw.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("artifact_id is required")
    value_field = str(raw.get("value_field") or "aligned_value").strip()
    if value_field not in {"aligned_value", "value"}:
        raise ValueError("value_field must be aligned_value or value")
    horizons_raw = raw.get("forward_horizons") or []
    if not isinstance(horizons_raw, (list, tuple)):
        raise ValueError("forward_horizons must be a list")
    horizons = sorted({int(item) for item in horizons_raw})
    if not set(horizons) <= _ALLOWED_HORIZONS:
        raise ValueError("forward_horizons supports 1, 5, 10, 20")
    groups_raw = raw.get("group_counts") or [3, 5, 10]
    if not isinstance(groups_raw, (list, tuple)):
        raise ValueError("group_counts must be a list")
    groups = sorted({int(item) for item in groups_raw})
    if not groups or any(item < 2 or item > 10 for item in groups):
        raise ValueError("group_counts must be between 2 and 10")
    rates_raw = raw.get("one_side_rates") or [0.0]
    if not isinstance(rates_raw, (list, tuple)):
        raise ValueError("one_side_rates must be a list")
    rates = sorted({float(item) for item in rates_raw})
    if not rates or any(item < 0 or item > 0.05 for item in rates):
        raise ValueError("one_side_rates must be between 0 and 0.05")
    minimum = int(raw.get("min_cross_section_size") or 5)
    if minimum < 2:
        raise ValueError("min_cross_section_size must be at least 2")
    return {
        "task_id": str(raw.get("task_id") or "").strip() or None,
        "artifact_id": artifact_id,
        "value_field": value_field,
        "forward_horizons": horizons,
        "group_counts": groups,
        "one_side_rates": rates,
        "min_cross_section_size": minimum,
        "objective": "mean_net_top_bottom_return",
        "artifact_binding": "immutable_exact_id",
        "execution_policy": "explicit_start",
    }



def _normalize_config(raw: Mapping[str, Any]) -> dict[str, Any]:
    factor_id = _factor_id(raw.get("factor_id"))
    start_date = _iso_date(raw.get("start_date"), "start_date")
    end_date = _iso_date(raw.get("end_date"), "end_date")
    if start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    pool_type = str(raw.get("pool_type") or "all_a").strip().lower()
    if pool_type not in {"all_a", "index"}:
        raise ValueError("pool_type must be all_a or index")
    universe_policy = str(
        raw.get("universe_policy") or _DEFAULT_UNIVERSE_POLICY
    ).strip().lower()
    if universe_policy not in {_DEFAULT_UNIVERSE_POLICY, _FUJING_V7_UNIVERSE_POLICY}:
        raise ValueError("unsupported universe_policy")
    if pool_type == "index" and universe_policy != _DEFAULT_UNIVERSE_POLICY:
        raise ValueError("index pool does not support an all-A universe_policy")
    pool_code = str(raw.get("pool_code") or "").strip().upper() or None
    if pool_type == "index" and pool_code not in _ALLOWED_INDEX_CODES:
        raise ValueError("unsupported index pool")
    factor_adjustment = str(raw.get("factor_adjustment") or "raw").lower()
    outcome_adjustment = str(raw.get("outcome_adjustment") or "qfq").lower()
    if factor_adjustment not in _ALLOWED_ADJUSTMENTS:
        raise ValueError("invalid factor_adjustment")
    if outcome_adjustment not in _ALLOWED_ADJUSTMENTS:
        raise ValueError("invalid outcome_adjustment")
    horizons = raw.get("forward_horizons") or [5]
    if not isinstance(horizons, (list, tuple)):
        raise ValueError("forward_horizons must be a list")
    normalized_horizons = sorted({int(value) for value in horizons})
    if not normalized_horizons or not set(normalized_horizons) <= _ALLOWED_HORIZONS:
        raise ValueError("forward_horizons supports 1, 5, 10, 20")
    group_count = int(raw.get("group_count") or 5)
    if not 2 <= group_count <= 10:
        raise ValueError("group_count must be between 2 and 10")
    preprocessing = dict(raw.get("preprocessing") or {})
    winsor_mad = float(preprocessing.get("winsor_mad", 3.0))
    if not 0 <= winsor_mad <= 10:
        raise ValueError("winsor_mad must be between 0 and 10")
    one_side_rate = float(
        dict(raw.get("cost_assumption") or {}).get("one_side_rate", 0.0)
    )
    if not 0 <= one_side_rate <= 0.05:
        raise ValueError("one_side_rate must be between 0 and 0.05")
    symbols_raw = raw.get("symbols") or []
    if not isinstance(symbols_raw, (list, tuple)):
        raise ValueError("symbols must be a list")
    symbol_limit = int(raw.get("symbol_limit") or 0)
    if symbol_limit < 0:
        raise ValueError("symbol_limit must not be negative")
    research_mode = str(raw.get("research_mode") or "governed").strip().lower()
    if research_mode not in {"exploratory", "governed"}:
        raise ValueError("research_mode must be exploratory or governed")
    normalized_symbols = [_symbol(item) for item in symbols_raw if _symbol(item)]
    if research_mode == "governed" and (symbol_limit or normalized_symbols):
        raise ValueError(
            "governed research requires the complete point-in-time pool; "
            "symbol_limit and manual symbols are exploratory only"
        )
    acceptance_policy_id = str(
        raw.get("acceptance_policy_id") or _FACTOR_ACCEPTANCE_POLICY_V1["policy_id"]
    ).strip()
    if acceptance_policy_id != _FACTOR_ACCEPTANCE_POLICY_V1["policy_id"]:
        raise ValueError("unsupported acceptance_policy_id")
    requested_split = dict(raw.get("sample_split") or {})
    split_ratios = {
        "training": float(requested_split.get("training", 0.60)),
        "validation": float(requested_split.get("validation", 0.20)),
        "out_of_sample": float(requested_split.get("out_of_sample", 0.20)),
    }
    if research_mode == "governed":
        if any(value <= 0 for value in split_ratios.values()):
            raise ValueError("governed sample split ratios must be positive")
        total_ratio = sum(split_ratios.values())
        if abs(total_ratio - 1.0) > 1e-9:
            raise ValueError("governed sample split ratios must sum to 1")
    else:
        split_ratios = {"exploratory": 1.0}
    return {
        "task_id": str(raw.get("task_id") or "") or None,
        "name": str(raw.get("name") or factor_id),
        "factor_id": factor_id,
        "factor_version": str(raw.get("factor_version") or "").strip() or None,
        "pool_type": pool_type,
        "universe_policy": universe_policy,
        "pool_code": pool_code,
        "pool_as_of_date": _iso_date(
            raw.get("pool_as_of_date") or end_date, "pool_as_of_date"
        ),
        "symbols": normalized_symbols,
        "symbol_limit": symbol_limit,
        "research_mode": research_mode,
        "sample_split": split_ratios,
        "acceptance_policy_id": acceptance_policy_id,
        "requested_range": {"start_date": start_date, "end_date": end_date},
        "factor_adjustment": factor_adjustment,
        "outcome_adjustment": outcome_adjustment,
        "forward_horizons": normalized_horizons,
        "preprocessing": {
            "winsor_mad": winsor_mad,
            "industry_neutral": bool(preprocessing.get("industry_neutral", False)),
            "standardize": bool(preprocessing.get("standardize", True)),
        },
        "group_count": group_count,
        "rebalance_frequency": str(
            raw.get("rebalance_frequency") or "daily_cross_section"
        ),
        "cost_assumption": {
            "one_side_rate": one_side_rate,
            "commission_rate": float(
                dict(raw.get("cost_assumption") or {}).get("commission_rate", 0.0)
            ),
            "stamp_duty_rate": float(
                dict(raw.get("cost_assumption") or {}).get("stamp_duty_rate", 0.0)
            ),
            "slippage_rate": float(
                dict(raw.get("cost_assumption") or {}).get("slippage_rate", 0.0)
            ),
            "semantics": "execution_estimate_only",
        },
        "data_version_id": str(raw.get("data_version_id") or "") or None,
    }


def _preflight_unavailable(
    config: Mapping[str, Any],
    reason: str,
    *,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "capabilities": {},
        "config": dict(config),
        "context": None,
        "context_hash": None,
        "data_version": evidence.get("data_version"),
        "requested_range": config.get("requested_range"),
        "effective_range": None,
        "pool_snapshot": None,
        "evidence": dict(evidence),
        "reasons": [reason],
    }


def _forward_returns(
    rows: Sequence[Mapping[str, Any]], horizons: Sequence[int]
) -> dict[str, dict[str, float]]:
    ordered = sorted(
        (
            (str(row.get("date") or row.get("trade_date"))[:10], _float_or_none(row.get("close")))
            for row in rows
        ),
        key=lambda item: item[0],
    )
    result: dict[str, dict[str, float]] = {}
    for index, (trade_date, close) in enumerate(ordered):
        values: dict[str, float] = {}
        if close not in {None, 0.0}:
            for horizon in horizons:
                target = index + int(horizon)
                if target < len(ordered) and ordered[target][1] is not None:
                    values[str(horizon)] = float(ordered[target][1]) / float(close) - 1.0
        result[trade_date] = values
    return result


def _resolve_industry(intervals: Sequence[Mapping[str, Any]], trade_date: str) -> str | None:
    candidates = [
        row
        for row in intervals
        if str(row.get("valid_from") or "") <= trade_date
        and (
            not str(row.get("valid_to") or "")
            or str(row.get("valid_to")) >= trade_date
        )
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (str(row.get("valid_from") or ""), str(row.get("category") or "")),
        reverse=True,
    )
    return str(candidates[0].get("category") or "") or None


def _iso_date(value: Any, name: str) -> str:
    try:
        return date.fromisoformat(str(value or "")[:10]).isoformat()
    except ValueError as error:
        raise ValueError(f"{name} must be YYYY-MM-DD") from error


def _symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    code = raw.split(".", 1)[0]
    return code.zfill(6) if code.isdigit() else raw


def _normalize_id(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in str(value).strip()
    )
    if not normalized:
        raise ValueError("task_id is empty after normalization")
    return normalized[:120]


def _factor_id(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", normalized):
        raise ValueError(
            "factor_id must start with a letter and contain 3 to 64 lowercase letters, digits, or underscores"
        )
    return normalized


def _factor_version_number(value: Any) -> int:
    match = re.fullmatch(r"v([1-9][0-9]*)", str(value or "").strip().lower())
    return int(match.group(1)) if match else 0


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dump(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _status_counts(items: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _primary_metric(payload: Mapping[str, Any], name: str) -> Any:
    horizons = payload.get("config", {}).get("forward_horizons") or [5]
    return (
        payload.get("analysis", {})
        .get("ic", {})
        .get(str(horizons[0]), {})
        .get(name)
    )


def _factor_comparison_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the frozen research fields that must match across different factors."""

    context = dict(payload.get("context") or {})
    config = dict(payload.get("config") or {})
    fields = (
        "data_version_id",
        "quality_report_id",
        "requested_range",
        "effective_range",
        "pool_type",
        "pool_code",
        "pool_as_of_date",
        "pool_snapshot_hash",
        "forward_horizons",
        "preprocessing",
        "factor_adjustment",
        "outcome_adjustment",
        "group_count",
        "rebalance_frequency",
        "cost_assumption",
        "research_mode",
        "sample_split",
        "acceptance_policy_id",
    )
    return {
        field: context.get(field, config.get(field))
        for field in fields
        if context.get(field, config.get(field)) is not None
    }


def _seal_out_of_sample_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    sealed = json.loads(_dump(payload))
    analysis = dict(sealed.get("analysis") or {})
    samples = dict(analysis.get("sample_analysis") or {})
    if "out_of_sample" in samples:
        samples["out_of_sample"] = {
            "status": "sealed",
            "reason": "explicit_one_time_reveal_required",
        }
    analysis["sample_analysis"] = samples
    multi = dict(analysis.get("multi_factor") or {})
    if multi:
        multi["component_out_of_sample"] = {
            "status": "sealed", "reason": "explicit_one_time_reveal_required",
        }
        multi["ablations"] = {
            "status": "sealed", "reason": "explicit_one_time_reveal_required",
        }
        multi.pop("best_single_direction_aligned_rank_ic", None)
        multi.pop("full_minus_best_single_rank_ic", None)
        analysis["multi_factor"] = multi
    sealed["analysis"] = analysis
    acceptance = dict(sealed.get("acceptance") or {})
    sealed["acceptance"] = {
        "status": "sealed",
        "decision": "sealed",
        "strategy_eligible": False,
        "policy_id": acceptance.get("policy_id"),
        "reasons": ["out_of_sample_evidence_not_revealed"],
        "checks": [],
    }
    return sealed


def _freeze_factor_sample_split(
    trade_dates: Sequence[str], *, mode: str, ratios: Mapping[str, Any],
) -> dict[str, Any]:
    dates = sorted({str(item) for item in trade_dates})
    if not dates:
        return {"status": "unavailable", "reason": "no_effective_trade_dates", "segments": {}}
    if mode == "exploratory":
        return {
            "status": "ready",
            "method": "full_sample_exploratory",
            "segments": {
                "exploratory": {
                    "start_date": dates[0], "end_date": dates[-1], "period_count": len(dates),
                }
            },
        }
    training_count = max(1, int(len(dates) * float(ratios.get("training", 0.60))))
    validation_count = max(1, int(len(dates) * float(ratios.get("validation", 0.20))))
    if training_count + validation_count >= len(dates):
        validation_count = max(1, len(dates) - training_count - 1)
    out_start = training_count + validation_count
    slices = {
        "training": dates[:training_count],
        "validation": dates[training_count:out_start],
        "out_of_sample": dates[out_start:],
    }
    segments = {
        name: {
            "start_date": values[0] if values else None,
            "end_date": values[-1] if values else None,
            "period_count": len(values),
        }
        for name, values in slices.items()
    }
    return {
        "status": "ready" if all(item["period_count"] for item in segments.values()) else "unavailable",
        "method": "chronological_ratio_v1",
        "ratios": {name: float(ratios[name]) for name in ("training", "validation", "out_of_sample")},
        "segments": segments,
    }


def _evaluate_factor_acceptance(
    analysis: Mapping[str, Any], *, mode: str, primary_horizon: int,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    if mode != "governed":
        return {
            "status": "exploratory_only",
            "decision": "unavailable",
            "strategy_eligible": False,
            "policy_id": policy["policy_id"],
            "reasons": ["exploratory_research_cannot_enter_factor_admission"],
            "checks": [],
        }
    sample_analysis = dict(analysis.get("sample_analysis") or {})
    out_of_sample = dict(sample_analysis.get("out_of_sample") or {})
    if out_of_sample.get("status") == "unavailable" or not out_of_sample:
        return {
            "status": "complete",
            "decision": "unavailable",
            "strategy_eligible": False,
            "policy_id": policy["policy_id"],
            "reasons": ["out_of_sample_evidence_unavailable"],
            "checks": [],
        }
    ic = dict(out_of_sample.get("ic") or {}).get(str(primary_horizon), {}) or {}
    coverage = dict(out_of_sample.get("coverage") or {})
    group = dict(out_of_sample.get("group_analysis") or {})
    execution = dict(out_of_sample.get("execution_estimate") or {})
    period_count = len(ic.get("series") or [])
    checks = [
        _acceptance_check(
            "factor_coverage", coverage.get("average_factor_coverage"),
            ">=", policy["minimum_factor_coverage"],
        ),
        _acceptance_check(
            "independent_periods", period_count,
            ">=", policy["minimum_independent_periods"],
        ),
        _acceptance_check(
            "direction_aligned_rank_ic", ic.get("direction_aligned_rank_ic_mean"),
            ">=", policy["minimum_direction_aligned_rank_ic"],
        ),
        _acceptance_check(
            "rank_ic_hac_t_value", ic.get("rank_ic_hac_t_value"),
            ">=", policy["minimum_rank_ic_hac_t_value"],
        ),
        _acceptance_check(
            "positive_rank_ic_ratio", ic.get("positive_aligned_rank_ic_ratio"),
            ">=", policy["minimum_positive_rank_ic_ratio"],
        ),
        _acceptance_check(
            "net_return_estimate", execution.get("net_return_estimate"),
            ">=", policy["minimum_net_return_estimate"],
        ),
        _acceptance_check(
            "maximum_drawdown", group.get("max_drawdown"),
            ">=", policy["maximum_drawdown_floor"],
        ),
    ]
    unavailable = [item["metric"] for item in checks if item["status"] == "unavailable"]
    failed = [item["metric"] for item in checks if item["status"] == "failed"]
    decision = "approved" if not unavailable and not failed else (
        "unavailable" if unavailable else "rejected"
    )
    return {
        "status": "complete",
        "decision": decision,
        "strategy_eligible": False,
        "policy_id": policy["policy_id"],
        "policy_hash": canonical_hash(policy),
        "checks": checks,
        "reasons": [*(f"unavailable:{item}" for item in unavailable), *(f"failed:{item}" for item in failed)],
        "note": "research acceptance is evidence only; approval and registration are separate",
    }


def _acceptance_check(metric: str, actual: Any, operator: str, threshold: Any) -> dict[str, Any]:
    value = _float_or_none(actual)
    if value is None:
        status = "unavailable"
    else:
        status = "passed" if value >= float(threshold) else "failed"
    return {
        "metric": metric,
        "actual": value,
        "operator": operator,
        "threshold": threshold,
        "status": status,
    }


def _normalize_composite_weights(values: Sequence[Any], *, count: int, method: str) -> list[float]:
    if method == "equal_rank":
        return [1.0 / count] * count
    weights = [float(item) for item in values]
    if len(weights) != count:
        raise ValueError("fixed_weight_rank requires one weight per component")
    scale = sum(abs(item) for item in weights)
    if scale <= 0:
        raise ValueError("composite weights must not all be zero")
    return [item / scale for item in weights]


def _component_rank_maps(
    component_values: Sequence[Mapping[tuple[str, str], float]],
    common_keys: set[tuple[str, str]],
) -> list[dict[tuple[str, str], float]]:
    result: list[dict[tuple[str, str], float]] = []
    for values in component_values:
        by_date: dict[str, list[tuple[tuple[str, str], float]]] = defaultdict(list)
        for key in common_keys:
            by_date[key[0]].append((key, float(values[key])))
        ranked: dict[tuple[str, str], float] = {}
        for rows in by_date.values():
            ordered = sorted(rows, key=lambda item: (item[1], item[0][1]))
            position = 0
            while position < len(ordered):
                end = position + 1
                while end < len(ordered) and ordered[end][1] == ordered[position][1]:
                    end += 1
                average_rank = (position + 1 + end) / 2.0
                centered = (
                    average_rank / (len(ordered) + 1.0) - 0.5
                    if len(ordered) > 1 else 0.0
                )
                for index in range(position, end):
                    ranked[ordered[index][0]] = centered
                position = end
        result.append(ranked)
    return result


def _composite_observations(
    common_keys: set[tuple[str, str]],
    rank_maps: Sequence[Mapping[tuple[str, str], float]],
    weights: Sequence[float],
    base_observations: Mapping[tuple[str, str], Mapping[str, Any]],
    *, component_artifact_ids: Sequence[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade_date, symbol in sorted(common_keys):
        key = (trade_date, symbol)
        source = dict(base_observations.get(key) or {})
        if not source:
            continue
        score = sum(
            float(weight) * float(rank_map[key])
            for weight, rank_map in zip(weights, rank_maps, strict=True)
        )
        rows.append({
            "trade_date": trade_date,
            "symbol": symbol,
            "raw_value": score,
            "processed_value": score,
            "aligned_value": score,
            "forward_returns": dict(source.get("forward_returns") or {}),
            "industry": source.get("industry"),
            "evidence": {
                "component_artifact_ids": list(component_artifact_ids),
                "component_rank_values": [rank_map[key] for rank_map in rank_maps],
                "weights": list(weights),
            },
        })
    return rows


def _sample_analysis_for_observations(
    observations: Sequence[Mapping[str, Any]], *, universe_by_date: Mapping[str, int],
    sample_split: Mapping[str, Any], horizons: Sequence[int], group_count: int,
    cost_rate: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, selected_range in dict(sample_split.get("segments") or {}).items():
        start = str(selected_range.get("start_date") or "")
        end = str(selected_range.get("end_date") or "")
        rows = [
            dict(item) for item in observations
            if start <= str(item.get("trade_date") or "") <= end
        ]
        if not rows:
            result[name] = {"status": "unavailable", "reason": "sample_has_no_observations"}
            continue
        dates = {str(item["trade_date"]) for item in rows}
        result[name] = build_factor_report(
            observations=rows,
            universe_count_by_date={item: universe_by_date.get(item, 0) for item in dates},
            horizons=horizons,
            group_count=group_count,
            direction="positive",
            cost_rate=cost_rate,
        )
    return result


def _multi_factor_evidence(
    *, component_values: Sequence[Mapping[tuple[str, str], float]],
    common_keys: set[tuple[str, str]], artifact_ids: Sequence[str],
    factor_ids: Sequence[str], weights: Sequence[float],
    observations: Sequence[Mapping[str, Any]],
    base_observations: Mapping[tuple[str, str], Mapping[str, Any]],
    rank_maps: Sequence[Mapping[tuple[str, str], float]],
    source_reports: Sequence[Mapping[str, Any]], universe_by_date: Mapping[str, int],
    context: Mapping[str, Any], config: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_keys = sorted(common_keys)
    correlations: list[dict[str, Any]] = []
    redundant_pairs: list[dict[str, Any]] = []
    for left in range(len(component_values)):
        for right in range(left + 1, len(component_values)):
            correlation = spearman(
                [component_values[left][key] for key in ordered_keys],
                [component_values[right][key] for key in ordered_keys],
            )
            item = {
                "left_factor_id": factor_ids[left],
                "right_factor_id": factor_ids[right],
                "rank_correlation": correlation,
                "sample_count": len(ordered_keys),
            }
            correlations.append(item)
            if correlation is not None and abs(float(correlation)) >= 0.80:
                redundant_pairs.append({**item, "reason": "absolute_rank_correlation_at_least_0_80"})
    horizon = str((config.get("forward_horizons") or [5])[0])
    component_oos: list[dict[str, Any]] = []
    for artifact_id, factor_id, report in zip(
        artifact_ids, factor_ids, source_reports, strict=True
    ):
        payload = dict(report.get("payload") or {})
        oos = dict(payload.get("analysis", {}).get("sample_analysis", {}).get("out_of_sample") or {})
        primary = dict(oos.get("ic") or {}).get(horizon, {}) or {}
        component_oos.append({
            "artifact_id": artifact_id,
            "factor_id": factor_id,
            "direction_aligned_rank_ic_mean": primary.get("direction_aligned_rank_ic_mean"),
            "net_return_estimate": dict(oos.get("execution_estimate") or {}).get("net_return_estimate"),
        })
    ablations: list[dict[str, Any]] = []
    for omitted in range(len(weights)):
        remaining_indices = [index for index in range(len(weights)) if index != omitted]
        scale = sum(abs(weights[index]) for index in remaining_indices)
        remaining_weights = [weights[index] / scale for index in remaining_indices]
        rows = _composite_observations(
            common_keys,
            [rank_maps[index] for index in remaining_indices],
            remaining_weights,
            base_observations,
            component_artifact_ids=[artifact_ids[index] for index in remaining_indices],
        )
        sample_analysis = _sample_analysis_for_observations(
            rows,
            universe_by_date=universe_by_date,
            sample_split=dict(context.get("sample_split") or {}),
            horizons=config["forward_horizons"],
            group_count=int(config["group_count"]),
            cost_rate=float(config["cost_assumption"]["one_side_rate"]),
        )
        oos = dict(sample_analysis.get("out_of_sample") or {})
        primary = dict(oos.get("ic") or {}).get(horizon, {}) or {}
        ablations.append({
            "omitted_artifact_id": artifact_ids[omitted],
            "omitted_factor_id": factor_ids[omitted],
            "direction_aligned_rank_ic_mean": primary.get("direction_aligned_rank_ic_mean"),
            "net_return_estimate": dict(oos.get("execution_estimate") or {}).get("net_return_estimate"),
        })
    return {
        "component_count": len(artifact_ids),
        "common_observation_count": len(observations),
        "weights": [
            {"artifact_id": artifact_id, "factor_id": factor_id, "weight": weight}
            for artifact_id, factor_id, weight in zip(artifact_ids, factor_ids, weights, strict=True)
        ],
        "correlations": correlations,
        "redundant_pairs": redundant_pairs,
        "component_out_of_sample": component_oos,
        "ablations": ablations,
    }


def _apply_multi_factor_acceptance(
    acceptance: Mapping[str, Any], analysis: Mapping[str, Any], primary_horizon: int,
) -> dict[str, Any]:
    result = dict(acceptance)
    checks = list(result.get("checks") or [])
    evidence = dict(analysis.get("multi_factor") or {})
    full_oos = dict(analysis.get("sample_analysis", {}).get("out_of_sample") or {})
    full_primary = dict(full_oos.get("ic") or {}).get(str(primary_horizon), {}) or {}
    full_ic = _float_or_none(full_primary.get("direction_aligned_rank_ic_mean"))
    component_values = [
        _float_or_none(item.get("direction_aligned_rank_ic_mean"))
        for item in evidence.get("component_out_of_sample") or []
    ]
    available_components = [item for item in component_values if item is not None]
    best_single = max(available_components) if available_components else None
    incremental = full_ic - best_single if full_ic is not None and best_single is not None else None
    checks.append(_acceptance_check("best_single_rank_ic_increment", incremental, ">=", 0.0))
    ablation_deltas = []
    for item in evidence.get("ablations") or []:
        ablation_ic = _float_or_none(item.get("direction_aligned_rank_ic_mean"))
        delta = full_ic - ablation_ic if full_ic is not None and ablation_ic is not None else None
        ablation_deltas.append({**dict(item), "full_minus_ablation_rank_ic": delta})
        checks.append(_acceptance_check(
            f"ablation_contribution:{item.get('omitted_factor_id')}", delta, ">=", 0.0,
        ))
    evidence["best_single_direction_aligned_rank_ic"] = best_single
    evidence["full_minus_best_single_rank_ic"] = incremental
    evidence["ablations"] = ablation_deltas
    if isinstance(analysis, dict):
        analysis["multi_factor"] = evidence
    result["checks"] = checks
    unavailable = [item["metric"] for item in checks if item["status"] == "unavailable"]
    failed = [item["metric"] for item in checks if item["status"] == "failed"]
    if unavailable:
        result["decision"] = "unavailable"
    elif failed:
        result["decision"] = "rejected"
    elif result.get("decision") == "approved":
        result["decision"] = "approved"
    result["strategy_eligible"] = False
    result["reasons"] = [
        *(f"unavailable:{item}" for item in unavailable),
        *(f"failed:{item}" for item in failed),
    ]
    return result


def _factor_comparison_context_label(context: Mapping[str, Any]) -> str:
    requested = dict(context.get("effective_range") or context.get("requested_range") or {})
    pool = str(context.get("pool_code") or context.get("pool_type") or "未标记股票池")
    start = str(requested.get("start_date") or "?")
    end = str(requested.get("end_date") or "?")
    horizon = ",".join(str(item) for item in context.get("forward_horizons") or []) or "?"
    version = str(context.get("data_version_id") or "未标记数据版本")
    return f"{pool} · {start} 至 {end} · {horizon}日 · {version}"


def _latest_top_turnover(analysis: Mapping[str, Any]) -> Any:
    group = dict(analysis.get("group_analysis") or {})
    series = list(group.get("series") or [])
    if not series:
        return None
    return dict(series[-1].get("turnover") or {}).get(str(group.get("group_count") or 5))
