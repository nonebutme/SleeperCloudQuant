"""Batch comparison implementation for phase-1 reporting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .store_protocols import ReportingStore


@dataclass(frozen=True, slots=True)
class BatchExperimentRow:
    """One normalized comparison row inside a batch experiment summary."""

    rank: int
    run_id: str
    strategy_name: str
    strategy_id: str
    symbol: str | None
    short_window: int | None
    long_window: int | None
    annualized_returns: float | None
    total_returns: float | None
    max_drawdown: float | None
    sharpe: float | None
    status: str
    error_message: str | None


@dataclass(frozen=True, slots=True)
class BatchExperimentSummary:
    """Aggregated comparison view for one batch experiment."""

    experiment_id: str
    profile: str
    status: str
    started_at: str
    finished_at: str | None
    request_count: int
    success_count: int
    failure_count: int
    rows: Sequence[BatchExperimentRow]
    yearly_rows: Sequence[Mapping[str, Any]]
    failures: Sequence[Mapping[str, Any]]


class BatchComparisonService:
    """Read batch experiment metadata and join it with archived backtest results."""

    def __init__(self, store: ReportingStore) -> None:
        self._store = store

    def summarize_experiment(
        self,
        experiment_id: str,
    ) -> BatchExperimentSummary | None:
        """Return one batch experiment summary sorted by core performance metrics."""

        experiment = self._store.fetch_research_run(experiment_id)
        if experiment is None:
            return None

        parameters = self._coerce_mapping(experiment.get("parameters"))
        run_ids = [
            str(item) for item in parameters.get("run_ids", []) if isinstance(item, str)
        ]
        rows: list[BatchExperimentRow] = []
        yearly_rows: list[Mapping[str, Any]] = []
        for run_id in run_ids:
            run = self._store.fetch_backtest_run(run_id)
            if run is None:
                continue
            row = self._build_row(run_id, run)
            rows.append(row)
            yearly_rows.extend(
                self._build_yearly_rows(
                    run_id,
                    row.strategy_name,
                    row.short_window,
                    row.long_window,
                    self._store.fetch_backtest_yearly_returns(run_id),
                )
            )

        sorted_rows = sorted(
            rows,
            key=lambda item: (
                -(item.annualized_returns if item.annualized_returns is not None else -999),
                item.max_drawdown if item.max_drawdown is not None else 999,
                item.run_id,
            ),
        )
        ranked_rows = [
            BatchExperimentRow(
                rank=index + 1,
                run_id=row.run_id,
                strategy_name=row.strategy_name,
                strategy_id=row.strategy_id,
                symbol=row.symbol,
                short_window=row.short_window,
                long_window=row.long_window,
                annualized_returns=row.annualized_returns,
                total_returns=row.total_returns,
                max_drawdown=row.max_drawdown,
                sharpe=row.sharpe,
                status=row.status,
                error_message=row.error_message,
            )
            for index, row in enumerate(sorted_rows)
        ]
        return BatchExperimentSummary(
            experiment_id=str(experiment["run_id"]),
            profile=str(experiment.get("strategy_name") or parameters.get("profile") or "--"),
            status=str(experiment.get("status") or "--"),
            started_at=str(experiment.get("started_at") or "--"),
            finished_at=(
                None
                if experiment.get("finished_at") is None
                else str(experiment.get("finished_at"))
            ),
            request_count=int(parameters.get("request_count") or len(run_ids)),
            success_count=int(parameters.get("success_count") or len(ranked_rows)),
            failure_count=int(parameters.get("failure_count") or 0),
            rows=ranked_rows,
            yearly_rows=tuple(yearly_rows),
            failures=tuple(self._coerce_sequence(parameters.get("failures"))),
        )

    def _build_row(
        self,
        run_id: str,
        run: Mapping[str, Any],
    ) -> BatchExperimentRow:
        metrics = self._index_metrics(self._store.fetch_backtest_metrics(run_id))
        parameters = self._coerce_mapping(run.get("parameters"))
        return BatchExperimentRow(
            rank=0,
            run_id=run_id,
            strategy_name=str(run.get("strategy_name") or "--"),
            strategy_id=str(run.get("strategy_id") or "--"),
            symbol=self._to_optional_text(run.get("universe")),
            short_window=self._to_optional_int(parameters.get("short_window")),
            long_window=self._to_optional_int(parameters.get("long_window")),
            annualized_returns=self._to_optional_float(metrics.get("annualized_returns")),
            total_returns=self._to_optional_float(metrics.get("total_returns")),
            max_drawdown=self._to_optional_float(metrics.get("max_drawdown")),
            sharpe=self._to_optional_float(metrics.get("sharpe")),
            status=str(run.get("status") or "--"),
            error_message=self._to_optional_text(run.get("error_message")),
        )

    def _build_yearly_rows(
        self,
        run_id: str,
        strategy_name: str,
        short_window: int | None,
        long_window: int | None,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        normalized: list[Mapping[str, Any]] = []
        for row in rows:
            normalized.append(
                {
                    "run_id": run_id,
                    "strategy_name": strategy_name,
                    "short_window": short_window,
                    "long_window": long_window,
                    "year": str(row.get("year") or "--"),
                    "portfolio_return": self._to_optional_float(row.get("portfolio_return")),
                    "benchmark_return": self._to_optional_float(row.get("benchmark_return")),
                    "excess_return": self._to_optional_float(row.get("excess_return")),
                }
            )
        return normalized

    @staticmethod
    def _index_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        indexed: dict[str, Any] = {}
        for row in rows:
            indexed[str(row["metric_name"])] = (
                row["metric_value"]
                if row.get("metric_value") is not None
                else row.get("metric_text")
            )
        return indexed

    @staticmethod
    def _coerce_mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    @staticmethod
    def _coerce_sequence(value: Any) -> Sequence[Mapping[str, Any]]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [dict(item) for item in value if isinstance(item, Mapping)]

    @staticmethod
    def _to_optional_text(value: Any) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _to_optional_int(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None

    @staticmethod
    def _to_optional_float(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None
