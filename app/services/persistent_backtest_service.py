"""Persistence-aware backtest execution service."""

from __future__ import annotations
from data_platform.maintenance_transaction import guarded_research, require_current_input

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from dataclasses import replace
from typing import Any

from app.runtime.sqlite_runtime_store import SqliteRuntimeStore
from domain.backtest.models import BacktestResultSummary, BacktestRunRequest

from .backtest_service import BacktestService
from .backtest_advanced_analysis import build_advanced_analysis


class PersistentBacktestService:
    """Execute one backtest and persist runtime/task metadata into SQLite."""

    def __init__(
        self,
        backtest_service: BacktestService,
        runtime_store: SqliteRuntimeStore,
        market_data_service: Any | None = None,
    ) -> None:
        self._backtest_service = backtest_service
        self._runtime_store = runtime_store
        self._market_data_service = market_data_service

    def list_runs(self, limit: int = 50) -> list[Mapping[str, Any]]:
        if not hasattr(self._runtime_store, "list_backtest_runs"):
            return []
        return [dict(item) for item in self._runtime_store.list_backtest_runs(limit=limit)]
    @guarded_research
    def run_once(self, request: BacktestRunRequest) -> BacktestResultSummary:
        adjustment = str(request.parameters.get("adjustment") or request.extra_config.get("adjustment") or "raw")
        if request.extra_config.get("adjustment") and request.extra_config["adjustment"] != adjustment:
            raise ValueError("conflicting adjustment settings")
        request = replace(request, parameters={**request.parameters, "adjustment": adjustment},
                          extra_config={**request.extra_config, "adjustment": adjustment})
        started_at = _utc_now()
        data_asset_trace = self._build_data_asset_trace(request=request, bound_at=started_at)
        extra_config = _merge_data_asset_trace(request.extra_config, data_asset_trace)
        request = replace(request, extra_config=extra_config)
        require_current_input(self, extra_config)
        self._runtime_store.upsert_backtest_run(
            run_id=request.run_id,
            strategy_name=request.strategy_name,
            strategy_id=request.strategy_id,
            status="running",
            benchmark=request.benchmark,
            universe=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            created_at=started_at,
            completed_at=None,
            parameters=request.parameters,
            extra_config=extra_config,
            raw_result={},
            error_message=None,
        )
        if data_asset_trace.get("status") == "data_not_ready":
            message = f"data_not_ready:{data_asset_trace.get('reason') or 'published_version_unavailable'}"
            self._runtime_store.upsert_backtest_run(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                strategy_id=request.strategy_id,
                status="failed",
                benchmark=request.benchmark,
                universe=request.symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                created_at=started_at,
                completed_at=_utc_now(),
                parameters=request.parameters,
                extra_config=extra_config,
                raw_result={},
                error_message=message,
            )
            raise RuntimeError(message)
        try:
            result, raw_result = self._backtest_service.run_once_with_raw_result(request)
        except Exception as exc:
            self._runtime_store.upsert_backtest_run(
                run_id=request.run_id,
                strategy_name=request.strategy_name,
                strategy_id=request.strategy_id,
                status="failed",
                benchmark=request.benchmark,
                universe=request.symbol,
                start_date=request.start_date,
                end_date=request.end_date,
                created_at=started_at,
                completed_at=_utc_now(),
                parameters=request.parameters,
                extra_config=extra_config,
                raw_result={},
                error_message=str(exc),
            )
            self._runtime_store.replace_backtest_metrics(run_id=request.run_id, metrics={})
            raise

        detail_payload = _extract_runtime_detail(raw_result)
        completed_at = _utc_now()
        self._runtime_store.upsert_backtest_run(
            run_id=request.run_id,
            strategy_name=result.strategy_name,
            strategy_id=request.strategy_id,
            status=result.status.value,
            benchmark=result.benchmark,
            universe=request.symbol,
            start_date=result.start_date,
            end_date=result.end_date,
            created_at=started_at,
            completed_at=completed_at,
            parameters=request.parameters,
            extra_config=extra_config,
            raw_result=raw_result,
            error_message=None,
        )
        self._runtime_store.replace_backtest_metrics(
            run_id=request.run_id,
            metrics=result.metrics,
        )
        self._runtime_store.replace_backtest_logs(
            run_id=request.run_id,
            rows=detail_payload["logs"],
        )
        self._runtime_store.replace_backtest_trades(
            run_id=request.run_id,
            rows=detail_payload["trades"],
        )
        self._runtime_store.replace_backtest_positions(
            run_id=request.run_id,
            rows=detail_payload["positions"],
        )
        self._runtime_store.replace_backtest_accounts(
            run_id=request.run_id,
            rows=detail_payload["accounts"],
        )
        self._runtime_store.replace_backtest_yearly_returns(
            run_id=request.run_id,
            rows=detail_payload["yearly_returns"],
        )
        if hasattr(self._runtime_store, "save_backtest_input_snapshot"):
            self._runtime_store.save_backtest_input_snapshot(
                run_id=request.run_id,
                data_asset_trace=extra_config.get("data_asset_trace") or {},
            )
        return result


    def _build_data_asset_trace(self, *, request: BacktestRunRequest, bound_at: str) -> dict[str, Any]:
        adjustment = str(request.parameters.get("adjustment") or request.extra_config.get("adjustment") or "raw")
        if self._market_data_service is not None and hasattr(
            self._market_data_service, "get_published_data_version"
        ):
            try:
                resolved = dict(self._market_data_service.get_published_data_version(
                    symbol=request.symbol,
                    adjustment=adjustment,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    benchmark=request.benchmark,
                ))
            except Exception as exc:
                return {
                    "status": "data_not_ready",
                    "symbol": request.symbol,
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "bound_at": bound_at,
                    "reason": f"published_version_lookup_failed:{type(exc).__name__}",
                }
            governance_status = str(resolved.get("status") or "")
            if governance_status == "bound":
                return {
                    "status": "bound",
                    "symbol": request.symbol,
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "bound_at": bound_at,
                    "asset": resolved,
                    "manifest": {
                        "scope": "published_canonical_a_share_release",
                        "members": resolved.get("members") or [],
                        "quality_report_id": resolved.get("quality_report_id"),
                    },
                    "source_endpoint": "canonical-governance:data_versions",
                    "notes": [
                        "Published data version was resolved before backtest execution.",
                        "The immutable version is reused when the run is persisted.",
                    ],
                }
            if governance_status != "unsupported":
                return {
                    **resolved,
                    "status": "data_not_ready",
                    "bound_at": bound_at,
                }

        if self._market_data_service is None or not hasattr(self._market_data_service, "get_local_price_bar_assets"):
            return {
                "status": "unsupported",
                "symbol": request.symbol,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "bound_at": bound_at,
                "reason": "market_data_service_not_configured",
            }
        try:
            payload = self._market_data_service.get_local_price_bar_assets(symbol=request.symbol, limit=1)
        except Exception as exc:  # pragma: no cover - defensive trace path
            return {
                "status": "needs_attention",
                "symbol": request.symbol,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "bound_at": bound_at,
                "reason": f"asset_lookup_failed:{type(exc).__name__}",
            }
        assets = list(payload.get("assets") or []) if isinstance(payload, Mapping) else []
        asset = dict(assets[0]) if assets and isinstance(assets[0], Mapping) else {}
        manifest = dict(payload.get("manifest") or {}) if isinstance(payload, Mapping) else {}
        return {
            "status": "bound" if asset else "not_found",
            "symbol": request.symbol,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "bound_at": bound_at,
            "asset": asset,
            "manifest": manifest,
            "source_endpoint": f"/api/market/local-price-bars/assets?symbol={request.symbol}",
            "notes": [
                "data_asset_trace is captured after backtest execution and before run persistence is finalized.",
                "The trace is read-only metadata and does not trigger provider sync.",
            ],
        }

    def delete_run(self, run_id: str, *, reason: str = "用户从 Web 工作台删除") -> dict[str, Any]:
        if not hasattr(self._runtime_store, "soft_delete_backtest_run"):
            return {"run_id": run_id, "status": "unsupported"}
        deleted_at = _utc_now()
        deleted = self._runtime_store.soft_delete_backtest_run(
            run_id,
            deleted_at=deleted_at,
            reason=reason,
        )
        return dict(deleted or {"run_id": run_id, "status": "not_found"})

    def get_result_panel(self, run_id: str) -> dict[str, Any]:
        """Return a UI-friendly result panel for one persisted backtest run."""

        run = self._runtime_store.fetch_backtest_run(run_id)
        if run is None:
            return {
                "run_id": run_id,
                "status": "not_found",
                "summary": {},
                "metrics": {},
                "trades": [],
                "positions": [],
                "accounts": [],
                "yearly_returns": [],
                "logs": [],
                "parameter_snapshot": {},
                "equity_curve": [],
                "drawdown_curve": [],
                "trade_attribution": {},
                "risk_metrics": {},
                "exposure_summary": {},
            }
        metrics = _index_metric_rows(self._runtime_store.fetch_backtest_metrics(run_id))
        raw_result = dict(run.get("raw_result") or {})
        trades = _merge_artifact_rows(
            _dict_rows(self._runtime_store.fetch_backtest_trades(run_id)),
            raw_result.get("trades") or [],
        )
        positions = _merge_artifact_rows(
            _dict_rows(self._runtime_store.fetch_backtest_positions(run_id)),
            raw_result.get("positions") or [],
        )
        accounts = _merge_artifact_rows(
            _dict_rows(self._runtime_store.fetch_backtest_accounts(run_id)),
            raw_result.get("accounts") or [],
        )
        yearly_returns = _dict_rows(self._runtime_store.fetch_backtest_yearly_returns(run_id))
        logs = _dict_rows(self._runtime_store.fetch_backtest_logs(run_id))
        equity_curve = _build_equity_curve(accounts)
        drawdown_curve = _build_drawdown_curve(equity_curve)
        extra_config = dict(run.get("extra_config") or {})
        trade_attribution = _build_trade_attribution(trades, parameter_snapshot=extra_config)
        metrics["trade_fill_count"] = len(trades)
        metrics["trade_count"] = trade_attribution.get("roundtrip_count")
        metrics["win_rate"] = trade_attribution.get("estimated_win_rate")
        metrics["profit_loss_ratio"] = trade_attribution.get("profit_loss_ratio")
        risk_metrics = _build_risk_metrics(equity_curve, drawdown_curve)
        exposure_summary = _build_exposure_summary(positions, accounts)
        advanced = build_advanced_analysis(
            account_rows=accounts,
            benchmark_curve=_dict_rows(raw_result.get("benchmark_curve") or []),
            excess_curve=_dict_rows(raw_result.get("excess_curve") or []),
            trades=trades,
            metrics=metrics,
            raw_result=raw_result,
            extra_config=extra_config,
        )
        input_snapshot = dict(self._runtime_store.fetch_backtest_input_snapshot(run_id) or {}) if hasattr(self._runtime_store, "fetch_backtest_input_snapshot") else {}
        persisted_trace = dict((input_snapshot.get("payload") or {}).get("trace") or {}) if input_snapshot else {}
        data_asset_trace = persisted_trace or dict(extra_config.get("data_asset_trace") or {})
        parameter_snapshot = {
            "parameters": dict(run.get("parameters") or {}),
            "extra_config": extra_config,
        }
        return {
            "run_id": run_id,
            "status": str(run.get("status") or "unknown"),
            "summary": {
                "run_id": run.get("run_id"),
                "strategy_name": run.get("strategy_name"),
                "strategy_id": run.get("strategy_id"),
                "status": run.get("status"),
                "benchmark": run.get("benchmark"),
                "universe": run.get("universe"),
                "start_date": run.get("start_date"),
                "end_date": run.get("end_date"),
                "created_at": run.get("created_at"),
                "completed_at": run.get("completed_at"),
                "error_message": run.get("error_message"),
                "trade_count": trade_attribution.get("roundtrip_count") or 0,
                "trade_fill_count": len(trades),
                "position_count": len(positions),
                "account_points": len(accounts),
                "year_count": len(yearly_returns),
                "log_count": len(logs),
                "data_asset_status": data_asset_trace.get("status") or "not_bound",
                "data_version": input_snapshot.get("data_version") or ((data_asset_trace.get("asset") or {}).get("data_version") if isinstance(data_asset_trace.get("asset"), Mapping) else None),
                "input_snapshot_id": input_snapshot.get("snapshot_id"),
            },
            "metrics": metrics,
            "trades": trades,
            "positions": positions,
            "accounts": accounts,
            "yearly_returns": yearly_returns,
            "logs": logs,
            "parameter_snapshot": parameter_snapshot,
            "benchmark_alignment": raw_result.get("benchmark_alignment") or {},
            "benchmark_status": raw_result.get("benchmark_status"),
            "benchmark_curve": raw_result.get("benchmark_curve") or [],
            "data_asset_trace": data_asset_trace,
            "input_snapshot": input_snapshot,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "trade_attribution": trade_attribution,
            "risk_metrics": risk_metrics,
            "exposure_summary": exposure_summary,
            "price_bars": advanced["price_bars"],
            "signal_evidence": advanced["signal_evidence"],
            "monthly_return_heatmap": advanced["monthly_return_heatmap"],
            "excess_drawdown_curve": advanced["excess_drawdown_curve"],
            "market_regimes": advanced["market_regimes"],
            "execution_quality": advanced["execution_quality"],
            "cost_capacity_stress": advanced["cost_capacity_stress"],
            "robustness": advanced["robustness"],
            "parameter_sensitivity": advanced["parameter_sensitivity"],
            "report_governance": advanced["report_governance"],        }


    def get_input_snapshot(self, run_id: str) -> dict[str, Any]:
        if not hasattr(self._runtime_store, "fetch_backtest_input_snapshot"):
            return {"run_id": run_id, "status": "unsupported"}
        snapshot = self._runtime_store.fetch_backtest_input_snapshot(run_id)
        if snapshot is None:
            return {"run_id": run_id, "status": "not_found"}
        return {"status": "found", **dict(snapshot)}

    def list_data_assets(
        self,
        *,
        symbol: str | None = None,
        dataset: str | None = None,
        data_version: str | None = None,
        quality_status: str | None = None,
        coverage_status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        if not hasattr(self._runtime_store, "fetch_local_data_assets"):
            return {"assets": [], "summary": {"status": "unsupported", "asset_count": 0}}
        assets = [
            dict(item)
            for item in self._runtime_store.fetch_local_data_assets(
                symbol=symbol,
                dataset=dataset,
                data_version=data_version,
                quality_status=quality_status,
                coverage_status=coverage_status,
                limit=limit,
            )
        ]
        return {
            "assets": assets,
            "summary": {
                "status": "ready",
                "asset_count": len(assets),
                "filters": {
                    "symbol": symbol,
                    "dataset": dataset,
                    "data_version": data_version,
                    "quality_status": quality_status,
                    "coverage_status": coverage_status,
                    "limit": limit,
                },
                "symbols": sorted({str(item.get("symbol") or "") for item in assets if item.get("symbol")}),
                "datasets": sorted({str(item.get("dataset") or "") for item in assets if item.get("dataset")}),
                "quality_statuses": sorted({str(item.get("quality_status") or "") for item in assets if item.get("quality_status")}),
                "coverage_statuses": sorted({str(item.get("coverage_status") or "") for item in assets if item.get("coverage_status")}),
                "data_versions": sorted({str(item.get("data_version") or "") for item in assets if item.get("data_version")}),
            },
        }

    def migrate_input_snapshots(self, *, run_id_prefix: str | None = None, dry_run: bool = True, limit: int = 100) -> dict[str, Any]:
        if not all(hasattr(self._runtime_store, name) for name in ("fetch_backtest_runs_by_prefix", "fetch_backtest_input_snapshot", "save_backtest_input_snapshot")):
            return {"status": "unsupported", "dry_run": dry_run, "summary": {"scanned_count": 0}}
        safe_limit = max(1, min(int(limit or 100), 500))
        prefix = str(run_id_prefix or "")
        runs = list(self._runtime_store.fetch_backtest_runs_by_prefix(prefix))[:safe_limit]
        rows: list[dict[str, Any]] = []
        counters = {"already_snapshotted": 0, "planned": 0, "migrated": 0, "missing_trace": 0}
        for run in runs:
            run_id = str(run.get("run_id") or "")
            existing = self._runtime_store.fetch_backtest_input_snapshot(run_id)
            if existing:
                counters["already_snapshotted"] += 1
                rows.append({"run_id": run_id, "status": "already_snapshotted", "snapshot_id": existing.get("snapshot_id"), "data_version": existing.get("data_version")})
                continue
            extra_config = dict(run.get("extra_config") or {})
            trace = extra_config.get("data_asset_trace")
            if not isinstance(trace, Mapping) or not trace:
                counters["missing_trace"] += 1
                rows.append({"run_id": run_id, "status": "missing_trace"})
                continue
            if dry_run:
                counters["planned"] += 1
                asset = dict(trace.get("asset") or {}) if isinstance(trace.get("asset"), Mapping) else {}
                rows.append({"run_id": run_id, "status": "planned", "data_version": asset.get("data_version"), "symbol": trace.get("symbol") or asset.get("symbol")})
                continue
            snapshot = self._runtime_store.save_backtest_input_snapshot(run_id=run_id, data_asset_trace=trace)
            counters["migrated"] += 1
            rows.append({"run_id": run_id, "status": "migrated", "snapshot_id": snapshot.get("snapshot_id"), "data_version": (snapshot.get("asset") or {}).get("data_version")})
        return {
            "status": "dry_run" if dry_run else "completed",
            "dry_run": dry_run,
            "run_id_prefix": prefix,
            "summary": {"scanned_count": len(runs), **counters},
            "rows": rows,
        }

    def get_portfolio_panel(self, run_id_prefix: str) -> dict[str, Any]:
        """Return an equal-weight portfolio panel across runs sharing one prefix."""

        runs = list(self._runtime_store.fetch_backtest_runs_by_prefix(run_id_prefix))
        panels = [self.get_result_panel(str(run.get("run_id") or "")) for run in runs]
        panels = [panel for panel in panels if panel.get("status") != "not_found"]
        if not panels:
            return {
                "run_id_prefix": run_id_prefix,
                "status": "not_found",
                "summary": {"run_count": 0, "symbols": []},
                "rows": [],
                "metrics": {},
                "equity_curve": [],
                "drawdown_curve": [],
            }
        rows = [_portfolio_row(panel) for panel in panels]
        asset_consistency = _build_asset_consistency(rows)
        equity_curve = _combine_equity_curves(panels)
        return {
            "run_id_prefix": run_id_prefix,
            "status": "completed" if all(row.get("status") == "completed" for row in rows) else "partial",
            "summary": {
                "run_count": len(rows),
                "symbols": [row.get("symbol") for row in rows if row.get("symbol")],
                "completed_count": sum(1 for row in rows if row.get("status") == "completed"),
                "trade_count": sum(int(row.get("trade_count") or 0) for row in rows),
                "account_points": sum(int(row.get("account_points") or 0) for row in rows),
                "asset_consistency_status": asset_consistency.get("status"),
                "data_version_count": asset_consistency.get("data_version_count"),
            },
            "rows": rows,
            "metrics": _aggregate_portfolio_metrics(rows),
            "equity_curve": equity_curve,
            "drawdown_curve": _build_drawdown_curve(equity_curve),
            "asset_consistency": asset_consistency,
            "risk_metrics": _build_risk_metrics(equity_curve, _build_drawdown_curve(equity_curve)),
            "trade_attribution": _aggregate_trade_attribution(panels),
        }

    def get_result_table(
        self,
        run_id: str,
        *,
        table: str = "trades",
        offset: int = 0,
        limit: int = 50,
        export_format: str = "json",
    ) -> dict[str, Any]:
        """Return one result detail table with pagination and simple exports."""

        panel = self.get_result_panel(run_id)
        if panel.get("status") == "not_found":
            return {"run_id": run_id, "status": "not_found", "table": table, "rows": [], "total": 0}
        normalized_table = table if table in _RESULT_TABLE_KEYS else "trades"
        rows = list(panel.get(normalized_table) or [])
        safe_offset = max(0, int(offset or 0))
        safe_limit = min(500, max(1, int(limit or 50)))
        page_rows = rows[safe_offset:safe_offset + safe_limit]
        normalized_format = str(export_format or "json").lower()
        result = {
            "run_id": run_id,
            "status": panel.get("status"),
            "table": normalized_table,
            "offset": safe_offset,
            "limit": safe_limit,
            "total": len(rows),
            "has_next": safe_offset + safe_limit < len(rows),
            "rows": page_rows,
            "export_format": normalized_format,
        }
        if normalized_format == "csv":
            result["content"] = _rows_to_csv(page_rows)
            result["content_type"] = "text/csv"
        else:
            result["content"] = page_rows
            result["content_type"] = "application/json"
        return result


    def get_experiment_panel(self, run_id_prefix: str) -> dict[str, Any]:
        """Return a lightweight experiment/run group summary."""

        runs = list(self._runtime_store.fetch_backtest_runs_by_prefix(run_id_prefix))
        rows = []
        for run in runs:
            run_id = str(run.get("run_id") or "")
            metrics = _index_metric_rows(self._runtime_store.fetch_backtest_metrics(run_id))
            input_snapshot = dict(self._runtime_store.fetch_backtest_input_snapshot(run_id) or {}) if hasattr(self._runtime_store, "fetch_backtest_input_snapshot") else {}
            rows.append({
                "run_id": run_id,
                "strategy_name": run.get("strategy_name"),
                "symbol": run.get("universe"),
                "status": run.get("status"),
                "start_date": run.get("start_date"),
                "end_date": run.get("end_date"),
                "created_at": run.get("created_at"),
                "completed_at": run.get("completed_at"),
                "total_returns": _to_float(metrics.get("total_returns")),
                "annualized_returns": _to_float(metrics.get("annualized_returns")),
                "max_drawdown": _to_float(metrics.get("max_drawdown")),
                "sharpe": _to_float(metrics.get("sharpe")),
                "parameters": dict(run.get("parameters") or {}),
                "data_version": input_snapshot.get("data_version"),
                "input_snapshot_id": input_snapshot.get("snapshot_id"),
                "asset_key": input_snapshot.get("asset_key"),
            })
        asset_consistency = _build_asset_consistency(rows)
        return {
            "run_id_prefix": run_id_prefix,
            "status": "completed" if rows and all(row.get("status") == "completed" for row in rows) else ("not_found" if not rows else "partial"),
            "summary": {
                "run_count": len(rows),
                "completed_count": sum(1 for row in rows if row.get("status") == "completed"),
                "symbols": [row.get("symbol") for row in rows if row.get("symbol")],
                "asset_consistency_status": asset_consistency.get("status"),
                "data_version_count": asset_consistency.get("data_version_count"),
            },
            "rows": rows,
            "asset_consistency": asset_consistency,
            "portfolio_panel_path": f"/api/backtest/results/{run_id_prefix}/portfolio-panel",
        }
def _merge_data_asset_trace(extra_config: Mapping[str, Any], trace: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(extra_config or {})
    merged["data_asset_trace"] = dict(trace)
    return merged

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extract_runtime_detail(
    raw_result: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]]:
    detail_sources = [raw_result, *_nested_detail_mappings(raw_result)]
    return {
        "logs": _normalize_log_rows(
            _find_sequence(detail_sources, "logs", "backtest_logs", "log_rows"),
        ),
        "trades": _normalize_mapping_rows(
            _find_sequence(detail_sources, "trades", "backtest_trades", "trade_rows"),
        ),
        "positions": _normalize_mapping_rows(
            _find_sequence(detail_sources, "positions", "backtest_positions", "position_rows"),
        ),
        "accounts": _normalize_mapping_rows(
            _find_sequence(detail_sources, "accounts", "backtest_accounts", "account_rows"),
        ),
        "yearly_returns": _normalize_mapping_rows(
            _find_sequence(
                detail_sources,
                "yearly_returns",
                "backtest_yearly_returns",
                "yearly_return_rows",
                "annual_returns",
            ),
        ),
    }


def _nested_detail_mappings(raw_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    nested_keys = ("details", "artifacts", "reporting", "persistence")
    nested: list[Mapping[str, Any]] = []
    for key in nested_keys:
        value = raw_result.get(key)
        if isinstance(value, Mapping):
            nested.append(value)
    return nested


def _find_sequence(
    sources: Sequence[Mapping[str, Any]],
    *keys: str,
) -> Sequence[Any]:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return value
    return []


def _normalize_log_rows(rows: Sequence[Any]) -> list[Mapping[str, Any]]:
    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            normalized.append(dict(row))
            continue
        if row in (None, ""):
            continue
        normalized.append({"message": str(row)})
    return normalized


def _normalize_mapping_rows(rows: Sequence[Any]) -> list[Mapping[str, Any]]:
    normalized: list[Mapping[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            normalized.append(dict(row))
    return normalized


def _index_metric_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for row in rows:
        name = row.get("metric_name")
        if name in (None, ""):
            continue
        metrics[str(name)] = row.get("metric_value") if row.get("metric_value") is not None else row.get("metric_text")
    return metrics


def _merge_artifact_rows(
    persisted: Sequence[Mapping[str, Any]],
    raw: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(persisted) != len(raw):
        return [dict(row) for row in persisted]
    return [{**dict(saved), **dict(source)} for saved, source in zip(persisted, raw)]

def _dict_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]



def _build_equity_curve(accounts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    first_value: float | None = None
    for account in accounts:
        snapshot_time = str(account.get("snapshot_time") or "")
        if not snapshot_time:
            continue
        raw_value = account.get("unit_net_value")
        value = _to_float(raw_value)
        if value is None:
            value = _to_float(account.get("total_value"))
            if value is not None:
                first_value = first_value or value
                value = value / first_value if first_value else value
        if value is None:
            continue
        rows.append({"snapshot_time": snapshot_time, "value": value})
    return sorted(rows, key=lambda row: str(row.get("snapshot_time") or ""))


def _build_drawdown_curve(equity_curve: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    peak: float | None = 1.0
    rows: list[dict[str, Any]] = []
    for point in equity_curve:
        value = _to_float(point.get("value"))
        if value is None:
            continue
        peak = value if peak is None else max(peak, value)
        drawdown = 0.0 if not peak else (value / peak) - 1.0
        rows.append({"snapshot_time": point.get("snapshot_time"), "value": drawdown})
    return rows


def _combine_equity_curves(panels: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = {}
    for panel in panels:
        for point in panel.get("equity_curve") or []:
            snapshot_time = str(point.get("snapshot_time") or "")
            value = _to_float(point.get("value"))
            if not snapshot_time or value is None:
                continue
            buckets.setdefault(snapshot_time, []).append(value)
    return [
        {"snapshot_time": key, "value": sum(values) / len(values)}
        for key, values in sorted(buckets.items())
        if values
    ]


def _portfolio_row(panel: Mapping[str, Any]) -> dict[str, Any]:
    summary = dict(panel.get("summary") or {})
    metrics = dict(panel.get("metrics") or {})
    return {
        "run_id": panel.get("run_id"),
        "symbol": summary.get("universe"),
        "status": panel.get("status"),
        "total_returns": _to_float(metrics.get("total_returns")),
        "annualized_returns": _to_float(metrics.get("annualized_returns")),
        "max_drawdown": _to_float(metrics.get("max_drawdown")),
        "sharpe": _to_float(metrics.get("sharpe")),
        "trade_count": summary.get("trade_count") or 0,
        "account_points": summary.get("account_points") or 0,
        "data_version": summary.get("data_version"),
        "input_snapshot_id": summary.get("input_snapshot_id"),
        "asset_key": (dict(panel.get("input_snapshot") or {}).get("asset_key")),
    }


def _build_asset_consistency(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    versions = sorted({str(row.get("data_version") or "") for row in rows if row.get("data_version")})
    snapshot_ids = [str(row.get("input_snapshot_id") or "") for row in rows if row.get("input_snapshot_id")]
    missing_count = sum(1 for row in rows if not row.get("data_version"))
    if not rows:
        status = "empty"
    elif missing_count == len(rows):
        status = "missing"
    elif len(versions) == 1 and missing_count == 0:
        status = "consistent"
    else:
        status = "mixed"
    return {
        "status": status,
        "run_count": len(rows),
        "missing_count": missing_count,
        "data_versions": versions,
        "data_version_count": len(versions),
        "snapshot_count": len(snapshot_ids),
        "snapshot_ids": snapshot_ids[:20],
    }

def _aggregate_portfolio_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "avg_total_returns": _average(row.get("total_returns") for row in rows),
        "avg_annualized_returns": _average(row.get("annualized_returns") for row in rows),
        "worst_max_drawdown": _minimum(row.get("max_drawdown") for row in rows),
        "avg_sharpe": _average(row.get("sharpe") for row in rows),
    }


def _average(values: Sequence[Any]) -> float | None:
    numbers = [value for value in (_to_float(value) for value in values) if value is not None]
    return sum(numbers) / len(numbers) if numbers else None


def _minimum(values: Sequence[Any]) -> float | None:
    numbers = [value for value in (_to_float(value) for value in values) if value is not None]
    return min(numbers) if numbers else None


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None





def _build_trade_attribution(
    trades: Sequence[Mapping[str, Any]],
    *,
    parameter_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    buy_count = 0
    sell_count = 0
    buy_amount = 0.0
    sell_amount = 0.0
    traded_amount = 0.0
    quantity_by_symbol: dict[str, float] = {}
    cost_by_symbol: dict[str, float] = {}
    sell_win_count = 0
    sell_loss_count = 0
    realized_pnls: list[float] = []
    for trade in trades:
        side = str(trade.get("side") or "").upper()
        symbol = str(trade.get("order_book_id") or "")
        price = abs(_to_float(trade.get("price")) or 0.0)
        quantity = abs(_to_float(trade.get("quantity")) or 0.0)
        amount = abs(_to_float(trade.get("amount")) or (price * quantity))
        traded_amount += amount
        if side == "SELL":
            sell_count += 1
            sell_amount += amount
            avg_cost = cost_by_symbol.get(symbol, 0.0) / quantity_by_symbol.get(symbol, 1.0) if quantity_by_symbol.get(symbol, 0.0) > 0 else None
            if avg_cost is not None:
                explicit_pnl = _to_float(trade.get("pnl") if trade.get("pnl") is not None else trade.get("realized_pnl"))
                fees = abs(_to_float(trade.get("commission")) or 0.0) + abs(_to_float(trade.get("tax")) or 0.0)
                realized_pnl = explicit_pnl if explicit_pnl is not None else amount - fees - avg_cost * quantity
                realized_pnls.append(realized_pnl)
                if realized_pnl > 0:
                    sell_win_count += 1
                elif realized_pnl < 0:
                    sell_loss_count += 1
            quantity_by_symbol[symbol] = max(0.0, quantity_by_symbol.get(symbol, 0.0) - quantity)
            cost_by_symbol[symbol] = max(0.0, cost_by_symbol.get(symbol, 0.0) - (avg_cost or 0.0) * quantity)
        else:
            buy_count += 1
            buy_amount += amount
            quantity_by_symbol[symbol] = quantity_by_symbol.get(symbol, 0.0) + quantity
            buy_fees = abs(_to_float(trade.get("commission")) or 0.0) + abs(_to_float(trade.get("tax")) or 0.0)
            cost_by_symbol[symbol] = cost_by_symbol.get(symbol, 0.0) + amount + buy_fees
    roundtrip_count = len(realized_pnls)
    wins = [value for value in realized_pnls if value > 0]
    losses = [value for value in realized_pnls if value < 0]
    profit_loss_ratio = (
        (sum(wins) / len(wins)) / abs(sum(losses) / len(losses))
        if wins and losses else None
    )
    cost_rate = _estimate_cost_rate(parameter_snapshot or {})
    estimated_cost = traded_amount * cost_rate
    return {
        "trade_count": len(trades),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "buy_amount": buy_amount,
        "sell_amount": sell_amount,
        "net_cash_flow": sell_amount - buy_amount,
        "traded_amount": traded_amount,
        "roundtrip_count": roundtrip_count,
        "estimated_win_count": sell_win_count,
        "estimated_loss_count": sell_loss_count,
        "estimated_win_rate": sell_win_count / roundtrip_count if roundtrip_count else None,
        "profit_loss_ratio": profit_loss_ratio,
        "estimated_cost": estimated_cost,
        "estimated_cost_rate": cost_rate,
        "method": "avg_cost_sell_price_estimate",
    }


def _build_risk_metrics(
    equity_curve: Sequence[Mapping[str, Any]],
    drawdown_curve: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    values = [_to_float(point.get("value")) for point in equity_curve]
    values = [value for value in values if value is not None]
    returns: list[float] = []
    for previous, current in zip(values, values[1:]):
        if previous not in (None, 0.0):
            returns.append((current / previous) - 1.0)
    drawdowns = [_to_float(point.get("value")) for point in drawdown_curve]
    drawdowns = [value for value in drawdowns if value is not None]
    max_drawdown = min(drawdowns) if drawdowns else None
    current_drawdown = drawdowns[-1] if drawdowns else None
    return {
        "point_count": len(values),
        "max_drawdown": max_drawdown,
        "current_drawdown": current_drawdown,
        "best_period_return": max(returns) if returns else None,
        "worst_period_return": min(returns) if returns else None,
        "period_volatility": _stddev(returns),
        "positive_period_count": sum(1 for value in returns if value > 0),
        "negative_period_count": sum(1 for value in returns if value < 0),
        "recovered": current_drawdown == 0.0 if current_drawdown is not None else None,
    }


def _build_exposure_summary(
    positions: Sequence[Mapping[str, Any]],
    accounts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not positions:
        return {"latest_snapshot_time": None, "holding_count": 0, "gross_market_value": 0.0, "max_single_weight": None}
    latest_time = max(str(row.get("snapshot_time") or "") for row in positions)
    latest_positions = [row for row in positions if str(row.get("snapshot_time") or "") == latest_time]
    market_values = [abs(_to_float(row.get("market_value")) or 0.0) for row in latest_positions]
    gross_market_value = sum(market_values)
    account_value = _latest_account_value(accounts, latest_time) or gross_market_value
    weights = [value / account_value for value in market_values if account_value]
    return {
        "latest_snapshot_time": latest_time,
        "holding_count": sum(1 for value in market_values if value > 0),
        "gross_market_value": gross_market_value,
        "max_single_weight": max(weights) if weights else None,
        "position_symbols": [str(row.get("order_book_id") or "") for row in latest_positions if (_to_float(row.get("market_value")) or 0.0) > 0],
    }


def _aggregate_trade_attribution(panels: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    attributions = [dict(panel.get("trade_attribution") or {}) for panel in panels]
    trade_count = sum(int(item.get("trade_count") or 0) for item in attributions)
    roundtrip_count = sum(int(item.get("roundtrip_count") or 0) for item in attributions)
    win_count = sum(int(item.get("estimated_win_count") or 0) for item in attributions)
    return {
        "trade_count": trade_count,
        "buy_count": sum(int(item.get("buy_count") or 0) for item in attributions),
        "sell_count": sum(int(item.get("sell_count") or 0) for item in attributions),
        "traded_amount": sum(float(item.get("traded_amount") or 0.0) for item in attributions),
        "estimated_cost": sum(float(item.get("estimated_cost") or 0.0) for item in attributions),
        "roundtrip_count": roundtrip_count,
        "estimated_win_rate": win_count / roundtrip_count if roundtrip_count else None,
        "method": "aggregate_single_run_trade_attribution",
    }


def _estimate_cost_rate(extra_config: Mapping[str, Any]) -> float:
    rqalpha = extra_config.get("rqalpha_local") if isinstance(extra_config.get("rqalpha_local"), Mapping) else {}
    return sum(
        abs(_to_float(rqalpha.get(key)) or 0.0)
        for key in ("commission_rate", "tax_rate", "slippage_rate")
    )


def _latest_account_value(accounts: Sequence[Mapping[str, Any]], snapshot_time: str) -> float | None:
    candidates = [row for row in accounts if str(row.get("snapshot_time") or "") == snapshot_time]
    if not candidates and accounts:
        candidates = [accounts[-1]]
    for account in candidates:
        value = _to_float(account.get("total_value"))
        if value is not None:
            return value
    return None


def _stddev(values: Sequence[float]) -> float | None:
    if not values:
        return None
    average = sum(values) / len(values)
    variance = sum((value - average) ** 2 for value in values) / len(values)
    return variance ** 0.5

_RESULT_TABLE_KEYS = {"trades", "positions", "accounts", "yearly_returns", "logs"}


def _rows_to_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(str(key))
    lines = [",".join(_csv_cell(column) for column in columns)]
    for row in rows:
        lines.append(",".join(_csv_cell(row.get(column)) for column in columns))
    return "\n".join(lines)


def _csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(char in text for char in (",", '"', "\n", "\r")):
        text = '"' + text.replace('"', '""') + '"'
    return text





