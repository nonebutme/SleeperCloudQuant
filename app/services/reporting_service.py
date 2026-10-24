"""Service-layer facade for formal reporting reads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
from typing import Any

from app.schemas.reporting import (
    StrategyEvaluationChartPayload,
    StrategyEvaluationDimensionPayload,
    StrategyEvaluationMetricPayload,
    ParameterScanComparisonReportPayload,
    ParameterScanComparisonRowPayload,
    ReportSnapshotPayload,
    ReportSnapshotSummaryPayload,
    StrategyEvaluationReportPayload,
)
from domain.report.models import (
    BatchExperimentRowModel,
    BatchExperimentSummaryModel,
    BacktestRunDetailModel,
)
from reporting import BatchComparisonService, RunResultsReader
from app.services.backtest_advanced_analysis import build_advanced_analysis


class ReportingService:
    """Expose reporting reads through stable application models."""

    def __init__(
        self,
        results_reader: RunResultsReader,
        batch_comparison_service: BatchComparisonService,
        snapshot_store: Any | None = None,
    ) -> None:
        self._results_reader = results_reader
        self._batch_comparison_service = batch_comparison_service
        self._snapshot_store = snapshot_store
        self._completed_run_detail_cache: dict[str, BacktestRunDetailModel] = {}

    def get_run_detail(self, run_id: str) -> BacktestRunDetailModel | None:
        cached = self._completed_run_detail_cache.get(run_id)
        if cached is not None:
            return cached
        detail = self._results_reader.get_run_detail(run_id)
        if detail is None:
            return None
        run = dict(detail.run)
        raw_result = dict(run.get("raw_result") or {})
        account_value_chart = _dict_rows(self._results_reader.build_account_value_chart(detail))
        benchmark_curve = _dict_rows(raw_result.get("benchmark_curve") or [])
        excess_curve = _dict_rows(raw_result.get("excess_curve") or [])
        trades = _dict_rows(detail.trades)
        positions = _dict_rows(detail.positions)
        accounts = _dict_rows(detail.accounts)
        advanced = build_advanced_analysis(
            account_rows=accounts,
            benchmark_curve=benchmark_curve,
            excess_curve=excess_curve,
            trades=trades,
            metrics=dict(detail.metrics),
            raw_result=raw_result,
            extra_config=dict(run.get("extra_config") or {}),
        )
        model = BacktestRunDetailModel(
            run_id=str(run.get("run_id") or run_id),
            strategy_name=str(run.get("strategy_name") or "--"),
            status=str(run.get("status") or "--"),
            benchmark=_optional_str(run.get("benchmark")),
            benchmark_alignment=dict(raw_result.get("benchmark_alignment") or {}),
            benchmark_status=_optional_str(raw_result.get("benchmark_status")),
            start_date=_optional_str(run.get("start_date")),
            end_date=_optional_str(run.get("end_date")),
            strategy_id=_optional_str(run.get("strategy_id")),
            extra_config=dict(run.get("extra_config") or {}),
            metrics=dict(detail.metrics),
            account_value_chart=account_value_chart,
            drawdown_curve=_account_drawdown_curve(account_value_chart),
            benchmark_curve=benchmark_curve,
            excess_curve=excess_curve,
            trade_activity_chart=_dict_rows(
                self._results_reader.build_trade_activity_chart(detail)
            ),
            position_exposure_chart=_dict_rows(
                self._results_reader.build_position_exposure_chart(detail)
            ),
            yearly_return_chart=_dict_rows(
                self._results_reader.build_yearly_return_chart(detail)
            ),
            trades=trades,
            positions=positions,
            accounts=accounts,
            price_bars=list(advanced["price_bars"]),
            signal_evidence=dict(advanced["signal_evidence"]),
            monthly_return_heatmap=dict(advanced["monthly_return_heatmap"]),
            excess_drawdown_curve=list(advanced["excess_drawdown_curve"]),
            market_regimes=dict(advanced["market_regimes"]),
            execution_quality=dict(advanced["execution_quality"]),
            cost_capacity_stress=dict(advanced["cost_capacity_stress"]),
            robustness=dict(advanced["robustness"]),
            parameter_sensitivity=dict(advanced["parameter_sensitivity"]),
            report_governance=dict(advanced["report_governance"]),
        )
        if model.status in {"completed", "partial_completed"}:
            self._completed_run_detail_cache[run_id] = model
        return model

    def get_strategy_evaluation(self, run_id: str) -> StrategyEvaluationReportPayload | None:
        detail = self.get_run_detail(run_id)
        if detail is None:
            return None
        metrics = detail.metrics
        diagnostics = _build_strategy_evaluation_diagnostics(detail)
        return_diag = dict(diagnostics.get("return") or {})
        risk_diag = dict(diagnostics.get("risk") or {})
        stability_diag = dict(diagnostics.get("stability") or {})
        trade_diag = dict(diagnostics.get("trade_quality") or {})
        cost_diag = dict(diagnostics.get("capacity_cost") or {})
        exposure_diag = dict(diagnostics.get("exposure") or {})
        data_diag = dict(diagnostics.get("data_quality") or {})

        total_return = _number(metrics, ("total_returns", "total_return"), float(return_diag.get("total_return") or 0.0))
        annual_return = _number(metrics, ("annualized_returns", "annual_return", "annual_returns"), float(return_diag.get("annualized_return") or total_return))
        sharpe = _number(metrics, ("sharpe", "sharpe_ratio"), float(risk_diag.get("sharpe_proxy") or 0.0))
        max_drawdown = abs(_number(metrics, ("max_drawdown", "drawdown"), float(risk_diag.get("max_drawdown") or 0.0)))
        volatility = abs(_number(metrics, ("volatility", "annual_volatility"), float(risk_diag.get("volatility") or 0.0)))
        yearly_rows = detail.yearly_return_chart or []
        year_win_rate = float(stability_diag.get("year_win_rate") or 0.0)
        positive_period_rate = float(stability_diag.get("positive_period_rate") or 0.0)
        trade_count = int(trade_diag.get("trade_count") or 0)
        estimated_win_rate = trade_diag.get("estimated_win_rate")
        holding_count = int(exposure_diag.get("latest_holding_count") or 0)
        max_single_weight = exposure_diag.get("max_single_weight")
        cost_rate = float(cost_diag.get("estimated_cost_rate") or 0.0)
        data_coverage = float(data_diag.get("coverage_score") or 0.0)
        evidence_quality = _build_strategy_evidence_quality(diagnostics)
        calmar = annual_return / max(max_drawdown, 0.01)
        sortino = float(risk_diag.get("sortino_proxy") or max(0.0, sharpe * 1.1))

        dimensions = [
            _dimension(
                key="return",
                short_label="收益真实",
                title="维度1：收益真实性",
                score=_clamp_score(45 + max(annual_return, -0.2) * 140 + data_coverage * 20),
                metrics=[
                    ("总收益率", _pct(total_return)),
                    ("年化收益率", _pct(annual_return)),
                    ("年度胜率", _pct(year_win_rate)),
                    ("数据覆盖", _pct(data_coverage)),
                ],
                chart=StrategyEvaluationChartPayload(
                    kind="bar",
                    rows=[
                        {"label": str(row.get("year", index + 1)), "value": _float(row.get("portfolio_return")) * 100, "display": _pct(row.get("portfolio_return"))}
                        for index, row in enumerate(yearly_rows)
                    ] or [{"label": "样本", "value": total_return * 100, "display": _pct(total_return)}],
                ),
            ),
            _dimension(
                key="risk",
                short_label="风险可控",
                title="维度2：风险可控性",
                score=_clamp_score(92 - max_drawdown * 180 - volatility * 45),
                metrics=[
                    ("最大回撤", _pct(max_drawdown)),
                    ("区间波动", _pct(volatility)),
                    ("最差区间收益", _pct(risk_diag.get("worst_period_return"))),
                    ("当前回撤", _pct(risk_diag.get("current_drawdown"))),
                ],
                chart=StrategyEvaluationChartPayload(
                    kind="line-danger",
                    rows=[
                        {"label": "最大回撤", "value": max_drawdown * 100, "display": _pct(max_drawdown)},
                        {"label": "当前回撤", "value": _float(risk_diag.get("current_drawdown")) * 100, "display": _pct(risk_diag.get("current_drawdown"))},
                        {"label": "最差收益", "value": abs(_float(risk_diag.get("worst_period_return"))) * 100, "display": _pct(risk_diag.get("worst_period_return"))},
                    ],
                ),
            ),
            _dimension(
                key="riskReturn",
                short_label="性价比",
                title="维度3：风险调整收益",
                score=_clamp_score(55 + sharpe * 16 + calmar * 5),
                metrics=[
                    ("Sharpe", f"{sharpe:.2f}"),
                    ("Calmar", f"{calmar:.2f}"),
                    ("Sortino 近似", f"{sortino:.2f}"),
                    ("收益/波动", f"{annual_return / max(volatility, 0.01):.2f}"),
                ],
                chart=StrategyEvaluationChartPayload(
                    kind="bar",
                    rows=[
                        {"label": "Sharpe", "value": sharpe, "display": f"{sharpe:.2f}"},
                        {"label": "Calmar", "value": calmar, "display": f"{calmar:.2f}"},
                        {"label": "Sortino", "value": sortino, "display": f"{sortino:.2f}"},
                    ],
                ),
            ),
            _dimension(
                key="stable",
                short_label="收益稳定",
                title="维度4：收益稳定性",
                score=_clamp_score(50 + year_win_rate * 22 + positive_period_rate * 24),
                metrics=[
                    ("年度胜率", _pct(year_win_rate)),
                    ("正收益区间占比", _pct(positive_period_rate)),
                    ("权益点数", str(stability_diag.get("equity_point_count") or 0)),
                    ("收益样本数", str(stability_diag.get("return_sample_count") or 0)),
                ],
                chart=StrategyEvaluationChartPayload(
                    kind="bar",
                    rows=[{"label": str(row.get("year", index + 1)), "value": _float(row.get("portfolio_return")) * 100, "display": _pct(row.get("portfolio_return"))} for index, row in enumerate(yearly_rows)]
                    or [{"label": "正收益", "value": positive_period_rate * 100, "display": _pct(positive_period_rate)}],
                ),
            ),
            _dimension(
                key="attr",
                short_label="交易质量",
                title="维度5：交易质量与归因",
                score=_clamp_score(58 + (float(estimated_win_rate or 0.0) * 28) + min(trade_count, 20) * 0.7),
                metrics=[
                    ("交易活跃点", str(trade_count)),
                    ("买入次数", str(trade_diag.get("buy_count") or 0)),
                    ("卖出次数", str(trade_diag.get("sell_count") or 0)),
                    ("估算胜率", _pct(estimated_win_rate)),
                ],
                chart=StrategyEvaluationChartPayload(kind="bar", rows=[
                    {"label": "买入", "value": trade_diag.get("buy_count") or 0},
                    {"label": "卖出", "value": trade_diag.get("sell_count") or 0},
                    {"label": "胜率", "value": float(estimated_win_rate or 0.0) * 100, "display": _pct(estimated_win_rate)},
                ]),
            ),
            _dimension(
                key="cost",
                short_label="成本容量",
                title="维度6：成本与容量适配性",
                score=_clamp_score(86 - cost_rate * 9000 - max(0, trade_count - 10) * 1.2),
                metrics=[
                    ("估算综合费率", _pct(cost_rate)),
                    ("成交额", _money(cost_diag.get("traded_amount"))),
                    ("成本估算", _money(cost_diag.get("estimated_cost"))),
                    ("交易频度", str(trade_count)),
                ],
                chart=StrategyEvaluationChartPayload(kind="line", rows=[
                    {"label": "费率", "value": cost_rate * 100, "display": _pct(cost_rate)},
                    {"label": "成本", "value": _float(cost_diag.get("estimated_cost")), "display": _money(cost_diag.get("estimated_cost"))},
                    {"label": "成交", "value": _float(cost_diag.get("traded_amount")), "display": _money(cost_diag.get("traded_amount"))},
                ]),
            ),
            _dimension(
                key="diverse",
                short_label="持仓分散",
                title="维度7：持仓分散度",
                score=_clamp_score(60 + min(holding_count, 12) * 3 - float(max_single_weight or 0.0) * 18),
                metrics=[
                    ("最新持仓数", str(holding_count)),
                    ("平均持仓数", f"{float(exposure_diag.get('average_holding_count') or 0.0):.1f}"),
                    ("单票最大权重", _pct(max_single_weight)),
                    ("最新市值", _money(exposure_diag.get("latest_market_value"))),
                ],
                chart=StrategyEvaluationChartPayload(kind="bar", rows=[
                    {"label": "最新持仓", "value": holding_count},
                    {"label": "平均持仓", "value": exposure_diag.get("average_holding_count") or 0},
                    {"label": "最大权重", "value": float(max_single_weight or 0.0) * 100, "display": _pct(max_single_weight)},
                ]),
            ),
        ]
        average = round(sum(item.score for item in dimensions) / len(dimensions))
        score_breakdown = {
            "average_score": average,
            "dimension_scores": {item.key: item.score for item in dimensions},
            "formula_version": "stage74-seven-dimension-evidence-v2",
            "weights": "equal_weight_7_dimensions_with_evidence_disclosure",
        }
        decision_flags = _build_strategy_decision_flags(average=average, diagnostics=diagnostics)
        analysis_summary = _build_strategy_analysis_summary(detail=detail, average=average, diagnostics=diagnostics, decision_flags=decision_flags)
        return StrategyEvaluationReportPayload(
            run_id=detail.run_id,
            strategy_name=detail.strategy_name,
            title="量化策略 7 维全方位评估报告",
            subtitle="阶段 74：基于本地回测明细、交易归因、风险曲线、成本和数据覆盖生成证据化策略评价。",
            average_score=average,
            dimensions=dimensions,
            conclusions=_build_strategy_conclusions(average=average, diagnostics=diagnostics, decision_flags=decision_flags),
            data_quality_notes=_build_strategy_quality_notes(diagnostics),
            diagnostics=diagnostics,
            score_breakdown=score_breakdown,
            decision_flags=decision_flags,
            analysis_summary=analysis_summary,
            report_version="stage74-strategy-evaluation-v2",
            evaluation_scope="single_run_or_shared_portfolio",
            evidence_quality=evidence_quality,
        )


    def create_report_package(
        self,
        run_id: str,
        *,
        symbol: str | None = None,
        workflow_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        if self._snapshot_store is None:
            raise RuntimeError("report package store is not configured")
        detail = self.get_run_detail(run_id)
        evaluation = self.get_strategy_evaluation(run_id)
        if detail is None or evaluation is None:
            return None
        workflow_row, binding_mode = self._select_ai_workflow_row(run_id=run_id, symbol=symbol, workflow_id=workflow_id)
        replay = self._build_ai_workflow_replay_payload(
            run_id=run_id,
            detail=detail,
            workflow_row=workflow_row,
            symbol=symbol,
            binding_mode=binding_mode,
        )
        created_at = datetime.now(timezone.utc).isoformat()
        package_id = f"{run_id}:research_package:{created_at}"
        snapshot_id = f"{run_id}:package_strategy_evaluation:{created_at}"
        package_title = title or f"{detail.strategy_name} 研究复盘包"
        evaluation_payload = asdict(evaluation)
        manifest = _build_report_package_manifest(
            package_id=package_id,
            run_id=run_id,
            snapshot_id=snapshot_id,
            created_at=created_at,
            title=package_title,
            detail=detail,
            replay=replay,
            symbol=symbol,
            binding_mode=binding_mode,
        )
        self._snapshot_store.save_report_snapshot(
            snapshot_id=snapshot_id,
            run_id=run_id,
            report_type="package_strategy_evaluation",
            report_version="research-package-v1",
            created_at=created_at,
            title=evaluation.title,
            payload=evaluation_payload,
        )
        payload = {
            "package_id": package_id,
            "run_id": run_id,
            "title": package_title,
            "created_at": created_at,
            "snapshot_id": snapshot_id,
            "workflow_id": replay.get("workflow_id"),
            "binding_mode": binding_mode,
            "manifest": manifest,
            "run_detail": asdict(detail),
            "strategy_evaluation": evaluation_payload,
            "ai_workflow_replay": replay,
                "data_quality_notes": [
                "已确认：报告包将 run、策略评估快照、AI workflow replay 和 manifest 固化在一个 payload 中。",
                "已确认：manifest 记录本地 SQLite 行情源、回测 runtime、LLM Provider trace、数据资产版本与验证命令，不落敏感密钥。",
                "已确认：若回测 run 已绑定 data_asset_trace，报告包会固化对应 data_version。",
                "待确认：真实生产环境仍需由任务编排层写入严格 session_id。",
            ],
        }
        self._snapshot_store.save_report_package(
            package_id=package_id,
            run_id=run_id,
            workflow_id=_optional_str(replay.get("workflow_id")),
            snapshot_id=snapshot_id,
            created_at=created_at,
            title=package_title,
            payload=payload,
        )
        return payload

    def create_experiment_comparison_package(self, run_id_prefix: str, *, title: str | None = None) -> dict[str, Any] | None:
        """Persist an auditable package for an experiment report comparison."""

        if self._snapshot_store is None:
            raise RuntimeError("report package store is not configured")
        comparison = self.get_experiment_report_comparison(run_id_prefix)
        if comparison.get("status") != "ready":
            return None
        created_at = datetime.now(timezone.utc).isoformat()
        package_id = f"{run_id_prefix}:experiment_comparison_package:{created_at}"
        snapshot_id = f"{run_id_prefix}:experiment_report_comparison:{created_at}"
        package_title = title or f"{run_id_prefix} 实验报告对比包"
        chart_source = {
            "score": [{"run_id": row.get("run_id"), "value": row.get("score")} for row in comparison.get("rows", [])],
            "annualized_return": [{"run_id": row.get("run_id"), "value": row.get("annualized_return")} for row in comparison.get("rows", [])],
            "max_drawdown": [{"run_id": row.get("run_id"), "value": row.get("max_drawdown")} for row in comparison.get("rows", [])],
            "data_versions": dict((comparison.get("summary") or {}).get("data_versions") and {"versions": (comparison.get("summary") or {}).get("data_versions")} or {"versions": []}),
        }
        manifest = {
            "manifest_version": "stage54-experiment-comparison-package-v1",
            "generated_at": created_at,
            "bindings": {
                "package_id": package_id,
                "run_id_prefix": run_id_prefix,
                "snapshot_id": snapshot_id,
                "title": package_title,
                "binding_mode": "run_id_prefix_comparison",
            },
            "comparison_summary": comparison.get("summary") or {},
            "verification": [
                "python scripts/smoke_test_experiment_report_comparison_package.py",
                "python scripts/run_formal_verifications.py",
            ],
        }
        snapshot_payload = {"comparison": comparison, "chart_source": chart_source, "manifest": manifest}
        self._snapshot_store.save_report_snapshot(
            snapshot_id=snapshot_id,
            run_id=run_id_prefix,
            report_type="experiment_report_comparison",
            report_version="stage54-experiment-comparison-package-v1",
            created_at=created_at,
            title=package_title,
            payload=snapshot_payload,
        )
        payload = {
            "package_id": package_id,
            "run_id": run_id_prefix,
            "run_id_prefix": run_id_prefix,
            "title": package_title,
            "created_at": created_at,
            "snapshot_id": snapshot_id,
            "workflow_id": None,
            "binding_mode": "run_id_prefix_comparison",
            "manifest": manifest,
            "experiment_report_comparison": comparison,
            "chart_source": chart_source,
            "data_quality_notes": [
                "已确认：实验对比报告包固化同一 run_id_prefix 下的评分、收益风险、数据版本和资产一致性。",
                "已确认：chart_source 保存前端图表所需源数据，导出时可复现阶段 53 图表。",
                "待确认：该包按 run_id_prefix 绑定实验，复杂实验索引映射后续可增强。",
            ],
        }
        self._snapshot_store.save_report_package(
            package_id=package_id,
            run_id=run_id_prefix,
            workflow_id=None,
            snapshot_id=snapshot_id,
            created_at=created_at,
            title=package_title,
            payload=payload,
        )
        return payload

    def list_report_packages(self, run_id: str) -> list[dict[str, Any]]:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "fetch_report_packages"):
            return []
        rows = self._snapshot_store.fetch_report_packages(run_id)
        return [
            {
                "package_id": str(row.get("package_id") or ""),
                "run_id": str(row.get("run_id") or ""),
                "workflow_id": row.get("workflow_id"),
                "snapshot_id": row.get("snapshot_id"),
                "created_at": str(row.get("created_at") or ""),
                "title": str(row.get("title") or ""),
                "binding_mode": str((row.get("payload") or {}).get("binding_mode") or "unknown"),
                "manifest_version": str(((row.get("payload") or {}).get("manifest") or {}).get("manifest_version") or ""),
            }
            for row in rows
        ]


    def list_report_package_directory(
        self,
        *,
        run_id: str | None = None,
        package_type: str | None = None,
        lifecycle_status: str | None = None,
        limit: int | str = 20,
    ) -> dict[str, Any]:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "fetch_report_package_directory"):
            return {"status": "unsupported", "summary": {"package_count": 0}, "packages": []}
        try:
            normalized_limit = max(1, min(int(limit or 20), 200))
        except (TypeError, ValueError):
            normalized_limit = 20
        normalized_type = (package_type or "").strip()
        normalized_lifecycle = (lifecycle_status or "").strip()
        rows = self._snapshot_store.fetch_report_package_directory(run_id=run_id or None, limit=normalized_limit)
        packages = [self._summarize_report_package(row) for row in rows]
        if normalized_type:
            packages = [item for item in packages if item.get("package_type") == normalized_type]
        if normalized_lifecycle:
            packages = [item for item in packages if item.get("lifecycle_status") == normalized_lifecycle]
        type_counts: dict[str, int] = {}
        run_counts: dict[str, int] = {}
        for item in packages:
            type_key = str(item.get("package_type") or "unknown")
            run_key = str(item.get("run_id") or "")
            type_counts[type_key] = type_counts.get(type_key, 0) + 1
            run_counts[run_key] = run_counts.get(run_key, 0) + 1
        return {
            "status": "ready",
            "summary": {
                "package_count": len(packages),
                "type_counts": type_counts,
                "run_counts": run_counts,
                "filters": {"run_id": run_id or "", "package_type": normalized_type, "lifecycle_status": normalized_lifecycle, "limit": normalized_limit},
            },
            "packages": packages,
        }

    def _summarize_report_package(self, row: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(row.get("payload") or {})
        manifest = dict(payload.get("manifest") or {})
        comparison = dict(payload.get("experiment_report_comparison") or {})
        comparison_summary = dict(comparison.get("summary") or {})
        package_type = "experiment_report_comparison" if comparison else "research_report_package"
        export_links = {
            "html": f"/api/reporting/report-packages/{row.get('package_id')}/export?format=html",
            "json": f"/api/reporting/report-packages/{row.get('package_id')}/export?format=json",
            "pdf": f"/api/reporting/report-packages/{row.get('package_id')}/export?format=pdf",
            "word": f"/api/reporting/report-packages/{row.get('package_id')}/export?format=word",
        }
        return {
            "package_id": str(row.get("package_id") or ""),
            "run_id": str(row.get("run_id") or ""),
            "title": str(row.get("title") or ""),
            "created_at": str(row.get("created_at") or ""),
            "workflow_id": row.get("workflow_id"),
            "snapshot_id": row.get("snapshot_id"),
            "binding_mode": str(payload.get("binding_mode") or ""),
            "manifest_version": str(manifest.get("manifest_version") or payload.get("manifest_version") or ""),
            "package_type": package_type,
            "run_count": comparison_summary.get("run_count"),
            "best_run_id": comparison_summary.get("best_run_id"),
            "asset_consistency_status": comparison_summary.get("asset_consistency_status"),
            "lifecycle_status": str((payload.get("lifecycle") or {}).get("status") or "active"),
            "retention_policy": str((payload.get("lifecycle") or {}).get("retention_policy") or "standard"),
            "protected": bool((payload.get("lifecycle") or {}).get("protected") or False),
            "lifecycle_updated_at": (payload.get("lifecycle") or {}).get("updated_at"),
            "lifecycle_audit_count": len((payload.get("lifecycle") or {}).get("audit_log") or []),
            "export_links": export_links,
        }


    def build_report_package_export_manifest(
        self,
        *,
        run_id: str | None = None,
        package_type: str | None = None,
        lifecycle_status: str | None = None,
        formats: str | Sequence[str] = "html,json",
        limit: int | str = 20,
    ) -> dict[str, Any]:
        directory = self.list_report_package_directory(
            run_id=run_id,
            package_type=package_type,
            lifecycle_status=lifecycle_status,
            limit=limit,
        )
        selected_formats = _normalize_export_formats(formats)
        created_at = datetime.now(timezone.utc).isoformat()
        summary = dict(directory.get("summary") or {})
        packages = []
        for item in directory.get("packages", []):
            package_id = str(item.get("package_id") or "")
            export_links = {
                fmt: f"/api/reporting/report-packages/{package_id}/export?format={fmt}"
                for fmt in selected_formats
            }
            packages.append(
                {
                    "package_id": package_id,
                    "run_id": item.get("run_id"),
                    "title": item.get("title"),
                    "package_type": item.get("package_type"),
                    "lifecycle_status": item.get("lifecycle_status") or "active",
                    "retention_policy": item.get("retention_policy") or "standard",
                    "protected": bool(item.get("protected") or False),
                    "manifest_version": item.get("manifest_version"),
                    "binding_mode": item.get("binding_mode"),
                    "snapshot_id": item.get("snapshot_id"),
                    "created_at": item.get("created_at"),
                    "export_links": export_links,
                }
            )
        lifecycle_counts: dict[str, int] = {}
        for item in packages:
            key = str(item.get("lifecycle_status") or "active")
            lifecycle_counts[key] = lifecycle_counts.get(key, 0) + 1
        manifest_id = f"report-package-export-manifest:{_safe_filename(run_id or 'all')}:{created_at}"
        return {
            "manifest_id": manifest_id,
            "manifest_version": "stage57-report-package-export-manifest-v1",
            "generated_at": created_at,
            "status": "ready",
            "filters": summary.get("filters") or {},
            "formats": selected_formats,
            "package_count": len(packages),
            "type_counts": summary.get("type_counts") or {},
            "lifecycle_counts": lifecycle_counts,
            "packages": packages,
            "offline_boundary": {
                "mode": "manifest_only",
                "no_files_written": True,
                "no_package_deleted": True,
                "export_content_endpoint": "/api/reporting/report-packages/{package_id}/export?format={format}",
            },
            "verification": [
                "python scripts/smoke_test_report_package_export_manifest.py",
                "python scripts/run_formal_verifications.py",
            ],
        }
    def update_report_package_lifecycle(
        self,
        package_id: str,
        *,
        status: str = "active",
        retention_policy: str | None = None,
        protected: bool = False,
        reason: str | None = None,
        updated_by: str | None = None,
    ) -> dict[str, Any] | None:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "update_report_package_payload"):
            return None
        row = self._snapshot_store.fetch_report_package(package_id)
        if row is None:
            return None
        payload = dict(row.get("payload") or {})
        normalized_status = _normalize_lifecycle_status(status)
        lifecycle = dict(payload.get("lifecycle") or {})
        audit_log = list(lifecycle.get("audit_log") or [])
        updated_at = datetime.now(timezone.utc).isoformat()
        entry = {
            "timestamp": updated_at,
            "status": normalized_status,
            "retention_policy": retention_policy or lifecycle.get("retention_policy") or "standard",
            "protected": bool(protected),
            "reason": reason or "",
            "updated_by": updated_by or "local-user",
            "action": "lifecycle_update",
        }
        audit_log.append(entry)
        lifecycle.update(
            {
                "status": normalized_status,
                "retention_policy": entry["retention_policy"],
                "protected": bool(protected),
                "reason": reason or "",
                "updated_by": entry["updated_by"],
                "updated_at": updated_at,
                "audit_log": audit_log[-50:],
            }
        )
        payload["lifecycle"] = lifecycle
        payload.setdefault("data_quality_notes", [])
        if isinstance(payload["data_quality_notes"], list):
            payload["data_quality_notes"].append(
                f"已确认：报告包生命周期状态更新为 {normalized_status}，保留策略 {entry['retention_policy']}，不删除原始报告包。"
            )
        updated = self._snapshot_store.update_report_package_payload(package_id, payload)
        if updated is None:
            return None
        result = dict(updated.get("payload") or {})
        if not result:
            result = dict(updated)
        return result
    def delete_report_package(self, package_id: str, *, reason: str = "?????????") -> dict[str, Any] | None:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "soft_delete_report_package"):
            return None
        return self._snapshot_store.soft_delete_report_package(package_id, deleted_at=datetime.now(timezone.utc).isoformat(), reason=reason)

    def delete_ai_workflow(self, workflow_id: str, *, reason: str = "??? AI ????") -> dict[str, Any] | None:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "soft_delete_ai_workflow_run"):
            return None
        return self._snapshot_store.soft_delete_ai_workflow_run(workflow_id, deleted_at=datetime.now(timezone.utc).isoformat(), reason=reason)

    def get_report_package(self, package_id: str) -> dict[str, Any] | None:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "fetch_report_package"):
            return None
        row = self._snapshot_store.fetch_report_package(package_id)
        if row is None:
            return None
        payload = dict(row.get("payload") or {})
        if not payload:
            payload = dict(row)
        return payload

    def export_report_package(self, package_id: str, *, export_format: str = "html") -> dict[str, Any] | None:
        package = self.get_report_package(package_id)
        if package is None:
            return None
        normalized = (export_format or "html").lower()
        if normalized == "json":
            return {
                "package_id": package_id,
                "format": "json",
                "filename": f"{_safe_filename(package_id)}.json",
                "content_type": "application/json; charset=utf-8",
                "content": self._render_report_package_json(package),
            }
        if normalized == "pdf":
            return {
                "package_id": package_id,
                "format": "pdf",
                "filename": f"{_safe_filename(package_id)}.pdf",
                "content_type": "application/pdf",
                "content": self._render_report_package_pdf(package),
            }
        if normalized in {"word", "doc"}:
            return {
                "package_id": package_id,
                "format": "word",
                "filename": f"{_safe_filename(package_id)}.doc",
                "content_type": "application/msword; charset=utf-8",
                "content": self._render_report_package_word(package),
            }
        return {
            "package_id": package_id,
            "format": "html",
            "filename": f"{_safe_filename(package_id)}.html",
            "content_type": "text/html; charset=utf-8",
            "content": self._render_report_package_html(package),
        }

    def _render_report_package_json(self, package: Mapping[str, Any]) -> str:
        import json

        return json.dumps(package, ensure_ascii=False, indent=2)

    def _render_report_package_word(self, package: Mapping[str, Any]) -> str:
        html = self._render_report_package_html(package)
        return html.replace("<html lang=\"zh-CN\">", "<html xmlns:o=\"urn:schemas-microsoft-com:office:office\" xmlns:w=\"urn:schemas-microsoft-com:office:word\" lang=\"zh-CN\">")

    def _render_report_package_pdf(self, package: Mapping[str, Any]) -> str:
        return _render_formal_pdf(package)


    def _render_experiment_comparison_package_html(self, package: Mapping[str, Any]) -> str:
        comparison = dict(package.get("experiment_report_comparison") or {})
        summary = dict(comparison.get("summary") or {})
        rows = list(comparison.get("rows") or [])
        manifest = dict(package.get("manifest") or {})
        chart_source = dict(package.get("chart_source") or {})
        row_html = "".join(
            "<tr>"
            f"<td>{escape(str(row.get('rank') or ''))}</td>"
            f"<td>{escape(str(row.get('run_id') or ''))}</td>"
            f"<td>{escape(str(row.get('score') or ''))}</td>"
            f"<td>{escape(str(row.get('verdict') or ''))}</td>"
            f"<td>{escape(str(row.get('annualized_return') or ''))}</td>"
            f"<td>{escape(str(row.get('max_drawdown') or ''))}</td>"
            f"<td>{escape(str(row.get('data_version') or ''))}</td>"
            "</tr>"
            for row in rows
        ) or "<tr><td colspan='7'>暂无实验对比记录</td></tr>"
        notes = "".join(f"<li>{escape(str(note))}</li>" for note in package.get("data_quality_notes", []))
        manifest_cards = _render_manifest_cards(manifest)
        manifest_json = _render_manifest_json(manifest)
        chart_json = escape(json.dumps(chart_source, ensure_ascii=False, indent=2))
        return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <title>{escape(str(package.get('title') or 'SleeperCloudQuant 实验对比报告包'))}</title>
  <style>
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 32px; color: #17202a; background: #f6f8fb; }}
    header, section {{ background: #fff; border: 1px solid #d9e1e8; border-radius: 8px; padding: 20px; margin-bottom: 18px; }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    article {{ border: 1px solid #e5ebf0; border-radius: 8px; padding: 12px; background: #fbfcfe; }}
    strong {{ color: #315f9f; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #d9e1e8; padding: 8px; text-align: left; vertical-align: top; word-break: break-word; }}
    th {{ background: #eef3f7; color: #5d6b78; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 8px; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(str(package.get('title') or 'SleeperCloudQuant 实验对比报告包'))}</h1>
    <p>Package: {escape(str(package.get('package_id') or ''))}</p>
    <p>Run Prefix: {escape(str(package.get('run_id_prefix') or package.get('run_id') or ''))} / Binding: {escape(str(package.get('binding_mode') or ''))}</p>
  </header>
  <section><h2>实验对比摘要</h2><div class=\"grid\"><article><h3>Run 数</h3><strong>{escape(str(summary.get('run_count') or 0))}</strong></article><article><h3>最佳 Run</h3><strong>{escape(str(summary.get('best_run_id') or ''))}</strong></article><article><h3>最佳评分</h3><strong>{escape(str(summary.get('best_score') or ''))}</strong></article><article><h3>资产一致性</h3><strong>{escape(str(summary.get('asset_consistency_status') or ''))}</strong></article></div></section>
  <section><h2>报告包 Manifest</h2><div class=\"grid\">{manifest_cards}</div><pre>{manifest_json}</pre></section>
  <section><h2>实验报告对比排名</h2><table><thead><tr><th>Rank</th><th>Run</th><th>评分</th><th>结论</th><th>年化</th><th>回撤</th><th>数据版本</th></tr></thead><tbody>{row_html}</tbody></table></section>
  <section><h2>图表源数据</h2><pre>{chart_json}</pre></section>
  <section><h2>数据质量与边界</h2><ul>{notes}</ul></section>
</body>
</html>"""
    def _render_report_package_html(self, package: Mapping[str, Any]) -> str:
        if package.get("experiment_report_comparison"):
            return self._render_experiment_comparison_package_html(package)
        evaluation = dict(package.get("strategy_evaluation") or {})
        replay = dict(package.get("ai_workflow_replay") or {})
        run_detail = dict(package.get("run_detail") or {})
        manifest = dict(package.get("manifest") or {})
        dimensions = list(evaluation.get("dimensions") or [])
        risk_votes = list(replay.get("risk_votes") or [])
        timeline = list(replay.get("timeline") or [])
        decision = dict(replay.get("portfolio_decision") or {})
        dimension_cards = "".join(
            f"<article><h3>{escape(str(item.get('title') or item.get('key') or '维度'))}</h3>"
            f"<strong>{escape(str(item.get('score') or ''))}/100</strong>"
            f"<p>{escape('；'.join(f'{metric.get('label')}: {metric.get('value')}' for metric in item.get('metrics', [])))}</p></article>"
            for item in dimensions
        )
        timeline_items = "".join(
            f"<li><strong>{escape(str(item.get('stage') or ''))}</strong> - {escape(str(item.get('summary') or ''))}</li>"
            for item in timeline
        )
        risk_items = "".join(
            f"<article><h3>{escape(str(item.get('agent') or 'Risk Analyst'))}</h3><strong>{escape(str(item.get('vote') or ''))}</strong><p>{escape(str(item.get('content') or ''))}</p></article>"
            for item in risk_votes
        )
        notes = "".join(f"<li>{escape(str(note))}</li>" for note in package.get("data_quality_notes", []))
        manifest_cards = _render_manifest_cards(manifest)
        manifest_json = _render_manifest_json(manifest)
        return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <title>{escape(str(package.get('title') or 'SleeperCloudQuant 研究报告包'))}</title>
  <style>
    body {{ font-family: Arial, 'Microsoft YaHei', sans-serif; margin: 32px; color: #17202a; background: #f6f8fb; }}
    header, section {{ background: #fff; border: 1px solid #d9e1e8; border-radius: 8px; padding: 20px; margin-bottom: 18px; }}
    h1, h2, h3 {{ margin: 0 0 10px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
    article {{ border: 1px solid #e5ebf0; border-radius: 8px; padding: 12px; background: #fbfcfe; }}
    strong {{ color: #315f9f; }}
    pre {{ white-space: pre-wrap; background: #111827; color: #f9fafb; padding: 12px; border-radius: 8px; }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(str(package.get('title') or 'SleeperCloudQuant 研究报告包'))}</h1>
    <p>Package: {escape(str(package.get('package_id') or ''))}</p>
    <p>Run: {escape(str(package.get('run_id') or ''))} / Workflow: {escape(str(package.get('workflow_id') or ''))} / Binding: {escape(str(package.get('binding_mode') or ''))}</p>
  </header>
  <section><h2>报告包 Manifest</h2><div class="grid">{manifest_cards}</div><pre>{manifest_json}</pre></section>
  <section><h2>回测摘要</h2><div class=\"grid\"><article><h3>策略</h3><p>{escape(str(run_detail.get('strategy_name') or ''))}</p></article><article><h3>状态</h3><p>{escape(str(run_detail.get('status') or ''))}</p></article><article><h3>基准</h3><p>{escape(str(run_detail.get('benchmark') or ''))}</p></article><article><h3>评分</h3><p>{escape(str(evaluation.get('average_score') or ''))}/100</p></article></div></section>
  <section><h2>7 维策略评估</h2><div class=\"grid\">{dimension_cards}</div></section>
  <section><h2>AI Workflow 推演</h2><ul>{timeline_items}</ul><div class=\"grid\">{risk_items}</div><article><h3>组合经理决策</h3><strong>{escape(str(decision.get('action') or ''))}</strong><p>{escape(str(decision.get('rationale') or ''))}</p></article></section>
  <section><h2>数据质量与边界</h2><ul>{notes}</ul></section>
  <section><h2>原始包摘要</h2><pre>{escape(str({'snapshot_id': package.get('snapshot_id'), 'created_at': package.get('created_at')}))}</pre></section>
</body>
</html>"""
    def _select_ai_workflow_row(
        self,
        *,
        run_id: str,
        symbol: str | None,
        workflow_id: str | None = None,
    ) -> tuple[Mapping[str, Any] | None, str]:
        if self._snapshot_store is None:
            return None, "store_missing"
        if workflow_id and hasattr(self._snapshot_store, "fetch_ai_workflow_run"):
            row = self._snapshot_store.fetch_ai_workflow_run(workflow_id)
            return row, "explicit_workflow_id" if row is not None else "explicit_workflow_missing"
        if hasattr(self._snapshot_store, "fetch_ai_workflow_runs_by_report"):
            rows = list(self._snapshot_store.fetch_ai_workflow_runs_by_report(report_id=run_id, symbol=symbol, limit=1))
            if rows:
                return rows[0], "report_id_exact"
        if hasattr(self._snapshot_store, "fetch_ai_workflow_runs"):
            rows = list(self._snapshot_store.fetch_ai_workflow_runs(symbol=symbol, limit=1))
            if rows:
                return rows[0], "symbol_latest_fallback"
        return None, "no_workflow"

    def _build_ai_workflow_replay_payload(
        self,
        *,
        run_id: str,
        detail: BacktestRunDetailModel,
        workflow_row: Mapping[str, Any] | None,
        symbol: str | None,
        binding_mode: str,
    ) -> dict[str, Any]:
        if workflow_row is None:
            return {
                "linked": False,
                "run_id": run_id,
                "symbol": symbol,
                "binding_mode": binding_mode,
                "reason": "no_ai_workflow_trace",
                "data_quality_notes": ["待确认：当前 run 尚未绑定 AI workflow trace。"],
            }
        workflow = dict(workflow_row.get("payload") or {})
        portfolio_decision = dict(workflow.get("portfolio_decision") or {})
        risk_votes = _dict_rows(workflow.get("risk_votes") or [])
        return {
            "linked": True,
            "run_id": run_id,
            "strategy_name": detail.strategy_name,
            "binding_mode": binding_mode,
            "workflow_id": str(workflow.get("workflow_id") or workflow_row.get("workflow_id") or ""),
            "symbol": str(workflow.get("symbol") or workflow_row.get("symbol") or symbol or ""),
            "analysis_date": workflow.get("analysis_date") or workflow_row.get("analysis_date"),
            "generated_at": workflow.get("generated_at") or workflow_row.get("generated_at"),
            "provider_mode": workflow.get("provider_mode") or workflow_row.get("provider_mode"),
            "llm_provider_trace": dict(workflow.get("llm_provider_trace") or {}),
            "source_trace": dict(workflow.get("source_trace") or {}),
            "workflow_config": {
                "enabled_analysts": list(workflow.get("enabled_analysts") or []),
                "enabled_researchers": list(workflow.get("enabled_researchers") or []),
                "risk_team": list(workflow.get("risk_team") or []),
                "max_debate_rounds": workflow.get("max_debate_rounds"),
                "decision_policy": workflow.get("decision_policy"),
            },
            "timeline": _dict_rows(workflow.get("timeline") or []),
            "agent_messages": _dict_rows(workflow.get("agent_messages") or []),
            "debate_rounds": _dict_rows(workflow.get("debate_rounds") or []),
            "risk_votes": risk_votes,
            "portfolio_decision": portfolio_decision,
            "summary_notes": [
                f"AI workflow {workflow.get('workflow_id') or workflow_row.get('workflow_id')} 以 {binding_mode} 方式绑定到 run {run_id}。",
                f"风险委员会共 {len(risk_votes)} 个投票，组合经理动作：{portfolio_decision.get('action') or 'unknown'}。",
                "该联动用于研究复盘，不构成实盘交易建议。",
            ],
            "data_quality_notes": [
                "已确认：AI workflow trace 从本地 SQLite runtime store 读取。",
                "已确认：报告包创建后会固化当前绑定结果。",
            ],
        }
    def get_ai_workflow_replay(self, run_id: str, *, symbol: str | None = None) -> dict[str, Any]:
        detail = self.get_run_detail(run_id)
        if detail is None:
            return {"linked": False, "run_id": run_id, "reason": "run_not_found"}
        workflow_row, binding_mode = self._select_ai_workflow_row(run_id=run_id, symbol=symbol)
        return self._build_ai_workflow_replay_payload(
            run_id=run_id,
            detail=detail,
            workflow_row=workflow_row,
            symbol=symbol,
            binding_mode=binding_mode,
        )

    def get_parameter_scan_comparison(self, run_id_prefix: str) -> ParameterScanComparisonReportPayload | None:
        if self._snapshot_store is None or not hasattr(self._snapshot_store, "fetch_backtest_runs_by_prefix"):
            return None
        runs = list(self._snapshot_store.fetch_backtest_runs_by_prefix(run_id_prefix))
        if not runs:
            return None
        rows: list[ParameterScanComparisonRowPayload] = []
        for run in runs:
            run_id = str(run.get("run_id") or "")
            metrics = _index_metric_rows(self._snapshot_store.fetch_backtest_metrics(run_id))
            parameters = dict(run.get("parameters") or {})
            extra_config = dict(run.get("extra_config") or {})
            annualized_returns = _optional_float(metrics.get("annualized_returns"))
            total_returns = _optional_float(metrics.get("total_returns"))
            max_drawdown = _optional_float(metrics.get("max_drawdown"))
            sharpe = _optional_float(metrics.get("sharpe"))
            score = _comparison_score(
                annualized_returns=annualized_returns,
                total_returns=total_returns,
                max_drawdown=max_drawdown,
                sharpe=sharpe,
            )
            rows.append(
                ParameterScanComparisonRowPayload(
                    rank=0,
                    run_id=run_id,
                    strategy_name=str(run.get("strategy_name") or "--"),
                    strategy_id=_optional_str(run.get("strategy_id")),
                    strategy_version=_optional_str(extra_config.get("strategy_version")),
                    parameters=parameters,
                    annualized_returns=annualized_returns,
                    total_returns=total_returns,
                    max_drawdown=max_drawdown,
                    sharpe=sharpe,
                    score=score,
                    status=str(run.get("status") or "unknown"),
                )
            )
        ranked = [
            ParameterScanComparisonRowPayload(
                rank=index + 1,
                run_id=row.run_id,
                strategy_name=row.strategy_name,
                strategy_id=row.strategy_id,
                strategy_version=row.strategy_version,
                parameters=row.parameters,
                annualized_returns=row.annualized_returns,
                total_returns=row.total_returns,
                max_drawdown=row.max_drawdown,
                sharpe=row.sharpe,
                score=row.score,
                status=row.status,
            )
            for index, row in enumerate(sorted(rows, key=lambda item: (-item.score, item.run_id)))
        ]
        best = ranked[0] if ranked else None
        recommendation = "暂无可用参数扫描结果。"
        if best is not None:
            recommendation = f"建议优先复核 {best.run_id}：综合分 {best.score:.4f}，参数 {best.parameters}。"
        return ParameterScanComparisonReportPayload(
            run_id_prefix=run_id_prefix,
            title="参数扫描结果对比报告",
            best_run_id=None if best is None else best.run_id,
            best_parameters={} if best is None else best.parameters,
            rows=ranked,
            recommendation=recommendation,
            data_quality_notes=[
                "已确认：对比报告读取已落库的参数扫描 run 和指标。",
                "待确认：综合分公式为 MVP 排名规则，后续可接入正式策略优化目标。",
            ],
        )

    def save_parameter_scan_comparison_snapshot(
        self,
        run_id_prefix: str,
        *,
        report_type: str = "parameter_scan_comparison",
        report_version: str = "parameter-scan-v1",
    ) -> ReportSnapshotPayload | None:
        if self._snapshot_store is None:
            raise RuntimeError("report snapshot store is not configured")
        report = self.get_parameter_scan_comparison(run_id_prefix)
        if report is None:
            return None
        created_at = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"{run_id_prefix}:{report_type}:{created_at}"
        payload = asdict(report)
        self._snapshot_store.save_report_snapshot(
            snapshot_id=snapshot_id,
            run_id=run_id_prefix,
            report_type=report_type,
            report_version=report_version,
            created_at=created_at,
            title=report.title,
            payload=payload,
        )
        return ReportSnapshotPayload(
            snapshot_id=snapshot_id,
            run_id=run_id_prefix,
            report_type=report_type,
            report_version=report_version,
            created_at=created_at,
            title=report.title,
            payload=payload,
        )
    def save_strategy_evaluation_snapshot(
        self,
        run_id: str,
        *,
        report_type: str = "strategy_evaluation",
        report_version: str = "three2-v1",
    ) -> ReportSnapshotPayload | None:
        if self._snapshot_store is None:
            raise RuntimeError("report snapshot store is not configured")
        report = self.get_strategy_evaluation(run_id)
        if report is None:
            return None
        created_at = datetime.now(timezone.utc).isoformat()
        snapshot_id = f"{run_id}:{report_type}:{created_at}"
        payload = asdict(report)
        self._snapshot_store.save_report_snapshot(
            snapshot_id=snapshot_id,
            run_id=run_id,
            report_type=report_type,
            report_version=report_version,
            created_at=created_at,
            title=report.title,
            payload=payload,
        )
        return ReportSnapshotPayload(
            snapshot_id=snapshot_id,
            run_id=run_id,
            report_type=report_type,
            report_version=report_version,
            created_at=created_at,
            title=report.title,
            payload=payload,
        )

    def list_report_snapshots(
        self,
        run_id: str,
        *,
        report_type: str | None = "strategy_evaluation",
    ) -> list[ReportSnapshotSummaryPayload]:
        if self._snapshot_store is None:
            return []
        rows = self._snapshot_store.fetch_report_snapshots(run_id=run_id, report_type=report_type)
        return [
            ReportSnapshotSummaryPayload(
                snapshot_id=str(row.get("snapshot_id")),
                run_id=str(row.get("run_id")),
                report_type=str(row.get("report_type")),
                report_version=str(row.get("report_version")),
                created_at=str(row.get("created_at")),
                title=str(row.get("title")),
            )
            for row in rows
        ]

    def get_report_snapshot(self, snapshot_id: str) -> ReportSnapshotPayload | None:
        if self._snapshot_store is None:
            return None
        row = self._snapshot_store.fetch_report_snapshot(snapshot_id)
        if row is None:
            return None
        return ReportSnapshotPayload(
            snapshot_id=str(row.get("snapshot_id")),
            run_id=str(row.get("run_id")),
            report_type=str(row.get("report_type")),
            report_version=str(row.get("report_version")),
            created_at=str(row.get("created_at")),
            title=str(row.get("title")),
            payload=dict(row.get("payload") or {}),
        )
    def get_experiment_report_comparison(self, run_id_prefix: str) -> dict[str, Any]:
        """Compare strategy evaluation reports across runs sharing one prefix."""

        if self._snapshot_store is None or not hasattr(self._snapshot_store, "fetch_backtest_runs_by_prefix"):
            return {"run_id_prefix": run_id_prefix, "status": "unsupported", "summary": {"run_count": 0}, "rows": []}
        runs = list(self._snapshot_store.fetch_backtest_runs_by_prefix(run_id_prefix))
        rows: list[dict[str, Any]] = []
        for run in runs:
            run_id = str(run.get("run_id") or "")
            if not run_id:
                continue
            evaluation = self.get_strategy_evaluation(run_id)
            if evaluation is None:
                continue
            diagnostics = dict(evaluation.diagnostics or {})
            returns = dict(diagnostics.get("return") or {})
            risk = dict(diagnostics.get("risk") or {})
            summary = dict(evaluation.analysis_summary or {})
            data_asset = dict(summary.get("data_asset") or {})
            rows.append({
                "rank": 0,
                "run_id": run_id,
                "strategy_name": evaluation.strategy_name,
                "status": str(run.get("status") or "unknown"),
                "score": evaluation.average_score,
                "verdict": summary.get("verdict") or "unknown",
                "total_return": returns.get("total_return"),
                "annualized_return": returns.get("annualized_return"),
                "max_drawdown": risk.get("max_drawdown"),
                "volatility": risk.get("volatility"),
                "data_version": data_asset.get("data_version"),
                "quality_status": data_asset.get("quality_status"),
                "coverage_status": data_asset.get("coverage_status"),
                "symbol": data_asset.get("symbol") or run.get("universe"),
                "action_count": len(summary.get("action_items") or []),
            })
        rows = sorted(rows, key=lambda row: (-(int(row.get("score") or 0)), _float(row.get("max_drawdown")), str(row.get("run_id") or "")))
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        data_versions = sorted({str(row.get("data_version") or "") for row in rows if row.get("data_version")})
        missing_count = sum(1 for row in rows if not row.get("data_version") or row.get("data_version") == "not_bound")
        if not rows:
            consistency_status = "empty"
        elif missing_count == len(rows):
            consistency_status = "missing"
        elif len(data_versions) <= 1 and missing_count == 0:
            consistency_status = "consistent"
        else:
            consistency_status = "mixed"
        best = rows[0] if rows else {}
        worst = rows[-1] if rows else {}
        return {
            "run_id_prefix": run_id_prefix,
            "status": "ready" if rows else "not_found",
            "summary": {
                "run_count": len(rows),
                "best_run_id": best.get("run_id"),
                "worst_run_id": worst.get("run_id"),
                "best_score": best.get("score"),
                "worst_score": worst.get("score"),
                "data_version_count": len(data_versions),
                "missing_data_version_count": missing_count,
                "asset_consistency_status": consistency_status,
                "data_versions": data_versions,
                "symbols": sorted({str(row.get("symbol") or "") for row in rows if row.get("symbol")}),
            },
            "rows": rows,
            "links": {
                "portfolio_panel": f"/api/backtest/results/{run_id_prefix}/portfolio-panel",
                "experiment_panel": f"/api/backtest/experiments/{run_id_prefix}/panel",
            },
        }

    def get_batch_summary(self, experiment_id: str) -> BatchExperimentSummaryModel | None:
        summary = self._batch_comparison_service.summarize_experiment(experiment_id)
        if summary is None:
            return None
        return BatchExperimentSummaryModel(
            experiment_id=summary.experiment_id,
            profile=summary.profile,
            status=summary.status,
            started_at=summary.started_at,
            finished_at=summary.finished_at,
            request_count=summary.request_count,
            success_count=summary.success_count,
            failure_count=summary.failure_count,
            rows=[_to_batch_row_model(row) for row in summary.rows],
            yearly_rows=_dict_rows(summary.yearly_rows),
            failures=_dict_rows(summary.failures),
            failure_type_counts=dict(summary.failure_type_counts),
            failure_stage_counts=dict(summary.failure_stage_counts),
            failure_code_counts=dict(summary.failure_code_counts),
        )




def _build_report_package_manifest(
    *,
    package_id: str,
    run_id: str,
    snapshot_id: str,
    created_at: str,
    title: str,
    detail: BacktestRunDetailModel,
    replay: Mapping[str, Any],
    symbol: str | None,
    binding_mode: str,
) -> dict[str, Any]:
    run_detail = asdict(detail)
    workflow_config = dict(replay.get("workflow_config") or {})
    llm_trace = dict(replay.get("llm_provider_trace") or {})
    provider_profile = str(llm_trace.get("provider_profile") or replay.get("provider_mode") or workflow_config.get("provider_profile") or "local-demo-tradingagents-style")
    llm_status = str(llm_trace.get("status") or "not_recorded")
    extra_config = dict(run_detail.get("extra_config") or {})
    data_asset_trace = dict(extra_config.get("data_asset_trace") or {})
    data_asset = dict(data_asset_trace.get("asset") or {}) if isinstance(data_asset_trace.get("asset"), Mapping) else {}
    runtime_mode = str(extra_config.get("runtime_mode") or "local_sqlite_backtest")
    manifest_symbol = str(symbol or replay.get("symbol") or run_detail.get("universe") or data_asset_trace.get("symbol") or "000001.XSHE")
    return {
        "manifest_version": "stage20-report-package-manifest-v1",
        "generated_at": created_at,
        "bindings": {
            "package_id": package_id,
            "run_id": run_id,
            "workflow_id": replay.get("workflow_id"),
            "snapshot_id": snapshot_id,
            "symbol": manifest_symbol,
            "binding_mode": binding_mode,
            "title": title,
        },
        "data_sources": [
            {
                "source_id": "legacy_sqlite_market_data",
                "label": "SleeperCloudQuant-old local SQLite A-share data",
                "mode": "read_only_local_sqlite",
                "path_hint": "SleeperCloudQuant-old/SleeperCloudQuant/data/app_cache.db or SCQ_LEGACY_MARKET_DB_PATH",
                "fallback": "FakeMarketDataRepository demo bars when legacy DB is unavailable",
                "status": "stage17_integrated",
            },
            {
                "source_id": "runtime_store",
                "label": "local runtime SQLite store",
                "mode": "local_audit_store",
                "status": "stores backtest runs, metrics, trades, accounts, AI workflow traces, snapshots, report packages",
            },
        ],
        "runtime": {
            "engine": "local_sqlite_backtest_runtime",
            "compatibility_target": "rqalpha run-once style payload/result boundary",
            "runtime_mode": runtime_mode,
            "strategy_id": run_detail.get("strategy_id"),
            "strategy_name": run_detail.get("strategy_name"),
            "true_rqalpha_package_status": "pending_external_package_integration",
        },
        "data_assets": {
            "status": data_asset_trace.get("status") or "not_bound",
            "symbol": data_asset_trace.get("symbol") or manifest_symbol,
            "source_endpoint": data_asset_trace.get("source_endpoint"),
            "bound_at": data_asset_trace.get("bound_at"),
            "data_version": data_asset.get("data_version"),
            "quality_status": data_asset.get("quality_status"),
            "coverage_status": data_asset.get("coverage_status"),
            "row_count": data_asset.get("row_count"),
            "start_date": data_asset.get("start_date"),
            "end_date": data_asset.get("end_date"),
            "source_counts": data_asset.get("source_counts", {}),
            "trace_manifest": data_asset_trace.get("manifest", {}),
        },
        "llm_provider": {
            "provider_profile": provider_profile,
            "status": llm_status,
            "external_call_enabled": llm_status == "completed",
            "model": llm_trace.get("model"),
            "reason": llm_trace.get("reason"),
            "secret_policy": "API keys and tokens are never persisted in report packages.",
        },
        "verification": {
            "commands": [
                "python scripts\\run_formal_verifications.py",
                "python scripts\\smoke_test_legacy_sqlite_market_data.py",
                "python scripts\\smoke_test_local_sqlite_backtest_runtime.py",
                "python scripts\\smoke_test_ai_config_api.py",
                "python scripts\\smoke_test_report_package_manifest.py",
                "python scripts\\smoke_test_report_package_exports.py",
                "python scripts\\smoke_test_backtest_data_asset_trace.py",
            ],
            "status": "manifest_generated_with_package",
        },
        "boundaries": [
            "本报告包用于本地研究复盘，不构成投资建议。",
            "外部 LLM 仅在 SCQ_LLM_BASE_URL、SCQ_LLM_API_KEY、SCQ_LLM_MODEL 均配置时调用；否则回落本地 demo。",
            "真实 rqalpha 包接入仍为后续阶段，当前 runtime 为 rqalpha-compatible 本地 SQLite 最小实现。",
            "五仓库源码相似度扫描按需执行；当前以功能重构和来源清单追踪为主。",
            "报告包 manifest 不写入密钥、口令、令牌或证书。",
        ],
        "artifacts": {
            "title": title,
            "package_id": package_id,
            "created_at": created_at,
            "export_formats": ["html", "json", "pdf", "word"],
        },
    }


def _render_manifest_cards(manifest: Mapping[str, Any]) -> str:
    bindings = dict(manifest.get("bindings") or {})
    runtime = dict(manifest.get("runtime") or {})
    llm_provider = dict(manifest.get("llm_provider") or {})
    data_sources = list(manifest.get("data_sources") or [])
    cards = [
        ("Manifest", manifest.get("manifest_version") or "not_available"),
        ("绑定", f"run={bindings.get('run_id') or ''} / workflow={bindings.get('workflow_id') or '无'}"),
        ("数据源", ", ".join(str(item.get("source_id") or "") for item in data_sources) or "not_recorded"),
        ("Runtime", runtime.get("engine") or "not_recorded"),
        ("LLM Provider", f"{llm_provider.get('provider_profile') or 'unknown'} / {llm_provider.get('status') or 'unknown'}"),
        ("导出", ", ".join(manifest.get("artifacts", {}).get("export_formats", [])) or "html,json"),
    ]
    return "".join(f"<article><h3>{escape(str(label))}</h3><p>{escape(str(value))}</p></article>" for label, value in cards)


def _render_manifest_json(manifest: Mapping[str, Any]) -> str:
    import json

    return escape(json.dumps(dict(manifest), ensure_ascii=False, indent=2))

def _formal_pdf_pages(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    manifest = dict(package.get("manifest") or {})
    bindings = dict(manifest.get("bindings") or {})
    runtime = dict(manifest.get("runtime") or {})
    llm_provider = dict(manifest.get("llm_provider") or {})
    evaluation = dict(package.get("strategy_evaluation") or {})
    replay = dict(package.get("ai_workflow_replay") or {})
    run_detail = dict(package.get("run_detail") or {})
    metrics = dict(run_detail.get("metrics") or {})
    dimensions = list(evaluation.get("dimensions") or [])
    risk_votes = list(replay.get("risk_votes") or [])
    decision = dict(replay.get("portfolio_decision") or {})
    data_sources = list(manifest.get("data_sources") or [])
    boundaries = list(manifest.get("boundaries") or [])
    return [
        {
            "title": "Executive Overview",
            "subtitle": package.get("title") or "SleeperCloudQuant Research Package",
            "cards": [
                ("Run", package.get("run_id") or bindings.get("run_id") or ""),
                ("Workflow", package.get("workflow_id") or bindings.get("workflow_id") or "none"),
                ("Manifest", manifest.get("manifest_version") or "not_available"),
                ("Runtime", runtime.get("engine") or "not_recorded"),
                ("LLM", f"{llm_provider.get('provider_profile') or 'unknown'} / {llm_provider.get('status') or 'unknown'}"),
                ("Score", str(evaluation.get("average_score") or "not_recorded")),
            ],
            "lines": [
                f"Package: {package.get('package_id') or bindings.get('package_id') or ''}",
                f"Manifest version: {manifest.get('manifest_version') or 'not_available'}",
                f"Created: {package.get('created_at') or manifest.get('generated_at') or ''}",
                "Purpose: local research replay and audit package.",
                "Boundary: research use only; not investment advice.",
            ],
        },
        {
            "title": "Backtest And Strategy Review",
            "subtitle": run_detail.get("strategy_name") or "strategy review",
            "cards": [
                ("Strategy", run_detail.get("strategy_name") or ""),
                ("Status", run_detail.get("status") or ""),
                ("Benchmark", run_detail.get("benchmark") or ""),
                ("Total Return", _pdf_value(metrics.get("total_returns"))),
                ("Max Drawdown", _pdf_value(metrics.get("max_drawdown"))),
                ("Sharpe", _pdf_value(metrics.get("sharpe"))),
            ],
            "lines": [
                f"Dimension count: {len(dimensions)}",
                *[f"{item.get('short_label') or item.get('key')}: {item.get('score')}/100 - {item.get('title') or ''}" for item in dimensions[:7]],
            ],
        },
        {
            "title": "AI Workflow And Risk Committee",
            "subtitle": f"Provider trace: {llm_provider.get('status') or 'unknown'}",
            "cards": [
                ("Provider", llm_provider.get("provider_profile") or "unknown"),
                ("Status", llm_provider.get("status") or "unknown"),
                ("Decision", decision.get("action") or "unknown"),
                ("Risk Votes", str(len(risk_votes))),
            ],
            "lines": [
                f"Decision rationale: {decision.get('rationale') or 'not recorded'}",
                *[f"{vote.get('agent') or 'Risk Analyst'}: {vote.get('vote') or 'unknown'} - {vote.get('content') or ''}" for vote in risk_votes[:6]],
            ],
        },
        {
            "title": "Manifest, Sources, And Boundaries",
            "subtitle": "audit trail",
            "cards": [
                ("Data Sources", str(len(data_sources))),
                ("Exports", ", ".join(manifest.get("artifacts", {}).get("export_formats", []))),
                ("Binding", bindings.get("binding_mode") or package.get("binding_mode") or "unknown"),
                ("Symbol", bindings.get("symbol") or ""),
            ],
            "lines": [
                *[f"Source {index + 1}: {source.get('source_id') or ''} / {source.get('mode') or ''}" for index, source in enumerate(data_sources)],
                *[f"Boundary: {item}" for item in boundaries],
            ],
        },
    ]


def _render_formal_pdf(package: Mapping[str, Any]) -> str:
    pages = _formal_pdf_pages(package)
    page_objects: list[tuple[int, int]] = []
    objects: list[str] = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
    ]
    page_kids: list[str] = []
    next_object_id = 3
    for index, page in enumerate(pages, start=1):
        page_id = next_object_id
        content_id = next_object_id + 1
        next_object_id += 2
        page_kids.append(f"{page_id} 0 R")
        stream = _render_pdf_page_stream(page, page_number=index, page_count=len(pages))
        page_objects.append((page_id, content_id))
        objects.append(f"{page_id} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {next_object_id} 0 R /F2 {next_object_id + 1} 0 R >> >> /Contents {content_id} 0 R >>\nendobj\n")
        objects.append(f"{content_id} 0 obj\n<< /Length {len(stream.encode('ascii'))} >>\nstream\n{stream}\nendstream\nendobj\n")
    font_regular_id = next_object_id
    font_bold_id = next_object_id + 1
    pages_object = f"2 0 obj\n<< /Type /Pages /Kids [{' '.join(page_kids)}] /Count {len(page_kids)} >>\nendobj\n"
    objects.insert(1, pages_object)
    objects.append(f"{font_regular_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objects.append(f"{font_bold_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")
    pdf = "%PDF-1.4\n"
    offsets = [0]
    for item in objects:
        offsets.append(len(pdf.encode("ascii")))
        pdf += item
    xref_offset = len(pdf.encode("ascii"))
    pdf += f"xref\n0 {len(objects) + 1}\n"
    pdf += "0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    return pdf


def _render_pdf_page_stream(page: Mapping[str, Any], *, page_number: int, page_count: int) -> str:
    commands = [
        "0.96 0.98 1 rg 0 0 595 842 re f",
        "0.12 0.20 0.32 rg 0 792 595 50 re f",
        "0.88 0.93 0.98 rg 36 694 523 74 re f",
        "0.70 0.78 0.88 RG 36 694 523 74 re S",
        _pdf_text(48, 810, "SleeperCloudQuant", size=10, font="F2", color=(1, 1, 1)),
        _pdf_text(408, 810, "Research Report Package", size=9, font="F1", color=(1, 1, 1)),
        _pdf_text(48, 744, str(page.get("title") or "Report"), size=21, font="F2", color=(0.10, 0.16, 0.25)),
        _pdf_text(48, 720, str(page.get("subtitle") or ""), size=10, font="F1", color=(0.22, 0.30, 0.42)),
    ]
    cards = list(page.get("cards") or [])
    for idx, (label, value) in enumerate(cards[:6]):
        col = idx % 3
        row = idx // 3
        x = 48 + col * 166
        y = 626 - row * 76
        commands.extend(_pdf_card(x, y, str(label), str(value)))
    y = 452
    commands.append(_pdf_text(48, y, "Key Evidence", size=13, font="F2", color=(0.10, 0.16, 0.25)))
    y -= 26
    for line in list(page.get("lines") or [])[:14]:
        for wrapped in _wrap_ascii(str(line), 92):
            commands.append(_pdf_text(58, y, f"- {wrapped}", size=9, font="F1", color=(0.14, 0.19, 0.28)))
            y -= 16
            if y < 78:
                break
        if y < 78:
            commands.append(_pdf_text(58, y, "- Additional lines omitted in this export summary.", size=9, font="F1", color=(0.45, 0.16, 0.12)))
            break
    commands.extend([
        "0.70 0.78 0.88 RG 36 54 523 0.5 re f",
        _pdf_text(48, 36, "Local MVP audit export - generated without secrets - not investment advice", size=8, font="F1", color=(0.30, 0.36, 0.46)),
        _pdf_text(500, 36, f"Page {page_number}/{page_count}", size=8, font="F1", color=(0.30, 0.36, 0.46)),
    ])
    return "\n".join(commands)


def _pdf_card(x: int, y: int, label: str, value: str) -> list[str]:
    return [
        f"1 1 1 rg {x} {y} 150 56 re f",
        f"0.80 0.86 0.92 RG {x} {y} 150 56 re S",
        _pdf_text(x + 10, y + 36, label, size=8, font="F2", color=(0.34, 0.41, 0.52)),
        _pdf_text(x + 10, y + 18, _ellipsize_ascii(value, 28), size=9, font="F1", color=(0.08, 0.13, 0.22)),
    ]


def _pdf_text(x: int, y: int, value: str, *, size: int, font: str, color: tuple[float, float, float]) -> str:
    r, g, b = color
    return f"{r:.2f} {g:.2f} {b:.2f} rg BT /{font} {size} Tf {x} {y} Td ({_pdf_escape(_ascii_only(value))}) Tj ET"


def _wrap_ascii(value: str, width: int) -> list[str]:
    words = _ascii_only(value).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}"
    lines.append(current)
    return lines


def _ellipsize_ascii(value: str, limit: int) -> str:
    ascii_value = _ascii_only(value)
    return ascii_value if len(ascii_value) <= limit else ascii_value[: max(0, limit - 3)] + "..."


def _pdf_value(value: Any) -> str:
    if value is None:
        return "not_recorded"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(numeric) <= 2:
        return f"{numeric * 100:.2f}%"
    return f"{numeric:.4f}"


def _ascii_only(value: str) -> str:
    return "".join(char if 32 <= ord(char) <= 126 else "?" for char in str(value))


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _normalize_export_formats(formats: str | Sequence[str]) -> list[str]:
    allowed = {"html", "json", "pdf", "word"}
    if isinstance(formats, str):
        raw_items = [item.strip().lower() for item in formats.split(",")]
    else:
        raw_items = [str(item).strip().lower() for item in formats]
    result = []
    for item in raw_items:
        normalized = "word" if item == "doc" else item
        if normalized in allowed and normalized not in result:
            result.append(normalized)
    return result or ["html", "json"]
def _normalize_lifecycle_status(status: str | None) -> str:
    normalized = (status or "active").strip().lower()
    if normalized in {"active", "archived", "protected", "review"}:
        return normalized
    return "active"
def _safe_filename(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    return "".join(safe).strip("_") or "report_package"

def _build_strategy_evaluation_diagnostics(detail: BacktestRunDetailModel) -> dict[str, Any]:
    metrics = dict(detail.metrics or {})
    account_rows = list(detail.account_value_chart or [])
    yearly_rows = list(detail.yearly_return_chart or [])
    trade_rows = list(detail.trade_activity_chart or [])
    exposure_rows = list(detail.position_exposure_chart or [])
    values = [_float(row.get("total_value") if row.get("total_value") is not None else row.get("unit_net_value"), fallback=0.0) for row in account_rows]
    values = [value for value in values if value > 0]
    period_returns = [(current / previous) - 1 for previous, current in zip(values, values[1:]) if previous]
    total_return = (values[-1] / values[0] - 1) if len(values) >= 2 and values[0] else _number(metrics, ("total_returns", "total_return"), 0.0)
    annualized_return = _number(metrics, ("annualized_returns", "annual_return", "annual_returns"), total_return)
    max_drawdown, current_drawdown = _drawdown_stats(values)
    volatility = _stddev(period_returns)
    downside = [value for value in period_returns if value < 0]
    downside_vol = _stddev(downside)
    sharpe_proxy = _number(metrics, ("sharpe", "sharpe_ratio"), (sum(period_returns) / len(period_returns) / max(volatility, 0.0001)) if period_returns else 0.0)
    sortino_proxy = (sum(period_returns) / len(period_returns) / max(downside_vol, 0.0001)) if period_returns else 0.0
    yearly_win_rate = _yearly_win_rate(yearly_rows)
    positive_period_rate = sum(1 for item in period_returns if item > 0) / len(period_returns) if period_returns else 0.0
    buy_count = sum(int(row.get("buy_count") or 0) for row in trade_rows)
    sell_count = sum(int(row.get("sell_count") or 0) for row in trade_rows)
    buy_amount = sum(_float(row.get("buy_amount")) for row in trade_rows)
    sell_amount = sum(_float(row.get("sell_amount")) for row in trade_rows)
    traded_amount = buy_amount + sell_amount
    engine_win_rate = metrics.get("win_rate")
    win_rate_source = "engine_closed_trades" if engine_win_rate is not None else "estimated_sell_days"
    reported_win_rate = _float(engine_win_rate) if engine_win_rate is not None else _estimate_trade_win_rate(trade_rows)
    cost_rate = _estimate_report_cost_rate(detail.extra_config)
    latest_exposure = exposure_rows[-1] if exposure_rows else {}
    latest_market_value = _float(latest_exposure.get("position_market_value"))
    latest_total_value = values[-1] if values else latest_market_value
    latest_holding_count = int(latest_exposure.get("position_count") or 0)
    max_single_weight = min(1.0, latest_market_value / latest_total_value) if latest_total_value else None
    average_holding_count = sum(int(row.get("position_count") or 0) for row in exposure_rows) / len(exposure_rows) if exposure_rows else 0.0
    data_points = {
        "account_points": len(account_rows),
        "trade_points": len(trade_rows),
        "exposure_points": len(exposure_rows),
        "yearly_points": len(yearly_rows),
        "metric_count": len(metrics),
    }
    coverage_score = min(1.0, (min(len(account_rows), 2) / 2 * 0.35) + (min(len(yearly_rows), 1) * 0.20) + (min(len(trade_rows), 1) * 0.20) + (min(len(exposure_rows), 1) * 0.15) + (min(len(metrics), 4) / 4 * 0.10))
    return {
        "return": {"total_return": total_return, "annualized_return": annualized_return},
        "risk": {
            "max_drawdown": max_drawdown,
            "current_drawdown": current_drawdown,
            "volatility": volatility,
            "best_period_return": max(period_returns) if period_returns else None,
            "worst_period_return": min(period_returns) if period_returns else None,
            "sharpe_proxy": sharpe_proxy,
            "sortino_proxy": sortino_proxy,
        },
        "stability": {
            "year_win_rate": yearly_win_rate,
            "positive_period_rate": positive_period_rate,
            "equity_point_count": len(values),
            "return_sample_count": len(period_returns),
        },
        "trade_quality": {
            "trade_count": buy_count + sell_count,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "buy_amount": buy_amount,
            "sell_amount": sell_amount,
            # Keep the legacy key for report/UI compatibility, but prefer the
            # backtest engine's closed-trade metric whenever it is available.
            "estimated_win_rate": reported_win_rate,
            "win_rate": reported_win_rate,
            "win_rate_source": win_rate_source,
        },
        "capacity_cost": {
            "estimated_cost_rate": cost_rate,
            "traded_amount": traded_amount,
            "estimated_cost": traded_amount * cost_rate,
            "turnover_proxy": traded_amount / latest_total_value if latest_total_value else None,
        },
        "exposure": {
            "latest_holding_count": latest_holding_count,
            "average_holding_count": average_holding_count,
            "latest_market_value": latest_market_value,
            "max_single_weight": max_single_weight,
        },
        "data_quality": {"coverage_score": coverage_score, "points": data_points},
    }


def _drawdown_stats(values: Sequence[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    peak = values[0]
    max_drawdown = 0.0
    current_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = (value / peak) - 1 if peak else 0.0
        current_drawdown = drawdown
        max_drawdown = min(max_drawdown, drawdown)
    return abs(max_drawdown), abs(current_drawdown)


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    return (sum((value - average) ** 2 for value in values) / (len(values) - 1)) ** 0.5


def _yearly_win_rate(yearly_rows: Sequence[Mapping[str, Any]]) -> float:
    if not yearly_rows:
        return 0.0
    wins = sum(1 for row in yearly_rows if _float(row.get("portfolio_return")) > _float(row.get("benchmark_return")))
    return wins / len(yearly_rows)


def _estimate_trade_win_rate(trade_rows: Sequence[Mapping[str, Any]]) -> float | None:
    sell_days = [row for row in trade_rows if int(row.get("sell_count") or 0) > 0]
    if not sell_days:
        return None
    wins = sum(1 for row in sell_days if _float(row.get("sell_amount")) >= _float(row.get("buy_amount")))
    return wins / len(sell_days)


def _estimate_report_cost_rate(extra_config: Mapping[str, Any]) -> float:
    rqalpha = extra_config.get("rqalpha_local") if isinstance(extra_config.get("rqalpha_local"), Mapping) else {}
    keys = ("commission_rate", "tax_rate", "slippage_rate")
    configured = sum(abs(_float(rqalpha.get(key))) for key in keys)
    return configured


def _clamp_score(value: float, *, low: int = 35, high: int = 98) -> int:
    return max(low, min(high, round(value)))


def _money(value: Any) -> str:
    raw = _float(value)
    if abs(raw) >= 100000000:
        return f"{raw / 100000000:.2f}亿"
    if abs(raw) >= 10000:
        return f"{raw / 10000:.2f}万"
    return f"{raw:.2f}"


def _build_strategy_evidence_quality(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    data_quality = dict(diagnostics.get("data_quality") or {})
    points = dict(data_quality.get("points") or {})
    account_points = int(points.get("account_points") or 0)
    trade_points = int(points.get("trade_points") or 0)
    exposure_points = int(points.get("exposure_points") or 0)
    yearly_points = int(points.get("yearly_points") or 0)
    coverage = float(data_quality.get("coverage_score") or 0.0)
    evidence_count = account_points + trade_points + exposure_points + yearly_points
    if coverage >= 0.8 and account_points >= 2 and trade_points >= 1:
        grade = "high"
    elif coverage >= 0.5 and evidence_count >= 3:
        grade = "medium"
    else:
        grade = "low"
    return {
        "grade": grade,
        "coverage_score": coverage,
        "points": points,
        "demo_fallback_used": False,
        "unavailable_capabilities": [item for item in [
            "out_of_sample_validation" if yearly_points < 2 else None,
            "real_capacity_model",
            "full_factor_attribution",
        ] if item],
    }


def _build_strategy_decision_flags(*, average: int, diagnostics: Mapping[str, Any]) -> list[dict[str, Any]]:
    risk = dict(diagnostics.get("risk") or {})
    trade = dict(diagnostics.get("trade_quality") or {})
    data_quality = dict(diagnostics.get("data_quality") or {})
    flags = [
        {"key": "score", "level": "pass" if average >= 70 else "watch", "label": "综合评分", "value": average},
        {"key": "drawdown", "level": "pass" if _float(risk.get("max_drawdown")) <= 0.2 else "warning", "label": "最大回撤", "value": _pct(risk.get("max_drawdown"))},
        {"key": "trade_sample", "level": "pass" if int(trade.get("trade_count") or 0) >= 2 else "warning", "label": "交易样本", "value": trade.get("trade_count") or 0},
        {"key": "data_coverage", "level": "pass" if _float(data_quality.get("coverage_score")) >= 0.65 else "warning", "label": "数据覆盖", "value": _pct(data_quality.get("coverage_score"))},
    ]
    return flags



def _build_strategy_analysis_summary(
    *,
    detail: BacktestRunDetailModel,
    average: int,
    diagnostics: Mapping[str, Any],
    decision_flags: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    returns = dict(diagnostics.get("return") or {})
    risk = dict(diagnostics.get("risk") or {})
    trade = dict(diagnostics.get("trade_quality") or {})
    cost = dict(diagnostics.get("capacity_cost") or {})
    exposure = dict(diagnostics.get("exposure") or {})
    data_quality = dict(diagnostics.get("data_quality") or {})
    trace = dict(detail.extra_config.get("data_asset_trace") or {}) if isinstance(detail.extra_config.get("data_asset_trace"), Mapping) else {}
    asset = dict(trace.get("asset") or {}) if isinstance(trace.get("asset"), Mapping) else {}
    warning_flags = [dict(flag) for flag in decision_flags if flag.get("level") == "warning"]
    watch_flags = [dict(flag) for flag in decision_flags if flag.get("level") == "watch"]
    data_version = asset.get("data_version") or "not_bound"
    quality_status = asset.get("quality_status") or "unknown"
    coverage_status = asset.get("coverage_status") or "unknown"
    max_drawdown = _float(risk.get("max_drawdown"))
    total_return = _float(returns.get("total_return"))
    trade_count = int(trade.get("trade_count") or 0)
    win_rate_label = "已平仓胜率" if trade.get("win_rate_source") == "engine_closed_trades" else "估算胜率"
    if average >= 80 and max_drawdown <= 0.15 and quality_status not in {"failed", "unknown"}:
        verdict = "research_candidate"
    elif average >= 65 and len(warning_flags) <= 1:
        verdict = "watchlist"
    else:
        verdict = "needs_review"
    action_items: list[str] = []
    if data_version == "not_bound":
        action_items.append("补齐回测输入快照或重新运行回测以绑定本地数据版本。")
    if quality_status in {"needs_attention", "failed", "unknown"}:
        action_items.append("复查本地行情缺口、异常值和覆盖区间，再确认评分结论。")
    if max_drawdown > 0.20:
        action_items.append("最大回撤偏高，优先扩大样本区间并检查止损/仓位规则。")
    if trade_count < 2:
        action_items.append("交易样本偏少，当前胜率和成本判断仅作提示。")
    if not action_items:
        action_items.append("保留当前数据版本并进入更长样本或参数稳健性复核。")
    return {
        "version": "stage74-report-analysis-v2",
        "verdict": verdict,
        "headline": f"综合评分 {average}/100，数据版本 {data_version}，最大回撤 {_pct(max_drawdown)}。",
        "cards": [
            {"key": "return", "label": "收益", "value": _pct(total_return), "detail": f"年化 {_pct(returns.get('annualized_return'))}"},
            {"key": "risk", "label": "风险", "value": _pct(max_drawdown), "detail": f"波动 {_pct(risk.get('volatility'))}"},
            {"key": "trade", "label": "交易", "value": trade_count, "detail": f"{win_rate_label} {_pct(trade.get('win_rate'))}"},
            {"key": "cost", "label": "成本", "value": _money(cost.get("estimated_cost")), "detail": f"费率 {_pct(cost.get('estimated_cost_rate'))}"},
            {"key": "exposure", "label": "暴露", "value": exposure.get("latest_holding_count") or 0, "detail": f"最大权重 {_pct(exposure.get('max_single_weight'))}"},
            {"key": "data", "label": "数据", "value": quality_status, "detail": f"{coverage_status} / {data_version}"},
        ],
        "data_asset": {
            "status": trace.get("status") or "not_bound",
            "symbol": trace.get("symbol") or asset.get("symbol"),
            "data_version": data_version,
            "quality_status": quality_status,
            "coverage_status": coverage_status,
            "row_count": asset.get("row_count"),
            "start_date": asset.get("start_date"),
            "end_date": asset.get("end_date"),
            "source_counts": asset.get("source_counts") or {},
        },
        "warning_flags": warning_flags,
        "watch_flags": watch_flags,
        "action_items": action_items,
    }
def _build_strategy_conclusions(*, average: int, diagnostics: Mapping[str, Any], decision_flags: Sequence[Mapping[str, Any]]) -> list[str]:
    risk = dict(diagnostics.get("risk") or {})
    trade = dict(diagnostics.get("trade_quality") or {})
    cost = dict(diagnostics.get("capacity_cost") or {})
    warning_count = sum(1 for flag in decision_flags if flag.get("level") == "warning")
    win_rate_label = "已平仓胜率" if trade.get("win_rate_source") == "engine_closed_trades" else "估算胜率"
    return [
        f"核心结论：当前策略综合评分 {average}/100，阶段 43 评分已基于本地回测明细、风险曲线、交易活跃度和成本估算生成。",
        f"风险观察：最大回撤 {_pct(risk.get('max_drawdown'))}，区间波动 {_pct(risk.get('volatility'))}，需要结合更长样本继续确认。",
        f"交易质量：交易活跃点 {trade.get('trade_count') or 0}，{win_rate_label} {_pct(trade.get('win_rate'))}，成交额 {_money(cost.get('traded_amount'))}。",
        f"决策提示：当前有 {warning_count} 个观察项需要人工复核；本报告只用于本地研究，不构成投资建议。",
    ]


def _build_strategy_quality_notes(diagnostics: Mapping[str, Any]) -> list[str]:
    data_quality = dict(diagnostics.get("data_quality") or {})
    points = dict(data_quality.get("points") or {})
    return [
        "已确认：阶段 43 策略评价由后端 ReportingService 生成，前端仅渲染。",
        f"已确认：本次评价使用账户点 {points.get('account_points', 0)}、交易点 {points.get('trade_points', 0)}、持仓点 {points.get('exposure_points', 0)}、年度收益点 {points.get('yearly_points', 0)}。",
        "待确认：行业归因、样本外检验、真实容量和逐笔费用仍需更完整的数据源后继续增强。",
    ]

def _dimension(
    *,
    key: str,
    short_label: str,
    title: str,
    score: int,
    metrics: list[tuple[str, str]],
    chart: StrategyEvaluationChartPayload,
) -> StrategyEvaluationDimensionPayload:
    bounded_score = max(0, min(100, score))
    return StrategyEvaluationDimensionPayload(
        key=key,
        short_label=short_label,
        title=title,
        score=bounded_score,
        level=_level(bounded_score),
        metrics=[StrategyEvaluationMetricPayload(label=label, value=str(value)) for label, value in metrics],
        chart=chart,
        evidence_status="calculated_from_run_evidence",
        score_reason="按阶段 74 版本化公式使用真实回测诊断字段计算；缺失证据按零值计入并在报告级证据质量中披露。",
    )


def _level(score: int) -> str:
    if score >= 85:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "normal"
    return "bad"


def _number(metrics: Mapping[str, Any], keys: tuple[str, ...], fallback: float) -> float:
    for key in keys:
        if key in metrics:
            return _float(metrics[key], fallback=fallback)
    return fallback


def _float(value: Any, *, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _pct(value: Any) -> str:
    raw = _float(value)
    percent = raw * 100 if abs(raw) <= 2 else raw
    return f"{percent:.2f}%"




def _index_metric_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for row in rows:
        key = str(row.get("metric_name"))
        indexed[key] = row.get("metric_value") if row.get("metric_value") is not None else row.get("metric_text")
    return indexed


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _comparison_score(
    *,
    annualized_returns: float | None,
    total_returns: float | None,
    max_drawdown: float | None,
    sharpe: float | None,
) -> float:
    return (
        (annualized_returns or 0.0) * 0.45
        + (total_returns or 0.0) * 0.25
        + (sharpe or 0.0) * 0.20
        - abs(max_drawdown or 0.0) * 0.10
    )
def _to_batch_row_model(row: Any) -> BatchExperimentRowModel:
    return BatchExperimentRowModel(
        rank=row.rank,
        run_id=row.run_id,
        strategy_name=row.strategy_name,
        strategy_id=row.strategy_id,
        symbol=row.symbol,
        annualized_returns=row.annualized_returns,
        total_returns=row.total_returns,
        max_drawdown=row.max_drawdown,
        sharpe=row.sharpe,
        status=row.status,
        error_message=row.error_message,
    )


def _account_drawdown_curve(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    peak: float | None = None
    if rows:
        first_value = _optional_float(rows[0].get("total_value"))
        first_nav = _optional_float(rows[0].get("unit_net_value"))
        if first_value is not None and first_nav is not None and first_nav > 0:
            peak = first_value / first_nav
    points: list[dict[str, Any]] = []
    for row in rows:
        value = _optional_float(row.get("total_value"))
        if value is None or value <= 0:
            continue
        peak = value if peak is None else max(peak, value)
        points.append({
            "snapshot_time": row.get("snapshot_time"),
            "value": value / peak - 1.0 if peak else 0.0,
        })
    return points

def _dict_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in rows]


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
