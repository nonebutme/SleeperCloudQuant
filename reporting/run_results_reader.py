"""Single-run result reader implementation for phase-1 reporting."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .store_protocols import ReportingStore


@dataclass(frozen=True, slots=True)
class BacktestRunDetail:
    """Normalized result detail for one archived backtest run."""

    run: Mapping[str, Any]
    metrics: Mapping[str, Any]
    logs: Sequence[Mapping[str, Any]]
    trades: Sequence[Mapping[str, Any]]
    positions: Sequence[Mapping[str, Any]]
    accounts: Sequence[Mapping[str, Any]]
    yearly_returns: Sequence[Mapping[str, Any]]


class RunResultsReader:
    """Aggregate archived backtest data into reporting-friendly structures."""

    def __init__(self, store: ReportingStore) -> None:
        self._store = store

    def get_run_detail(self, run_id: str) -> BacktestRunDetail | None:
        """Return one fully-hydrated backtest run."""

        run = self._store.fetch_backtest_run(run_id)
        if run is None:
            return None

        metrics = {
            str(row["metric_name"]): (
                row["metric_value"]
                if row.get("metric_value") is not None
                else row.get("metric_text")
            )
            for row in self._store.fetch_backtest_metrics(run_id)
        }
        metrics = _fill_derived_metrics(metrics)
        raw_result = dict(run.get("raw_result") or {})
        return BacktestRunDetail(
            run=run,
            metrics=metrics,
            logs=self._store.fetch_backtest_logs(run_id),
            trades=_merge_artifact_rows(self._store.fetch_backtest_trades(run_id), raw_result.get("trades") or []),
            positions=_merge_artifact_rows(self._store.fetch_backtest_positions(run_id), raw_result.get("positions") or []),
            accounts=_ensure_account_snapshot_times(
                _merge_artifact_rows(self._store.fetch_backtest_accounts(run_id), raw_result.get("accounts") or []),
                fallback_time=str(run.get("completed_at") or run.get("created_at") or ""),
            ),
            yearly_returns=self._store.fetch_backtest_yearly_returns(run_id),
        )

    def build_account_value_chart(
        self,
        detail: BacktestRunDetail,
    ) -> list[Mapping[str, Any]]:
        """Return account equity snapshots sorted for chart rendering."""

        account_rows = _select_preferred_account_rows(detail.accounts)
        rows: list[Mapping[str, Any]] = []
        for account in account_rows:
            snapshot_time = account.get("snapshot_time")
            if not snapshot_time:
                continue
            rows.append(
                {
                    "snapshot_time": snapshot_time,
                    "total_value": _coerce_float(account.get("total_value")),
                    "unit_net_value": _coerce_float(account.get("unit_net_value")),
                    "market_value": _coerce_float(account.get("market_value")),
                    "cash": _coerce_float(account.get("cash")),
                }
            )
        return sorted(rows, key=lambda item: _parse_sortable_time(item["snapshot_time"]))

    def build_trade_activity_chart(
        self,
        detail: BacktestRunDetail,
    ) -> list[Mapping[str, Any]]:
        """Return daily buy/sell activity aggregated for chart rendering."""

        daily: dict[str, dict[str, Any]] = {}
        for trade in detail.trades:
            trade_time = str(trade.get("trade_time") or "")
            if not trade_time:
                continue
            trade_date = trade_time[:10]
            side = str(trade.get("side") or "").upper()
            amount = abs(_coerce_float(trade.get("amount")))
            quantity = abs(_coerce_float(trade.get("quantity")))
            bucket = daily.setdefault(
                trade_date,
                {
                    "trade_date": trade_date,
                    "buy_count": 0,
                    "sell_count": 0,
                    "buy_amount": 0.0,
                    "sell_amount": 0.0,
                    "buy_quantity": 0.0,
                    "sell_quantity": 0.0,
                },
            )
            if side == "SELL":
                bucket["sell_count"] += 1
                bucket["sell_amount"] += amount
                bucket["sell_quantity"] += quantity
            else:
                bucket["buy_count"] += 1
                bucket["buy_amount"] += amount
                bucket["buy_quantity"] += quantity
        return [daily[key] for key in sorted(daily)]

    def build_position_exposure_chart(
        self,
        detail: BacktestRunDetail,
    ) -> list[Mapping[str, Any]]:
        """Return per-snapshot position exposure and holding counts."""

        snapshots: dict[str, dict[str, Any]] = {}
        for position in detail.positions:
            snapshot_time = str(position.get("snapshot_time") or "")
            if not snapshot_time:
                continue
            bucket = snapshots.setdefault(
                snapshot_time,
                {
                    "snapshot_time": snapshot_time,
                    "position_count": 0,
                    "position_quantity": 0.0,
                    "position_market_value": 0.0,
                },
            )
            quantity = _coerce_float(position.get("quantity"))
            market_value = _coerce_float(position.get("market_value"))
            if quantity > 0 or market_value > 0:
                bucket["position_count"] += 1
            bucket["position_quantity"] += quantity
            bucket["position_market_value"] += market_value
        return sorted(
            snapshots.values(),
            key=lambda item: _parse_sortable_time(item["snapshot_time"]),
        )

    def build_yearly_return_chart(
        self,
        detail: BacktestRunDetail,
    ) -> list[Mapping[str, Any]]:
        """Return yearly return rows normalized for chart rendering."""

        rows: list[Mapping[str, Any]] = []
        for row in detail.yearly_returns:
            year = row.get("year")
            if year in (None, ""):
                continue
            rows.append(
                {
                    "year": str(year),
                    "portfolio_return": _coerce_float(
                        row.get("portfolio_return"),
                        allow_none=True,
                    ),
                    "benchmark_return": _coerce_float(
                        row.get("benchmark_return"),
                        allow_none=True,
                    ),
                    "excess_return": _coerce_float(
                        row.get("excess_return"),
                        allow_none=True,
                    ),
                }
            )
        return sorted(rows, key=lambda item: item["year"])


def _merge_artifact_rows(
    persisted: Sequence[Mapping[str, Any]],
    raw: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if len(persisted) != len(raw):
        return [dict(row) for row in persisted]
    return [{**dict(saved), **dict(source)} for saved, source in zip(persisted, raw)]

def _ensure_account_snapshot_times(
    accounts: Sequence[Mapping[str, Any]],
    *,
    fallback_time: str,
) -> list[Mapping[str, Any]]:
    normalized_accounts: list[Mapping[str, Any]] = []
    for account in accounts:
        snapshot_time = account.get("snapshot_time") or fallback_time
        normalized_accounts.append({**dict(account), "snapshot_time": snapshot_time})
    return normalized_accounts


def _coerce_float(value: Any, *, allow_none: bool = False) -> float | None:
    if value in (None, ""):
        return None if allow_none else 0.0
    return float(value)


def _parse_sortable_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.min


def _fill_derived_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(metrics)
    if normalized.get("calmar") in (None, ""):
        annualized = _coerce_float(
            normalized.get("annualized_returns"),
            allow_none=True,
        )
        max_drawdown = _coerce_float(
            normalized.get("max_drawdown"),
            allow_none=True,
        )
        if annualized is not None and max_drawdown not in (None, 0.0):
            normalized["calmar"] = annualized / abs(max_drawdown)
    return normalized


def _select_preferred_account_rows(
    accounts: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    portfolio_rows = [
        row
        for row in accounts
        if str((row.get("notes") or {}).get("account_type") or "") == "portfolio"
    ]
    candidate_rows = portfolio_rows or list(accounts)
    best_by_snapshot: dict[str, Mapping[str, Any]] = {}
    for account in candidate_rows:
        snapshot_time = str(account.get("snapshot_time") or "")
        if not snapshot_time:
            continue
        current = best_by_snapshot.get(snapshot_time)
        if current is None or _account_row_priority(account) > _account_row_priority(current):
            best_by_snapshot[snapshot_time] = account
    if best_by_snapshot:
        return [
            best_by_snapshot[key]
            for key in sorted(best_by_snapshot, key=_parse_sortable_time)
        ]
    return list(candidate_rows)


def _account_row_priority(account: Mapping[str, Any]) -> tuple[int, int]:
    unit_net_value = account.get("unit_net_value")
    total_value = account.get("total_value")
    return (
        1 if unit_net_value not in (None, "") else 0,
        1 if total_value not in (None, "") else 0,
    )
