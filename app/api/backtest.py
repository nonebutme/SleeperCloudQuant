from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.api.contracts import RouteDefinition
from app.schemas.backtest import (
    BatchBacktestRunRequestPayload,
    BatchBacktestRunResponsePayload,
    BacktestRunRequestPayload,
    BacktestRunResponsePayload,
    BacktestDataAssetDirectoryQueryPayload,
    BacktestDataAssetDirectoryResponsePayload,
    BacktestInputSnapshotMigrationRequestPayload,
    BacktestInputSnapshotMigrationResponsePayload,
    BacktestInputSnapshotResponsePayload,
    BacktestResultPanelResponsePayload,
    BacktestPortfolioPanelResponsePayload,
    BacktestResultTableQueryPayload,
    BacktestResultTableResponsePayload,
    BacktestExperimentPanelResponsePayload,
    BacktestExperimentCompareRequestPayload,
    BacktestExperimentCompareResponsePayload,
    BacktestExperimentIndexCreateRequestPayload,
    BacktestExperimentIndexFilterPayload,
    BacktestExperimentIndexUpdateRequestPayload,
    BacktestExperimentIndexListResponsePayload,
    BacktestExperimentIndexResponsePayload,
    BacktestModeTaskDirectoryQueryPayload,
    BacktestModeTaskDirectoryResponsePayload,
    IndependentScreeningItemQueryPayload,
    IndependentScreeningItemsResponsePayload,
    IndependentScreeningTaskCreateRequestPayload,
    IndependentScreeningTaskControlRequestPayload,
    IndependentScreeningTaskListQueryPayload,
    IndependentScreeningTaskListResponsePayload,
    IndependentScreeningTaskResponsePayload,
    IndependentScreeningTaskRunRequestPayload,
    SharedPortfolioTaskCreateRequestPayload,
    SharedPortfolioTaskListQueryPayload,
    SharedPortfolioTaskListResponsePayload,
    SharedPortfolioTaskResponsePayload,
    SharedPortfolioTaskRunRequestPayload,
    SingleBacktestTaskCreateRequestPayload,
    SingleBacktestTaskListQueryPayload,
    SingleBacktestTaskListResponsePayload,
    SingleBacktestTaskResponsePayload,
    SingleBacktestTaskRunRequestPayload,
    ParameterMatrixTaskCreateRequestPayload,
    ParameterMatrixTaskListResponsePayload,
    ParameterMatrixTaskResponsePayload,
    ParameterMatrixTaskRunRequestPayload,
    ParameterMatrixTaskRunResponsePayload,
    ParameterScanRequestPayload,
    ParameterScanResponsePayload,
    StrategyDefinitionPayload,
    StrategyLibraryResponsePayload,
    StrategyResearchTaskCreateRequestPayload,
    StrategyResearchTaskListResponsePayload,
    StrategyResearchTaskResponsePayload,
    StrategyResearchTaskRunRequestPayload,
    StrategyResearchTaskRunResponsePayload,
    StrategySaveRequestPayload,
    StrategySaveResponsePayload,
    StrategyValidateRequestPayload,
    StrategyValidateResponsePayload,
    StrategyVersionHistoryResponsePayload,
)
from app.services.backtest_service import BacktestService
from app.services.batch_research_service import BatchResearchService
from app.services.independent_screening_service import IndependentScreeningService
from app.services.persistent_backtest_service import PersistentBacktestService
from app.services.shared_portfolio_service import SharedPortfolioService
from app.services.single_backtest_task_service import SingleBacktestTaskService
from app.services.strategy_service import StrategyService
from domain.backtest import BacktestRunRequest, BatchBacktestRunRequest


_STRATEGY_DRAFTS_PATH = Path("var/runtime/strategy_drafts.json")
_RESEARCH_TASKS_PATH = Path("var/runtime/strategy_research_tasks.json")
_PARAMETER_MATRIX_TASKS_PATH = Path("var/runtime/parameter_matrix_tasks.json")
_EXPERIMENT_INDEX_PATH = Path("var/runtime/backtest_experiment_index.json")



def list_experiment_index(payload: BacktestExperimentIndexFilterPayload | None = None) -> BacktestExperimentIndexListResponsePayload:
    experiments = _filter_experiment_index([item for item in _load_experiment_index() if not item.get("deleted_at")], payload or BacktestExperimentIndexFilterPayload())
    experiments = sorted(experiments, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return BacktestExperimentIndexListResponsePayload(experiments=experiments, summary=_summarize_experiment_index(experiments))


def get_experiment_index(experiment_id: str) -> BacktestExperimentIndexResponsePayload:
    experiment = next((item for item in _load_experiment_index() if item.get("experiment_id") == experiment_id), None)
    return BacktestExperimentIndexResponsePayload(experiment=experiment or {"experiment_id": experiment_id, "status": "not_found"})


def create_experiment_index(payload: BacktestExperimentIndexCreateRequestPayload) -> BacktestExperimentIndexResponsePayload:
    experiment = _build_experiment_index_entry(
        experiment_id=payload.experiment_id,
        run_id_prefix=payload.run_id_prefix,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        task_id=payload.task_id,
        primary_run_id=payload.primary_run_id,
        status="indexed",
    )
    _upsert_experiment_index(experiment)
    return BacktestExperimentIndexResponsePayload(experiment=experiment)

def update_experiment_index(experiment_id: str, payload: BacktestExperimentIndexUpdateRequestPayload) -> BacktestExperimentIndexResponsePayload:
    experiments = _load_experiment_index()
    experiment = next((item for item in experiments if item.get("experiment_id") == experiment_id), None)
    if experiment is None:
        return BacktestExperimentIndexResponsePayload(experiment={"experiment_id": experiment_id, "status": "not_found"})
    updated = dict(experiment)
    if payload.name is not None:
        updated["name"] = payload.name
    if payload.description is not None:
        updated["description"] = payload.description
    if payload.tags is not None:
        updated["tags"] = _normalize_experiment_tags(payload.tags)
    if payload.status is not None:
        updated["status"] = payload.status
    if payload.archived is not None:
        updated["archived"] = bool(payload.archived)
        if payload.archived:
            updated["status"] = "archived"
        elif updated.get("status") == "archived":
            updated["status"] = "indexed"
    if payload.review_note is not None:
        updated["review_note"] = payload.review_note
    updated["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _upsert_experiment_index(updated)
    return BacktestExperimentIndexResponsePayload(experiment=updated)


def delete_experiment_index(experiment_id: str) -> BacktestExperimentIndexResponsePayload:
    experiments = _load_experiment_index()
    experiment = next((item for item in experiments if item.get("experiment_id") == experiment_id), None)
    if experiment is None:
        return BacktestExperimentIndexResponsePayload(experiment={"experiment_id": experiment_id, "status": "not_found"})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    experiment["deleted_at"] = now
    experiment["deleted_reason"] = "用户从 Web 工作台删除"
    experiment["updated_at"] = now
    _upsert_experiment_index(experiment)
    return BacktestExperimentIndexResponsePayload(experiment=experiment)

def compare_experiments(
    service: BacktestService | PersistentBacktestService,
    payload: BacktestExperimentCompareRequestPayload,
) -> BacktestExperimentCompareResponsePayload:
    experiments = _load_experiment_index()
    requested = [str(item) for item in payload.experiment_ids if str(item)]
    selected = [item for item in experiments if str(item.get("experiment_id") or "") in requested]
    rows = []
    for experiment in selected:
        primary_run_id = str(experiment.get("primary_run_id") or "")
        panel = service.get_result_panel(primary_run_id) if isinstance(service, PersistentBacktestService) and primary_run_id else {}
        metrics = dict(panel.get("metrics") or {})
        risk = dict(panel.get("risk_metrics") or {})
        attribution = dict(panel.get("trade_attribution") or {})
        rows.append({
            "experiment_id": experiment.get("experiment_id"),
            "name": experiment.get("name"),
            "status": experiment.get("status"),
            "tags": list(experiment.get("tags") or []),
            "run_id_prefix": experiment.get("run_id_prefix"),
            "primary_run_id": primary_run_id,
            "total_returns": _to_float_or_none(metrics.get("total_returns")),
            "annualized_returns": _to_float_or_none(metrics.get("annualized_returns")),
            "max_drawdown": _to_float_or_none(metrics.get("max_drawdown") or risk.get("max_drawdown")),
            "sharpe": _to_float_or_none(metrics.get("sharpe")),
            "trade_count": attribution.get("trade_count") or panel.get("summary", {}).get("trade_count"),
            "risk_level": risk.get("level") or risk.get("status"),
            "review_link": f"/api/reporting/experiments/{experiment.get('experiment_id')}/review-package",
        })
    ranked = sorted(rows, key=lambda row: (row.get("annualized_returns") is not None, row.get("annualized_returns") or -999), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    result = {
        "status": "ready" if ranked else "empty",
        "requested_count": len(requested),
        "matched_count": len(ranked),
        "experiment_ids": requested,
        "rows": ranked,
        "best_experiment_id": ranked[0].get("experiment_id") if ranked else None,
        "summary": _summarize_experiment_comparison(ranked),
    }
    return BacktestExperimentCompareResponsePayload(result=result)

def list_backtest_runs(service: PersistentBacktestService, limit: int = 50) -> dict[str, Any]:
    return {"runs": service.list_runs(limit=limit)}
def delete_backtest_run(
    service: BacktestService | PersistentBacktestService,
    run_id: str,
) -> dict[str, Any]:
    if not isinstance(service, PersistentBacktestService):
        return {"run": {"run_id": run_id, "status": "unsupported"}}
    return {"run": service.delete_run(run_id)}

def run_once(
    service: BacktestService | PersistentBacktestService,
    payload: BacktestRunRequestPayload,
) -> BacktestRunResponsePayload:
    result = service.run_once(_to_run_request(payload))
    return BacktestRunResponsePayload(result=result)



def get_input_snapshot(
    service: BacktestService | PersistentBacktestService,
    run_id: str,
) -> BacktestInputSnapshotResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestInputSnapshotResponsePayload(snapshot={"run_id": run_id, "status": "unsupported"})
    return BacktestInputSnapshotResponsePayload(snapshot=service.get_input_snapshot(run_id))


def list_data_asset_directory(
    service: BacktestService | PersistentBacktestService,
    payload: BacktestDataAssetDirectoryQueryPayload,
) -> BacktestDataAssetDirectoryResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestDataAssetDirectoryResponsePayload(assets=[], summary={"status": "unsupported", "asset_count": 0})
    result = service.list_data_assets(symbol=payload.symbol, dataset=payload.dataset, data_version=payload.data_version, quality_status=payload.quality_status, coverage_status=payload.coverage_status, limit=payload.limit)
    return BacktestDataAssetDirectoryResponsePayload(assets=list(result.get("assets") or []), summary=dict(result.get("summary") or {}))


def migrate_input_snapshots(
    service: BacktestService | PersistentBacktestService,
    payload: BacktestInputSnapshotMigrationRequestPayload,
) -> BacktestInputSnapshotMigrationResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestInputSnapshotMigrationResponsePayload(result={"status": "unsupported", "summary": {"scanned_count": 0}})
    result = service.migrate_input_snapshots(run_id_prefix=payload.run_id_prefix, dry_run=payload.dry_run, limit=payload.limit)
    return BacktestInputSnapshotMigrationResponsePayload(result=result)
def get_result_panel(
    service: BacktestService | PersistentBacktestService,
    run_id: str,
) -> BacktestResultPanelResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestResultPanelResponsePayload(result={"run_id": run_id, "status": "unsupported"})
    return BacktestResultPanelResponsePayload(result=service.get_result_panel(run_id))


def get_portfolio_panel(
    service: BacktestService | PersistentBacktestService,
    run_id_prefix: str,
) -> BacktestPortfolioPanelResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestPortfolioPanelResponsePayload(result={"run_id_prefix": run_id_prefix, "status": "unsupported"})
    return BacktestPortfolioPanelResponsePayload(result=service.get_portfolio_panel(run_id_prefix))


def get_result_table(
    service: BacktestService | PersistentBacktestService,
    payload: BacktestResultTableQueryPayload,
    run_id: str,
) -> BacktestResultTableResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestResultTableResponsePayload(result={"run_id": run_id, "status": "unsupported"})
    return BacktestResultTableResponsePayload(result=service.get_result_table(run_id, table=payload.table, offset=payload.offset, limit=payload.limit, export_format=payload.export_format))


def get_experiment_panel(
    service: BacktestService | PersistentBacktestService,
    run_id_prefix: str,
) -> BacktestExperimentPanelResponsePayload:
    if not isinstance(service, PersistentBacktestService):
        return BacktestExperimentPanelResponsePayload(result={"run_id_prefix": run_id_prefix, "status": "unsupported"})
    return BacktestExperimentPanelResponsePayload(result=service.get_experiment_panel(run_id_prefix))

def run_batch(
    service: BatchResearchService,
    payload: BatchBacktestRunRequestPayload,
) -> BatchBacktestRunResponsePayload:
    request = BatchBacktestRunRequest(
        experiment_id=payload.experiment_id,
        profile=payload.profile,
        runs=[_to_run_request(item) for item in payload.runs],
    )
    summary = service.run_batch(request)
    return BatchBacktestRunResponsePayload(summary=summary)


def list_strategies(strategy_service: StrategyService | None = None) -> StrategyLibraryResponsePayload:
    service = strategy_service or StrategyService()
    return StrategyLibraryResponsePayload(
        strategies=[_to_strategy_payload(item) for item in service.list_strategies()]
    )


def list_strategy_versions(
    strategy_id: str,
    strategy_service: StrategyService | None = None,
) -> StrategyVersionHistoryResponsePayload:
    service = strategy_service or StrategyService()
    return StrategyVersionHistoryResponsePayload(
        strategy_id=strategy_id,
        versions=[_to_strategy_payload(item) for item in service.list_versions(strategy_id)],
    )


def validate_strategy(
    strategy_service: StrategyService,
    payload: StrategyValidateRequestPayload,
) -> StrategyValidateResponsePayload:
    return StrategyValidateResponsePayload(
        validation=strategy_service.validate_source(payload.source_code)
    )


def save_strategy(
    strategy_service: StrategyService,
    payload: StrategySaveRequestPayload,
) -> StrategySaveResponsePayload:
    strategy = strategy_service.save_version(
        strategy_id=payload.strategy_id,
        name=payload.name,
        source_code=payload.source_code,
        parameters=payload.parameters,
        parameter_schema=payload.parameter_schema,
        category=payload.category,
        description=payload.description,
    )
    return StrategySaveResponsePayload(strategy=_to_strategy_payload(strategy))


def archive_strategy(strategy_service: StrategyService, strategy_id: str) -> dict[str, Any]:
    return {"strategy": strategy_service.archive_strategy(strategy_id)}


def _to_strategy_payload(item: dict[str, Any]) -> StrategyDefinitionPayload:
    return StrategyDefinitionPayload(
        strategy_id=str(item["strategy_id"]),
        name=str(item["name"]),
        category=str(item.get("category") or "自定义策略"),
        description=str(item.get("description") or ""),
        parameters=dict(item.get("parameters") or {}),
        parameter_schema=dict(item.get("parameter_schema") or {}),
        source_code=str(item.get("source_code") or ""),
        source_reference=str(item.get("source_reference") or "local-versioned-strategy"),
        editable=bool(item.get("editable", True)),
        latest_version=str(item.get("latest_version") or "v1"),
        version_count=int(item.get("version_count") or 1),
        saved_at=item.get("saved_at"),
        source_sha256=item.get("source_sha256"),
        validation_status=str(item.get("validation_status") or "unknown"),
        execution_contract=str(item.get("execution_contract") or "target-weights-v1"),
    )





def list_research_tasks() -> StrategyResearchTaskListResponsePayload:
    return StrategyResearchTaskListResponsePayload(tasks=[item for item in _load_research_tasks() if not item.get("deleted_at")])


def get_research_task(task_id: str) -> StrategyResearchTaskResponsePayload:
    task = next((item for item in _load_research_tasks() if item.get("task_id") == task_id), None)
    return StrategyResearchTaskResponsePayload(task=task or {"task_id": task_id, "status": "not_found"})


def delete_research_task(task_id: str) -> StrategyResearchTaskResponsePayload:
    tasks = _load_research_tasks()
    task = next((item for item in tasks if item.get("task_id") == task_id), None)
    if task is None:
        return StrategyResearchTaskResponsePayload(task={"task_id": task_id, "status": "not_found"})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    task["deleted_at"] = now
    task["deleted_reason"] = "用户从 Web 工作台删除"
    task["updated_at"] = now
    _write_research_tasks([item if item.get("task_id") != task_id else task for item in tasks])
    return StrategyResearchTaskResponsePayload(task=task)

def create_research_task(payload: StrategyResearchTaskCreateRequestPayload) -> StrategyResearchTaskResponsePayload:
    tasks = _load_research_tasks()
    task_id = payload.task_id or f"research-{len(tasks) + 1:04d}"
    strategy = _find_strategy_definition(payload.strategy_id)
    parameters = dict(strategy.parameters if strategy else {})
    parameters.update(payload.parameters or {})
    indicator_plan = payload.indicator_plan or _default_indicator_plan(payload.strategy_id, parameters)
    signal_rules = payload.signal_rules or _default_signal_rules(payload.strategy_id, parameters)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    task = {
        "task_id": task_id,
        "status": "draft_ready",
        "name": payload.name,
        "strategy_id": payload.strategy_id,
        "strategy_version": payload.strategy_version or (strategy.latest_version if strategy else "v1"),
        "symbols": _normalize_research_symbols(payload.symbols),
        "date_window": {"start_date": payload.start_date, "end_date": payload.end_date},
        "benchmark": payload.benchmark,
        "frequency": payload.frequency,
        "parameters": parameters,
        "parameter_schema": dict(strategy.parameter_schema if strategy else _infer_parameter_schema(parameters)),
        "indicator_plan": indicator_plan,
        "signal_rules": signal_rules,
        "signal_preview": _build_signal_preview(symbols=_normalize_research_symbols(payload.symbols), start_date=payload.start_date, end_date=payload.end_date, signal_rules=signal_rules),
        "research_outputs": {"expected_artifacts": ["signal_preview", "backtest_candidate", "quality_notes"], "ready_for_backtest": True},
        "risk_notes": ["研究任务仅用于本地策略实验，不构成投资建议。", "进入正式回测前应确认本地行情质量状态。"],
        "notes": payload.notes,
        "created_at": created_at,
        "updated_at": created_at,
    }
    tasks = [item for item in tasks if item.get("task_id") != task_id]
    tasks.append(task)
    _write_research_tasks(tasks)
    return StrategyResearchTaskResponsePayload(task=task)

def run_research_task(
    service: BacktestService | PersistentBacktestService,
    payload: StrategyResearchTaskRunRequestPayload,
    task_id: str,
) -> StrategyResearchTaskRunResponsePayload:
    tasks = _load_research_tasks()
    task = next((item for item in tasks if item.get("task_id") == task_id), None)
    if task is None:
        return StrategyResearchTaskRunResponsePayload(result={"task_id": task_id, "status": "not_found", "results": []})
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prefix = payload.run_id_prefix or f"{task_id}-run"
    symbols = _normalize_research_symbols(task.get("symbols") or [])
    window = task.get("date_window") if isinstance(task.get("date_window"), dict) else {}
    results = []
    failures = []
    for index, symbol in enumerate(symbols, start=1):
        run_id = f"{prefix}-{index:03d}"
        request = BacktestRunRequest(
            run_id=run_id,
            strategy_name=str(task.get("name") or task.get("strategy_id") or "research_strategy"),
            symbol=symbol,
            benchmark=str(task.get("benchmark") or "000300.XSHG"),
            start_date=str(window.get("start_date") or "2020-01-01"),
            end_date=str(window.get("end_date") or "2020-12-31"),
            initial_cash=payload.initial_cash,
            frequency=str(task.get("frequency") or "1d"),
            parameters=dict(task.get("parameters") or {}),
            extra_config={**dict(payload.extra_config or {}), "research_task_id": task_id, "indicator_plan": task.get("indicator_plan", []), "signal_rules": task.get("signal_rules", [])},
            strategy_id=str(task.get("strategy_id") or ""),
            strategy_version=str(task.get("strategy_version") or "v1"),
        )
        try:
            result = service.run_once(request)
            results.append({
                "run_id": result.run_id,
                "symbol": symbol,
                "status": result.status.value,
                "metrics": dict(result.metrics),
                "start_date": result.start_date,
                "end_date": result.end_date,
                "benchmark": result.benchmark,
                "trade_artifacts": {"runtime_store": "backtest_trades", "reporting_run_id": result.run_id},
            })
        except Exception as exc:  # pragma: no cover - user data/runtime failure remains observable.
            failures.append({"run_id": run_id, "symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    status = "completed" if results and not failures else ("partial_failed" if results else "failed")
    execution = {
        "task_id": task_id,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "run_id_prefix": prefix,
        "run_count": len(results),
        "failure_count": len(failures),
        "run_ids": [item["run_id"] for item in results],
        "results": results,
        "failures": failures,
        "research_binding": {"strategy_id": task.get("strategy_id"), "strategy_version": task.get("strategy_version"), "signal_preview_count": len(task.get("signal_preview") or [])},
    }
    task["status"] = "backtest_completed" if status == "completed" else status
    task["last_execution"] = execution
    task["updated_at"] = finished_at
    if results:
        _upsert_experiment_index(_build_experiment_index_entry(run_id_prefix=prefix, name=str(task.get("name") or task_id), description=str(task.get("notes") or ""), tags=["research_task", str(task.get("strategy_id") or "strategy")], task_id=task_id, primary_run_id=results[0].get("run_id"), status=status))
    _write_research_tasks([item if item.get("task_id") != task_id else task for item in tasks])
    return StrategyResearchTaskRunResponsePayload(result=execution)

def list_parameter_matrix_tasks() -> ParameterMatrixTaskListResponsePayload:
    tasks = sorted((item for item in _load_parameter_matrix_tasks() if not item.get("deleted_at")), key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return ParameterMatrixTaskListResponsePayload(tasks=tasks)


def get_parameter_matrix_task(task_id: str) -> ParameterMatrixTaskResponsePayload:
    task = next((item for item in _load_parameter_matrix_tasks() if item.get("task_id") == task_id), None)
    return ParameterMatrixTaskResponsePayload(task=task or {"task_id": task_id, "status": "not_found"})


def delete_parameter_matrix_task(task_id: str) -> ParameterMatrixTaskResponsePayload:
    tasks = _load_parameter_matrix_tasks()
    task = next((item for item in tasks if item.get("task_id") == task_id), None)
    if task is None:
        return ParameterMatrixTaskResponsePayload(task={"task_id": task_id, "status": "not_found"})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    task["deleted_at"] = now
    task["deleted_reason"] = "用户从 Web 工作台删除"
    task["updated_at"] = now
    _write_parameter_matrix_tasks([item if item.get("task_id") != task_id else task for item in tasks])
    return ParameterMatrixTaskResponsePayload(task=task)

def create_parameter_matrix_task(payload: ParameterMatrixTaskCreateRequestPayload) -> ParameterMatrixTaskResponsePayload:
    tasks = _load_parameter_matrix_tasks()
    task_id = payload.task_id or f"matrix-{len(tasks) + 1:04d}"
    combinations = _parameter_combinations(payload.parameter_grid, max_runs=payload.max_runs)
    if not combinations:
        combinations = [dict(payload.base_parameters)]
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    task = {
        "task_id": task_id,
        "status": "draft_ready",
        "run_id_prefix": payload.run_id_prefix or task_id,
        "strategy_name": payload.strategy_name,
        "strategy_id": payload.strategy_id,
        "strategy_version": payload.strategy_version,
        "symbol": payload.symbol,
        "benchmark": payload.benchmark,
        "date_window": {"start_date": payload.start_date, "end_date": payload.end_date},
        "frequency": payload.frequency,
        "initial_cash": payload.initial_cash,
        "base_parameters": dict(payload.base_parameters or {}),
        "parameter_grid": dict(payload.parameter_grid or {}),
        "extra_config": dict(payload.extra_config or {}),
        "max_runs": payload.max_runs,
        "planned_combinations": [{**dict(payload.base_parameters or {}), **combination} for combination in combinations],
        "created_at": created_at,
        "updated_at": created_at,
    }
    tasks = [item for item in tasks if item.get("task_id") != task_id]
    tasks.append(task)
    _write_parameter_matrix_tasks(tasks)
    return ParameterMatrixTaskResponsePayload(task=task)


def run_parameter_matrix_task(
    service: BacktestService | PersistentBacktestService,
    payload: ParameterMatrixTaskRunRequestPayload,
    task_id: str,
) -> ParameterMatrixTaskRunResponsePayload:
    tasks = _load_parameter_matrix_tasks()
    task = next((item for item in tasks if item.get("task_id") == task_id), None)
    if task is None:
        return ParameterMatrixTaskRunResponsePayload(result={"task_id": task_id, "status": "not_found"})
    combinations = list(task.get("planned_combinations") or [])
    limit = payload.max_runs or task.get("max_runs") or len(combinations)
    combinations = combinations[: max(1, int(limit))]
    previous_rows = list((task.get("last_execution") or {}).get("rows") or [])
    previous_failed = {str(row.get("run_id")) for row in previous_rows if row.get("status") != "completed"}
    rows = []
    failures = []
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prefix = str(task.get("run_id_prefix") or task_id)
    window = dict(task.get("date_window") or {})
    for index, parameters in enumerate(combinations, start=1):
        run_id = f"{prefix}-{index:03d}"
        if payload.rerun_failed_only and previous_failed and run_id not in previous_failed:
            prior = next((row for row in previous_rows if row.get("run_id") == run_id), None)
            if prior:
                rows.append(dict(prior))
            continue
        request = BacktestRunRequest(
            run_id=run_id,
            strategy_name=str(task.get("strategy_name") or "parameter_matrix_strategy"),
            symbol=str(task.get("symbol") or "000001.XSHE"),
            benchmark=str(task.get("benchmark") or "000300.XSHG"),
            start_date=str(window.get("start_date") or "2020-01-01"),
            end_date=str(window.get("end_date") or "2020-12-31"),
            initial_cash=float(task.get("initial_cash") or 1_000_000),
            frequency=str(task.get("frequency") or "1d"),
            parameters=dict(parameters),
            extra_config={**dict(task.get("extra_config") or {}), "parameter_matrix_task_id": task_id, "parameter_matrix_index": index},
            strategy_id=task.get("strategy_id"),
            strategy_version=task.get("strategy_version"),
        )
        try:
            result = service.run_once(request)
            metrics = dict(result.metrics)
            rows.append({
                "rank": 0,
                "run_id": result.run_id,
                "status": result.status.value,
                "parameters": dict(parameters),
                "total_returns": _to_float_or_none(metrics.get("total_returns")),
                "annualized_returns": _to_float_or_none(metrics.get("annualized_returns")),
                "max_drawdown": _to_float_or_none(metrics.get("max_drawdown")),
                "sharpe": _to_float_or_none(metrics.get("sharpe")),
                "score": _parameter_matrix_score(metrics),
            })
        except Exception as exc:  # pragma: no cover - runtime/data issues remain observable.
            failure = {"run_id": run_id, "status": "failed", "parameters": dict(parameters), "error": f"{type(exc).__name__}: {exc}", "score": -999.0}
            rows.append(failure)
            failures.append(failure)
    ranked = sorted(rows, key=lambda row: float(row.get("score") if row.get("score") is not None else -999.0), reverse=True)
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    completed_count = sum(1 for row in ranked if row.get("status") == "completed")
    status = "completed" if completed_count == len(ranked) and ranked else ("partial_failed" if completed_count else "failed")
    execution = {
        "task_id": task_id,
        "status": status,
        "run_id_prefix": prefix,
        "started_at": started_at,
        "finished_at": finished_at,
        "planned_count": len(combinations),
        "run_count": len(ranked),
        "completed_count": completed_count,
        "failure_count": len(ranked) - completed_count,
        "best_run_id": ranked[0].get("run_id") if ranked else None,
        "best_parameters": ranked[0].get("parameters") if ranked else {},
        "rows": ranked,
        "failures": [row for row in ranked if row.get("status") != "completed"],
    }
    task["status"] = status
    task["last_execution"] = execution
    task["updated_at"] = finished_at
    _write_parameter_matrix_tasks([item if item.get("task_id") != task_id else task for item in tasks])
    if ranked:
        _upsert_experiment_index(_build_experiment_index_entry(
            run_id_prefix=prefix,
            name=str(task.get("strategy_name") or task_id) + " 参数矩阵",
            description=f"参数矩阵任务 {task_id}，共 {len(ranked)} 组参数。",
            tags=["parameter_matrix", str(task.get("strategy_id") or "strategy")],
            task_id=task_id,
            primary_run_id=str(ranked[0].get("run_id") or ""),
            status=status,
        ))
    return ParameterMatrixTaskRunResponsePayload(result=execution)

def run_parameter_scan(
    service: BacktestService | PersistentBacktestService,
    payload: ParameterScanRequestPayload,
) -> ParameterScanResponsePayload:
    combinations = _parameter_combinations(payload.parameter_grid, max_runs=payload.max_runs)
    if not combinations:
        combinations = [dict(payload.base_parameters)]
    results = []
    normalized_combinations = []
    for index, parameters in enumerate(combinations, start=1):
        merged_parameters = {**payload.base_parameters, **parameters}
        normalized_combinations.append(merged_parameters)
        request = BacktestRunRequest(
            run_id=f"{payload.run_id_prefix}-{index:03d}",
            strategy_name=payload.strategy_name,
            symbol=payload.symbol,
            benchmark=payload.benchmark,
            start_date=payload.start_date,
            end_date=payload.end_date,
            initial_cash=payload.initial_cash,
            frequency=payload.frequency,
            parameters=merged_parameters,
            extra_config={**payload.extra_config, "parameter_scan": True, "parameter_scan_index": index},
            strategy_id=payload.strategy_id,
            strategy_version=payload.strategy_version,
        )
        results.append(service.run_once(request))
    return ParameterScanResponsePayload(
        run_id_prefix=payload.run_id_prefix,
        results=results,
        combinations=normalized_combinations,
    )
def create_single_backtest_task(
    service: SingleBacktestTaskService,
    payload: SingleBacktestTaskCreateRequestPayload,
) -> SingleBacktestTaskResponsePayload:
    return SingleBacktestTaskResponsePayload(task=service.create_task(
        task_id=payload.task_id, run_id=payload.run_id, name=payload.name,
        strategy_name=payload.strategy_name, strategy_id=payload.strategy_id,
        strategy_version=payload.strategy_version, symbol=payload.symbol,
        benchmark=payload.benchmark, start_date=payload.start_date, end_date=payload.end_date,
        initial_cash=payload.initial_cash, frequency=payload.frequency,
        adjustment=payload.adjustment, parameters=payload.parameters,
        extra_config=payload.extra_config,
    ))


def list_single_backtest_tasks(
    service: SingleBacktestTaskService,
    payload: SingleBacktestTaskListQueryPayload,
) -> SingleBacktestTaskListResponsePayload:
    return SingleBacktestTaskListResponsePayload(tasks=service.list_tasks(limit=int(payload.limit)))


def get_single_backtest_task(service: SingleBacktestTaskService, task_id: str) -> SingleBacktestTaskResponsePayload:
    return SingleBacktestTaskResponsePayload(task=service.get_task(task_id))


def run_single_backtest_task(
    service: SingleBacktestTaskService,
    payload: SingleBacktestTaskRunRequestPayload,
    task_id: str,
) -> SingleBacktestTaskResponsePayload:
    wait = payload.wait is True or str(payload.wait).lower() in {"1", "true", "yes"}
    return SingleBacktestTaskResponsePayload(task=service.start_task(task_id, wait=wait))


def delete_single_backtest_task(service: SingleBacktestTaskService, task_id: str) -> SingleBacktestTaskResponsePayload:
    return SingleBacktestTaskResponsePayload(task=service.delete_task(task_id))

def create_independent_screening_task(
    service: IndependentScreeningService,
    payload: IndependentScreeningTaskCreateRequestPayload,
) -> IndependentScreeningTaskResponsePayload:
    task = service.create_task(
        task_id=payload.task_id,
        name=payload.name,
        strategy_id=payload.strategy_id,
        strategy_version=payload.strategy_version,
        symbols=payload.symbols,
        market=payload.market,
        start_date=payload.start_date,
        end_date=payload.end_date,
        adjustment=payload.adjustment,
        benchmark=payload.benchmark,
        initial_cash=payload.initial_cash,
        parameters=payload.parameters,
        max_workers=payload.max_workers,
        retry_count=payload.retry_count,
        symbol_limit=payload.symbol_limit,
        scheduler_batch_size=payload.scheduler_batch_size,
    )
    return IndependentScreeningTaskResponsePayload(task=task)


def list_independent_screening_tasks(
    service: IndependentScreeningService,
    payload: IndependentScreeningTaskListQueryPayload,
) -> IndependentScreeningTaskListResponsePayload:
    return IndependentScreeningTaskListResponsePayload(tasks=service.list_tasks(limit=int(payload.limit)))


def delete_independent_screening_task(
    service: IndependentScreeningService,
    task_id: str,
) -> IndependentScreeningTaskResponsePayload:
    return IndependentScreeningTaskResponsePayload(task=service.delete_task(task_id))


def get_independent_screening_task(
    service: IndependentScreeningService,
    task_id: str,
) -> IndependentScreeningTaskResponsePayload:
    return IndependentScreeningTaskResponsePayload(task=service.get_task(task_id))


def run_independent_screening_task(
    service: IndependentScreeningService,
    payload: IndependentScreeningTaskRunRequestPayload,
    task_id: str,
) -> IndependentScreeningTaskResponsePayload:
    wait = payload.wait is True or str(payload.wait).lower() in {"1", "true", "yes"}
    return IndependentScreeningTaskResponsePayload(task=service.start_task(task_id, wait=wait))




def control_independent_screening_task(
    service: IndependentScreeningService,
    payload: IndependentScreeningTaskControlRequestPayload,
    task_id: str,
) -> IndependentScreeningTaskResponsePayload:
    return IndependentScreeningTaskResponsePayload(
        task=service.control_task(task_id, payload.action)
    )

def list_independent_screening_items(
    service: IndependentScreeningService,
    payload: IndependentScreeningItemQueryPayload,
    task_id: str,
) -> IndependentScreeningItemsResponsePayload:
    entered_only = payload.entered_only is True or str(payload.entered_only).lower() in {"1", "true", "yes"}
    return IndependentScreeningItemsResponsePayload(
        result=service.list_items(
            task_id,
            entered_only=entered_only,
            status=str(payload.status or ""),
            limit=int(payload.limit),
            offset=int(payload.offset),
        )
    )

def create_shared_portfolio_task(
    service: SharedPortfolioService,
    payload: SharedPortfolioTaskCreateRequestPayload,
) -> SharedPortfolioTaskResponsePayload:
    task = service.create_task(
        task_id=payload.task_id, name=payload.name,
        strategy_id=payload.strategy_id, strategy_version=payload.strategy_version,
        symbols=payload.symbols, market=payload.market,
        start_date=payload.start_date, end_date=payload.end_date,
        adjustment=payload.adjustment, benchmark=payload.benchmark,
        initial_cash=payload.initial_cash, parameters=payload.parameters,
        max_workers=payload.max_workers, symbol_limit=payload.symbol_limit,
        max_positions=payload.max_positions, portfolio_exposure=payload.portfolio_exposure,
        commission_rate=payload.commission_rate, min_commission=payload.min_commission,
        tax_rate=payload.tax_rate, slippage_rate=payload.slippage_rate,
    )
    return SharedPortfolioTaskResponsePayload(task=task)


def list_shared_portfolio_tasks(service: SharedPortfolioService, payload: SharedPortfolioTaskListQueryPayload) -> SharedPortfolioTaskListResponsePayload:
    return SharedPortfolioTaskListResponsePayload(tasks=service.list_tasks(limit=int(payload.limit)))


def delete_shared_portfolio_task(
    service: SharedPortfolioService,
    task_id: str,
) -> SharedPortfolioTaskResponsePayload:
    return SharedPortfolioTaskResponsePayload(task=service.delete_task(task_id))

def get_shared_portfolio_task(service: SharedPortfolioService, task_id: str) -> SharedPortfolioTaskResponsePayload:
    return SharedPortfolioTaskResponsePayload(task=service.get_task(task_id))


def run_shared_portfolio_task(service: SharedPortfolioService, payload: SharedPortfolioTaskRunRequestPayload, task_id: str) -> SharedPortfolioTaskResponsePayload:
    wait = payload.wait is True or str(payload.wait).lower() in {"1", "true", "yes"}
    return SharedPortfolioTaskResponsePayload(task=service.start_task(task_id, wait=wait))


def list_backtest_mode_tasks(
    independent_service: IndependentScreeningService,
    portfolio_service: SharedPortfolioService,
    payload: BacktestModeTaskDirectoryQueryPayload,
    single_service: SingleBacktestTaskService | None = None,
) -> BacktestModeTaskDirectoryResponsePayload:
    tasks = [
        *(_mode_task_entry("single", task) for task in (single_service.list_tasks(limit=200) if single_service else [])),
        *(_mode_task_entry("independent-screening", task) for task in independent_service.list_tasks(limit=200)),
        *(_mode_task_entry("shared-portfolio", task) for task in portfolio_service.list_tasks(limit=200)),
    ]
    mode = str(payload.mode or "").strip().lower()
    status = str(payload.status or "").strip().lower()
    strategy_id = str(payload.strategy_id or "").strip().lower()
    search = str(payload.search or "").strip().lower()
    if mode:
        tasks = [task for task in tasks if task["mode"] == mode]
    if status:
        tasks = [task for task in tasks if str(task["status"]).lower() == status]
    if strategy_id:
        tasks = [task for task in tasks if str(task["strategy_binding"]["strategy_id"]).lower() == strategy_id]
    if search:
        tasks = [task for task in tasks if search in f"{task['task_id']} {task['name']} {task['strategy_binding']['strategy_id']}".lower()]
    tasks.sort(key=lambda task: str(task.get("updated_at") or task.get("created_at") or ""), reverse=True)
    tasks = tasks[: max(1, min(int(payload.limit), 200))]
    status_counts: dict[str, int] = {}
    mode_counts: dict[str, int] = {}
    for task in tasks:
        status_counts[task["status"]] = status_counts.get(task["status"], 0) + 1
        mode_counts[task["mode"]] = mode_counts.get(task["mode"], 0) + 1
    return BacktestModeTaskDirectoryResponsePayload(
        tasks=tasks,
        summary={"task_count": len(tasks), "mode_counts": mode_counts, "status_counts": status_counts},
    )


def _mode_task_entry(mode: str, task: dict[str, Any]) -> dict[str, Any]:
    config = dict(task.get("config") or {})
    progress = dict(task.get("progress") or {})
    universe_count = int(progress.get("total") or task.get("universe_count") or (1 if mode == "single" else 0))
    if mode == "single":
        normalized_progress = {
            "phase": str(progress.get("phase") or task.get("status") or "ready"),
            "processed": int(progress.get("processed") or 0), "total": 1,
            "percent": float(progress.get("percent") or 0.0), "entered": None,
            "failed": 1 if task.get("status") == "failed" else 0, "canceled": 0,
            "elapsed_seconds": float(progress.get("elapsed_seconds") or 0.0),
            "throughput_per_minute": 0.0, "estimated_remaining_seconds": None,
        }
        mode_label, task_path = "单品种测试", "single-backtest-tasks"
    elif mode == "independent-screening":
        normalized_progress = {
            "processed": int(progress.get("processed") or 0), "total": universe_count,
            "percent": float(progress.get("percent") or 0.0),
            "entered": int(progress.get("entered") or 0), "failed": int(progress.get("failed") or 0),
            "canceled": int(progress.get("canceled") or 0),
            "elapsed_seconds": float(progress.get("elapsed_seconds") or 0.0),
            "throughput_per_minute": float(progress.get("throughput_per_minute") or 0.0),
            "estimated_remaining_seconds": progress.get("estimated_remaining_seconds"),
        }
        mode_label, task_path = "独立账户批量回测", "independent-screening-tasks"
    else:
        complete = str(task.get("status") or "") in {"completed", "partial_completed"}
        normalized_progress = {
            "phase": str(progress.get("phase") or ("completed" if complete else "ready")),
            "processed": int(progress.get("processed") or (universe_count if complete else 0)),
            "total": universe_count, "percent": float(progress.get("percent") or (100.0 if complete else 0.0)),
            "prepared": int(progress.get("prepared") or 0), "entered": None,
            "failed": int(progress.get("excluded") or (task.get("summary") or {}).get("excluded_symbol_count") or 0),
            "canceled": 0, "elapsed_seconds": float(progress.get("elapsed_seconds") or 0.0),
            "throughput_per_minute": float(progress.get("throughput_per_minute") or 0.0),
            "estimated_remaining_seconds": progress.get("estimated_remaining_seconds"),
        }
        mode_label, task_path = "投资组合回测", "shared-portfolio-tasks"
    task_id = str(task.get("task_id") or "")
    status = str(task.get("status") or "unknown")
    run_id = task.get("run_id")
    result_ready = status in {"completed", "partial_completed", "partial_failed"} and bool(run_id or mode == "independent-screening")
    capabilities = {
        "can_start": status in {"ready", "paused", "interrupted", "failed", "partial_failed"},
        "can_pause": mode == "independent-screening" and status == "running",
        "can_cancel": mode == "independent-screening" and status in {"ready", "running", "pause_requested", "paused", "interrupted"},
        "can_view_result": result_ready,
        "can_view_report": result_ready,
        "can_clone": status != "running",
        "can_delete": status not in {"running", "pending", "pause_requested", "cancel_requested"},
    }
    report_link = (
        f"/api/reporting/strategy-evaluation/{run_id}" if mode == "single" and run_id
        else f"/api/reporting/backtest-modes/{mode}/{task_id}"
    )
    return {
        "task_id": task_id, "mode": mode, "mode_label": mode_label,
        "name": str(config.get("name") or task_id), "status": status,
        "strategy_binding": {
            "strategy_id": str(config.get("strategy_id") or ""),
            "strategy_version": str(config.get("strategy_version") or ""),
            "source_sha256": str(config.get("source_sha256") or ""),
        },
        "date_window": dict(config.get("date_window") or {}),
        "adjustment": str(config.get("adjustment") or "qfq"),
        "universe_count": universe_count, "symbol": config.get("symbol"),
        "progress": normalized_progress, "execution": dict(task.get("execution") or {}),
        "run_id": run_id, "error_message": task.get("error_message"),
        "created_at": task.get("created_at"), "updated_at": task.get("updated_at"),
        "started_at": task.get("started_at"), "finished_at": task.get("finished_at"),
        "capabilities": capabilities,
        "links": {
            "detail": f"/api/backtest/{task_path}/{task_id}",
            "run": f"/api/backtest/{task_path}/{task_id}/run",
            "delete": f"/api/backtest/{task_path}/{task_id}",
            "result": f"/api/backtest/results/{run_id}/panel" if run_id else "",
            "report": report_link,
        },
    }


def build_backtest_routes(
    service: BacktestService | PersistentBacktestService,
    batch_service: BatchResearchService,
    strategy_service: StrategyService,
    independent_screening_service: IndependentScreeningService,
    shared_portfolio_service: SharedPortfolioService,
    single_backtest_task_service: SingleBacktestTaskService | None = None,
) -> list[RouteDefinition]:
    return [
        RouteDefinition(
            method="GET",
            path="/api/backtest/strategies",
            name="backtest_strategy_library",
            handler=lambda: list_strategies(strategy_service),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/strategies/{strategy_id}/versions",
            name="backtest_strategy_versions",
            handler=lambda strategy_id: list_strategy_versions(strategy_id, strategy_service),
            request_model=None,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/strategies/{strategy_id}",
            name="backtest_strategy_archive",
            handler=lambda strategy_id: archive_strategy(strategy_service, strategy_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/strategies/save-draft",
            name="backtest_strategy_save_draft",
            handler=lambda payload: save_strategy(strategy_service, payload),
            request_model=StrategySaveRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/strategies/validate",
            name="backtest_strategy_validate",
            handler=lambda payload: validate_strategy(strategy_service, payload),
            request_model=StrategyValidateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/single-backtest-tasks",
            name="backtest_single_tasks",
            handler=lambda payload: list_single_backtest_tasks(single_backtest_task_service, payload),
            request_model=SingleBacktestTaskListQueryPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/single-backtest-tasks",
            name="backtest_single_task_create",
            handler=lambda payload: create_single_backtest_task(single_backtest_task_service, payload),
            request_model=SingleBacktestTaskCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/single-backtest-tasks/{task_id}",
            name="backtest_single_task_detail",
            handler=lambda task_id: get_single_backtest_task(single_backtest_task_service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/single-backtest-tasks/{task_id}/run",
            name="backtest_single_task_run",
            handler=lambda payload, task_id: run_single_backtest_task(single_backtest_task_service, payload, task_id),
            request_model=SingleBacktestTaskRunRequestPayload,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/single-backtest-tasks/{task_id}",
            name="backtest_single_task_delete",
            handler=lambda task_id: delete_single_backtest_task(single_backtest_task_service, task_id),
            request_model=None,
        ),        RouteDefinition(
            method="GET",
            path="/api/backtest/mode-tasks",
            name="backtest_mode_task_directory",
            handler=lambda payload: list_backtest_mode_tasks(independent_screening_service, shared_portfolio_service, payload, single_backtest_task_service),
            request_model=BacktestModeTaskDirectoryQueryPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/independent-screening-tasks",
            name="backtest_independent_screening_tasks",
            handler=lambda payload: list_independent_screening_tasks(independent_screening_service, payload),
            request_model=IndependentScreeningTaskListQueryPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/independent-screening-tasks",
            name="backtest_independent_screening_task_create",
            handler=lambda payload: create_independent_screening_task(independent_screening_service, payload),
            request_model=IndependentScreeningTaskCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/independent-screening-tasks/{task_id}",
            name="backtest_independent_screening_task_detail",
            handler=lambda task_id: get_independent_screening_task(independent_screening_service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/independent-screening-tasks/{task_id}",
            name="backtest_independent_screening_task_delete",
            handler=lambda task_id: delete_independent_screening_task(independent_screening_service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/independent-screening-tasks/{task_id}/run",
            name="backtest_independent_screening_task_run",
            handler=lambda payload, task_id: run_independent_screening_task(independent_screening_service, payload, task_id),
            request_model=IndependentScreeningTaskRunRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/independent-screening-tasks/{task_id}/control",
            name="backtest_independent_screening_task_control",
            handler=lambda payload, task_id: control_independent_screening_task(independent_screening_service, payload, task_id),
            request_model=IndependentScreeningTaskControlRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/independent-screening-tasks/{task_id}/items",
            name="backtest_independent_screening_task_items",
            handler=lambda payload, task_id: list_independent_screening_items(independent_screening_service, payload, task_id),
            request_model=IndependentScreeningItemQueryPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/shared-portfolio-tasks",
            name="backtest_shared_portfolio_tasks",
            handler=lambda payload: list_shared_portfolio_tasks(shared_portfolio_service, payload),
            request_model=SharedPortfolioTaskListQueryPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/shared-portfolio-tasks",
            name="backtest_shared_portfolio_task_create",
            handler=lambda payload: create_shared_portfolio_task(shared_portfolio_service, payload),
            request_model=SharedPortfolioTaskCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/shared-portfolio-tasks/{task_id}",
            name="backtest_shared_portfolio_task_detail",
            handler=lambda task_id: get_shared_portfolio_task(shared_portfolio_service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/shared-portfolio-tasks/{task_id}",
            name="backtest_shared_portfolio_task_delete",
            handler=lambda task_id: delete_shared_portfolio_task(shared_portfolio_service, task_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/shared-portfolio-tasks/{task_id}/run",
            name="backtest_shared_portfolio_task_run",
            handler=lambda payload, task_id: run_shared_portfolio_task(shared_portfolio_service, payload, task_id),
            request_model=SharedPortfolioTaskRunRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/experiments",
            name="backtest_experiment_index_list",
            handler=list_experiment_index,
            request_model=BacktestExperimentIndexFilterPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/experiments",
            name="backtest_experiment_index_create",
            handler=create_experiment_index,
            request_model=BacktestExperimentIndexCreateRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/experiments/compare",
            name="backtest_experiment_compare",
            handler=lambda payload: compare_experiments(service, payload),
            request_model=BacktestExperimentCompareRequestPayload,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/experiments/index/{experiment_id}",
            name="backtest_experiment_index_delete",
            handler=delete_experiment_index,
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/experiments/index/{experiment_id}/update",
            name="backtest_experiment_index_update",
            handler=lambda payload, experiment_id: update_experiment_index(experiment_id, payload),
            request_model=BacktestExperimentIndexUpdateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/experiments/index/{experiment_id}",
            name="backtest_experiment_index_detail",
            handler=get_experiment_index,
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/parameter-matrix-tasks",
            name="backtest_parameter_matrix_tasks",
            handler=list_parameter_matrix_tasks,
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/parameter-matrix-tasks",
            name="backtest_parameter_matrix_task_create",
            handler=create_parameter_matrix_task,
            request_model=ParameterMatrixTaskCreateRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/parameter-matrix-tasks/{task_id}",
            name="backtest_parameter_matrix_task_detail",
            handler=get_parameter_matrix_task,
            request_model=None,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/parameter-matrix-tasks/{task_id}",
            name="backtest_parameter_matrix_task_delete",
            handler=delete_parameter_matrix_task,
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/parameter-matrix-tasks/{task_id}/run",
            name="backtest_parameter_matrix_task_run",
            handler=lambda payload, task_id: run_parameter_matrix_task(service, payload, task_id),
            request_model=ParameterMatrixTaskRunRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/research-tasks",
            name="backtest_research_tasks",
            handler=list_research_tasks,
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/research-tasks/{task_id}",
            name="backtest_research_task_detail",
            handler=get_research_task,
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/research-tasks",
            name="backtest_research_task_create",
            handler=create_research_task,
            request_model=StrategyResearchTaskCreateRequestPayload,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/research-tasks/{task_id}",
            name="backtest_research_task_delete",
            handler=delete_research_task,
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/research-tasks/{task_id}/run",
            name="backtest_research_task_run",
            handler=lambda payload, task_id: run_research_task(service, payload, task_id),
            request_model=StrategyResearchTaskRunRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/data-assets",
            name="backtest_data_asset_directory",
            handler=lambda payload: list_data_asset_directory(service, payload),
            request_model=BacktestDataAssetDirectoryQueryPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/data-assets/migrate-input-snapshots",
            name="backtest_input_snapshot_migration",
            handler=lambda payload: migrate_input_snapshots(service, payload),
            request_model=BacktestInputSnapshotMigrationRequestPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/runs",
            name="backtest_runs",
            handler=lambda: list_backtest_runs(service, 50),
            request_model=None,
        ),
        RouteDefinition(
            method="DELETE",
            path="/api/backtest/results/{run_id}",
            name="backtest_run_delete",
            handler=lambda run_id: delete_backtest_run(service, run_id),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/results/{run_id}/input-snapshot",
            name="backtest_input_snapshot",
            handler=lambda run_id: get_input_snapshot(service, run_id),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/results/{run_id}/table",
            name="backtest_result_table",
            handler=lambda payload, run_id: get_result_table(service, payload, run_id),
            request_model=BacktestResultTableQueryPayload,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/experiments/{run_id_prefix}/panel",
            name="backtest_experiment_panel",
            handler=lambda run_id_prefix: get_experiment_panel(service, run_id_prefix),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/results/{run_id_prefix}/portfolio-panel",
            name="backtest_portfolio_panel",
            handler=lambda run_id_prefix: get_portfolio_panel(service, run_id_prefix),
            request_model=None,
        ),
        RouteDefinition(
            method="GET",
            path="/api/backtest/results/{run_id}/panel",
            name="backtest_result_panel",
            handler=lambda run_id: get_result_panel(service, run_id),
            request_model=None,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/run-once",
            name="backtest_run_once",
            handler=lambda payload: run_once(service, payload),
            request_model=BacktestRunRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/parameter-scan",
            name="backtest_parameter_scan",
            handler=lambda payload: run_parameter_scan(service, payload),
            request_model=ParameterScanRequestPayload,
        ),
        RouteDefinition(
            method="POST",
            path="/api/backtest/run-batch",
            name="backtest_run_batch",
            handler=lambda payload: run_batch(batch_service, payload),
            request_model=BatchBacktestRunRequestPayload,
        ),
    ]


def _strategy_library() -> list[StrategyDefinitionPayload]:
    return [
        StrategyDefinitionPayload(
            strategy_id="moving_average_strategy",
            name="双均线趋势策略",
            category="趋势跟随",
            description="参考 SleeperCloudQuant-old 的回测服务入口，使用短长均线交叉作为示例信号。",
            parameters={"short_window": 5, "long_window": 20, "position_size": 1.0},
            parameter_schema={"short_window": {"type": "integer", "min": 2}, "long_window": {"type": "integer", "min": 3}, "position_size": {"type": "number", "min": 0, "max": 1}},
            source_reference="SleeperCloudQuant-old/core/services/strategy_backtest_service.py",
            source_code=(
                "def handle_bar(context, bar):\n"
                "    short_ma = mean(close, window=5)\n"
                "    long_ma = mean(close, window=20)\n"
                "    if short_ma > long_ma:\n"
                "        order_target_percent(bar.symbol, 1.0)\n"
                "    else:\n"
                "        order_target_percent(bar.symbol, 0.0)\n"
            ),
        ),
        StrategyDefinitionPayload(
            strategy_id="factor_topn_rotation",
            name="因子 TopN 轮动策略",
            category="因子轮动",
            description="结合 factor_lab 的截面排名结果，选择 Top N 标的等权持有。",
            parameters={"factor_id": "close_to_ma2_bias", "top_n": 2, "rebalance": "daily"},
            parameter_schema={"factor_id": {"type": "string"}, "top_n": {"type": "integer", "min": 1}, "rebalance": {"type": "enum", "options": ["daily", "weekly", "monthly"]}},
            source_reference="factor_lab + backtrader 指标体验参考",
            source_code=(
                "def rebalance(context, factor_snapshot):\n"
                "    candidates = rank_by_factor(factor_snapshot, top_n=2)\n"
                "    for symbol in candidates:\n"
                "        order_target_percent(symbol, 1 / len(candidates))\n"
            ),
        ),
        StrategyDefinitionPayload(
            strategy_id="risk_controlled_breakout",
            name="风控突破策略",
            category="风险控制",
            description="参考 rqalpha/vnpy 的账户、持仓和订单语义，展示止损与仓位约束。",
            parameters={"breakout_window": 20, "stop_loss": 0.08, "max_position": 0.5},
            parameter_schema={"breakout_window": {"type": "integer", "min": 2}, "stop_loss": {"type": "number", "min": 0, "max": 1}, "max_position": {"type": "number", "min": 0, "max": 1}},
            source_reference="rqalpha-master + vnpy-master 语义对齐",
            source_code=(
                "def handle_bar(context, bar):\n"
                "    if bar.close > highest(high, window=20):\n"
                "        order_target_percent(bar.symbol, 0.5)\n"
                "    if drawdown(bar.symbol) > 0.08:\n"
                "        order_target_percent(bar.symbol, 0.0)\n"
            ),
        ),
    ]


def _load_strategy_versions() -> dict[str, list[StrategyDefinitionPayload]]:
    if not _STRATEGY_DRAFTS_PATH.exists():
        return {}
    try:
        raw = json.loads(_STRATEGY_DRAFTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = raw.get("versions", raw) if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        return {}
    grouped: dict[str, list[StrategyDefinitionPayload]] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        try:
            strategy_id = str(item["strategy_id"])
            version = str(item.get("latest_version") or item.get("version") or f"v{len(grouped.get(strategy_id, [])) + 1}")
            strategy = StrategyDefinitionPayload(
                strategy_id=strategy_id,
                name=str(item["name"]),
                category=str(item.get("category") or "自定义草稿"),
                description=str(item.get("description") or f"策略草稿版本 {version}"),
                parameters=dict(item.get("parameters") or {}),
                parameter_schema=dict(item.get("parameter_schema") or _infer_parameter_schema(item.get("parameters") or {})),
                source_code=str(item.get("source_code") or ""),
                source_reference=str(item.get("source_reference") or "web-mvp-draft"),
                editable=bool(item.get("editable", True)),
                latest_version=version,
                version_count=int(item.get("version_count") or len(grouped.get(strategy_id, [])) + 1),
                saved_at=item.get("saved_at"),
            )
        except (KeyError, TypeError, ValueError):
            continue
        grouped.setdefault(strategy.strategy_id, []).append(strategy)
    return grouped


def _write_strategy_versions(versions: dict[str, list[StrategyDefinitionPayload]]) -> None:
    _STRATEGY_DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for items in versions.values():
        for item in items:
            records.append(
                {
                    "strategy_id": item.strategy_id,
                    "name": item.name,
                    "category": item.category,
                    "description": item.description,
                    "parameters": item.parameters,
                    "parameter_schema": item.parameter_schema,
                    "source_code": item.source_code,
                    "source_reference": item.source_reference,
                    "editable": item.editable,
                    "latest_version": item.latest_version,
                    "version_count": item.version_count,
                    "saved_at": item.saved_at,
                }
            )
    _STRATEGY_DRAFTS_PATH.write_text(json.dumps({"versions": records}, ensure_ascii=False, indent=2), encoding="utf-8")




def _parameter_combinations(parameter_grid: dict[str, list[Any]], *, max_runs: int) -> list[dict[str, Any]]:
    items = [(key, values) for key, values in parameter_grid.items() if isinstance(values, list) and values]
    if not items:
        return []
    combinations: list[dict[str, Any]] = [{}]
    for key, values in items:
        next_combinations: list[dict[str, Any]] = []
        for combination in combinations:
            for value in values:
                next_combinations.append({**combination, key: value})
                if len(next_combinations) >= max(1, max_runs):
                    break
            if len(next_combinations) >= max(1, max_runs):
                break
        combinations = next_combinations
        if len(combinations) >= max(1, max_runs):
            break
    return combinations[: max(1, max_runs)]
def _infer_parameter_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, bool):
            schema[key] = {"type": "boolean"}
        elif isinstance(value, int):
            schema[key] = {"type": "integer"}
        elif isinstance(value, float):
            schema[key] = {"type": "number"}
        else:
            schema[key] = {"type": "string"}
    return schema


def _to_run_request(item: Any) -> BacktestRunRequest:
    extra_config = dict(item.extra_config)
    if item.strategy_id:
        extra_config["strategy_id"] = item.strategy_id
    if item.strategy_version:
        extra_config["strategy_version"] = item.strategy_version
    return BacktestRunRequest(
        run_id=item.run_id,
        strategy_name=item.strategy_name,
        symbol=item.symbol,
        benchmark=item.benchmark,
        start_date=item.start_date,
        end_date=item.end_date,
        initial_cash=item.initial_cash,
        frequency=item.frequency,
        parameters=item.parameters,
        extra_config=extra_config,
        strategy_id=item.strategy_id,
        strategy_version=item.strategy_version,
    )




def _load_parameter_matrix_tasks() -> list[dict[str, Any]]:
    if not _PARAMETER_MATRIX_TASKS_PATH.exists():
        return []
    try:
        raw = json.loads(_PARAMETER_MATRIX_TASKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    return [dict(item) for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []


def _write_parameter_matrix_tasks(tasks: list[dict[str, Any]]) -> None:
    _PARAMETER_MATRIX_TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PARAMETER_MATRIX_TASKS_PATH.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


def _parameter_matrix_score(metrics: dict[str, Any]) -> float:
    annual = _to_float_or_none(metrics.get("annualized_returns")) or 0.0
    total = _to_float_or_none(metrics.get("total_returns")) or 0.0
    drawdown = abs(_to_float_or_none(metrics.get("max_drawdown")) or 0.0)
    sharpe = _to_float_or_none(metrics.get("sharpe")) or 0.0
    return round(annual * 100 + total * 40 + sharpe * 8 - drawdown * 80, 6)

def _load_research_tasks() -> list[dict[str, Any]]:
    if not _RESEARCH_TASKS_PATH.exists():
        return []
    try:
        raw = json.loads(_RESEARCH_TASKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    return [dict(item) for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []


def _write_research_tasks(tasks: list[dict[str, Any]]) -> None:
    _RESEARCH_TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RESEARCH_TASKS_PATH.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_strategy_definition(strategy_id: str) -> StrategyDefinitionPayload | None:
    for item in list_strategies().strategies:
        if item.strategy_id == strategy_id:
            return item
    return None


def _normalize_research_symbols(symbols: list[str]) -> list[str]:
    normalized = []
    for item in symbols or []:
        symbol = str(item).strip()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    return normalized[:50] or ["000001.XSHE"]


def _default_indicator_plan(strategy_id: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    if strategy_id == "moving_average_strategy":
        return [
            {"indicator_id": "short_ma", "kind": "moving_average", "window": parameters.get("short_window", 5), "source_field": "close"},
            {"indicator_id": "long_ma", "kind": "moving_average", "window": parameters.get("long_window", 20), "source_field": "close"},
        ]
    if strategy_id == "factor_topn_rotation":
        return [{"indicator_id": str(parameters.get("factor_id", "close_to_ma2_bias")), "kind": "factor_rank", "top_n": parameters.get("top_n", 2)}]
    return [{"indicator_id": "price_breakout", "kind": "rolling_high", "window": parameters.get("breakout_window", 20), "source_field": "high"}]


def _default_signal_rules(strategy_id: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    if strategy_id == "moving_average_strategy":
        return [
            {"signal": "long_entry", "when": "short_ma > long_ma", "target_position": parameters.get("position_size", 1.0)},
            {"signal": "flat", "when": "short_ma <= long_ma", "target_position": 0.0},
        ]
    if strategy_id == "factor_topn_rotation":
        return [{"signal": "select_top_n", "when": "factor_rank <= top_n", "target_weight": "equal_weight"}]
    return [
        {"signal": "breakout_entry", "when": "close > rolling_high", "target_position": parameters.get("max_position", 0.5)},
        {"signal": "stop_loss_exit", "when": "drawdown > stop_loss", "target_position": 0.0},
    ]


def _build_signal_preview(*, symbols: list[str], start_date: str, end_date: str, signal_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preview = []
    for symbol in symbols[:5]:
        for index, rule in enumerate(signal_rules[:3], start=1):
            preview.append({"symbol": symbol, "date": start_date if index == 1 else end_date, "signal": rule.get("signal", "signal"), "rule": rule.get("when", "manual"), "action": {key: value for key, value in rule.items() if key.startswith("target_")}})
    return preview








def _load_experiment_index() -> list[dict[str, Any]]:
    if not _EXPERIMENT_INDEX_PATH.exists():
        return []
    try:
        raw = json.loads(_EXPERIMENT_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    experiments = raw.get("experiments") if isinstance(raw, dict) else raw
    return [dict(item) for item in experiments if isinstance(item, dict)] if isinstance(experiments, list) else []


def _write_experiment_index(experiments: list[dict[str, Any]]) -> None:
    _EXPERIMENT_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    _EXPERIMENT_INDEX_PATH.write_text(json.dumps({"experiments": experiments}, ensure_ascii=False, indent=2), encoding="utf-8")


def _upsert_experiment_index(experiment: dict[str, Any]) -> None:
    experiments = [item for item in _load_experiment_index() if item.get("experiment_id") != experiment.get("experiment_id")]
    experiments.append(experiment)
    _write_experiment_index(experiments)


def _filter_experiment_index(experiments: list[dict[str, Any]], payload: BacktestExperimentIndexFilterPayload) -> list[dict[str, Any]]:
    search = str(payload.search or "").strip().lower()
    tag = str(payload.tag or "").strip().lower()
    status = str(payload.status or "").strip().lower()
    filtered = []
    for experiment in experiments:
        tags = [str(item).lower() for item in experiment.get("tags") or []]
        archived = bool(experiment.get("archived")) or str(experiment.get("status") or "").lower() == "archived"
        if archived and not payload.include_archived:
            continue
        if tag and tag not in tags:
            continue
        if status and str(experiment.get("status") or "").lower() != status:
            continue
        if search:
            haystack = " ".join([
                str(experiment.get("experiment_id") or ""),
                str(experiment.get("run_id_prefix") or ""),
                str(experiment.get("name") or ""),
                str(experiment.get("description") or ""),
                " ".join(tags),
            ]).lower()
            if search not in haystack:
                continue
        filtered.append(experiment)
    return filtered


def _summarize_experiment_index(experiments: list[dict[str, Any]]) -> dict[str, Any]:
    tag_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for experiment in experiments:
        status = str(experiment.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        for tag in experiment.get("tags") or []:
            key = str(tag)
            tag_counts[key] = tag_counts.get(key, 0) + 1
    return {
        "count": len(experiments),
        "status_counts": status_counts,
        "tag_counts": tag_counts,
        "archived_count": sum(1 for item in experiments if item.get("archived") or item.get("status") == "archived"),
    }


def _normalize_experiment_tags(tags: list[str] | None) -> list[str]:
    normalized = []
    for tag in tags or []:
        value = str(tag).strip()
        if value and value not in normalized:
            normalized.append(value)
    return normalized[:20]


def _to_float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize_experiment_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [row.get("annualized_returns") for row in rows if row.get("annualized_returns") is not None]
    drawdowns = [row.get("max_drawdown") for row in rows if row.get("max_drawdown") is not None]
    return {
        "count": len(rows),
        "best_annualized_returns": max(returns) if returns else None,
        "worst_max_drawdown": min(drawdowns) if drawdowns else None,
        "average_annualized_returns": sum(returns) / len(returns) if returns else None,
    }


def _build_experiment_index_entry(
    *,
    run_id_prefix: str,
    name: str,
    experiment_id: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    task_id: str | None = None,
    primary_run_id: str | None = None,
    status: str = "indexed",
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    normalized_prefix = run_id_prefix or experiment_id or "experiment"
    normalized_id = experiment_id or normalized_prefix
    report_links = {
        "experiment_panel": f"/api/backtest/experiments/{normalized_prefix}/panel",
        "portfolio_panel": f"/api/backtest/results/{normalized_prefix}/portfolio-panel",
        "trades_export_csv": f"/api/backtest/results/{primary_run_id or normalized_prefix + '-001'}/table?table=trades&offset=0&limit=500&export_format=csv",
    }
    if primary_run_id:
        report_links["reporting_run_detail"] = f"/api/reporting/run-detail/{primary_run_id}"
        report_links["strategy_evaluation"] = f"/api/reporting/strategy-evaluation/{primary_run_id}"
    return {
        "experiment_id": normalized_id,
        "run_id_prefix": normalized_prefix,
        "name": name,
        "description": description,
        "status": status,
        "tags": [str(tag) for tag in (tags or []) if str(tag)],
        "task_id": task_id,
        "primary_run_id": primary_run_id,
        "report_links": report_links,
        "created_at": now,
        "updated_at": now,
    }













