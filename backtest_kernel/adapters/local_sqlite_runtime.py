"""Local SQLite market-data driven runtime for rqalpha-compatible smoke runs."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from backtest_kernel.strategy_execution import execute_strategy_evidence
from data_platform.repository.contracts import MarketDataRepository


class LocalSQLiteBacktestRuntime:
    """Execute one deterministic single-symbol backtest from local OHLCV rows."""

    def __init__(
        self,
        market_repository: MarketDataRepository,
        *,
        strategy_resolver: Callable[[str, str | None], Mapping[str, Any]] | None = None,
    ) -> None:
        self._market_repository = market_repository
        self._strategy_resolver = strategy_resolver

    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        parameters = dict(payload.get("parameters") or {})
        symbol = str(parameters.get("symbol") or payload.get("symbol") or "000001.XSHE")
        start_date = str(payload.get("start_date") or "")
        end_date = str(payload.get("end_date") or "")
        adjustment = str(parameters.get("adjustment") or "raw")
        try:
            history = self._market_repository.fetch_price_history(
                symbol,
                start_date,
                end_date,
                adjustment=adjustment,
            )
        except TypeError:
            history = self._market_repository.fetch_price_history(symbol, start_date, end_date)
        rows = [dict(row) for row in history]
        if len(rows) < 2:
            raise RuntimeError(f"not enough market rows for local runtime: {symbol} {start_date}..{end_date}")

        initial_cash = float(payload.get("initial_cash") or 1_000_000)
        strategy_name = str(payload.get("strategy_name") or "local_sqlite_strategy")
        extra_config = dict(payload.get("extra_config") or {})
        rqalpha_config = _normalize_rqalpha_local_config(extra_config.get("rqalpha_local"))
        short_window = _positive_int(parameters.get("short_window"), default=5)
        long_window = _positive_int(parameters.get("long_window"), default=max(short_window + 1, 20))
        position_size = min(max(float(parameters.get("position_size") or parameters.get("max_position") or 1.0), 0.0), 1.0)
        if long_window <= short_window:
            long_window = short_window + 1

        strategy_snapshot: Mapping[str, Any] | None = None
        target_weights: list[float] | None = None
        raw_scores: list[float | None] | None = None
        score_contract = "unavailable_legacy_strategy"
        strategy_id = str(extra_config.get("strategy_id") or "")
        strategy_version = str(extra_config.get("strategy_version") or "") or None
        if self._strategy_resolver is not None and strategy_id:
            strategy_snapshot = self._strategy_resolver(strategy_id, strategy_version)
            strategy_evidence = execute_strategy_evidence(
                str(strategy_snapshot.get("source_code") or ""),
                rows,
                parameters,
            )
            target_weights = list(strategy_evidence["weights"])
            raw_scores = strategy_evidence.get("raw_scores")
            score_contract = str(strategy_evidence.get("score_contract") or "")

        close_values = [float(row.get("close") or 0.0) for row in rows]
        cash = initial_cash
        quantity = 0.0
        trades: list[dict[str, Any]] = []
        positions: list[dict[str, Any]] = []
        accounts: list[dict[str, Any]] = []
        equity_curve: list[tuple[str, float]] = []

        for index, row in enumerate(rows):
            date = str(row.get("date") or "")[:10]
            close = float(row.get("close") or 0.0)
            if close <= 0:
                continue
            total_value = cash + quantity * close
            short_ma = _mean(close_values[max(0, index - short_window + 1) : index + 1])
            long_ma = _mean(close_values[max(0, index - long_window + 1) : index + 1])
            target_weight = (
                target_weights[index]
                if target_weights is not None
                else (position_size if index + 1 >= long_window and short_ma >= long_ma else 0.0)
            )
            target_quantity = math.floor((total_value * target_weight) / close / 100.0) * 100.0
            delta = target_quantity - quantity
            if abs(delta) >= 1:
                side = "BUY" if delta > 0 else "SELL"
                execution_price = close * (1.0 + rqalpha_config["slippage_rate"] if side == "BUY" else 1.0 - rqalpha_config["slippage_rate"])
                amount = abs(delta) * execution_price
                commission = max(amount * rqalpha_config["commission_rate"], rqalpha_config["min_commission"] if amount > 0 else 0.0)
                tax = amount * rqalpha_config["tax_rate"] if side == "SELL" else 0.0
                cash -= delta * execution_price
                cash -= commission + tax
                quantity = target_quantity
                trades.append(
                    {
                        "trade_time": f"{date}T15:00:00+08:00",
                        "order_book_id": symbol,
                        "side": side,
                        "position_effect": "OPEN" if side == "BUY" else "CLOSE",
                        "price": round(execution_price, 6),
                        "quantity": abs(delta),
                        "amount": round(amount, 6),
                        "commission": round(commission, 6),
                        "tax": round(tax, 6),
                        "notes": {
                            "runtime": "local_sqlite_backtest",
                            "target_weight": target_weight,
                            "raw_signal_score": raw_scores[index] if raw_scores is not None else None,
                            "market_vwap": _market_vwap(row, close),
                            "market_volume": _positive_float(row.get("volume")),
                            "rqalpha_local": rqalpha_config,
                        },
                    }
                )
            market_value = quantity * close
            total_value = cash + market_value
            equity_curve.append((date, total_value))
            positions.append(
                {
                    "snapshot_time": f"{date}T15:00:00+08:00",
                    "order_book_id": symbol,
                    "quantity": quantity,
                    "market_value": market_value,
                    "avg_price": close if quantity else 0.0,
                    "weight": market_value / total_value if total_value else 0.0,
                    "notes": {"runtime": "local_sqlite_backtest"},
                }
            )
            accounts.append(
                {
                    "snapshot_time": f"{date}T15:00:00+08:00",
                    "total_value": total_value,
                    "market_value": market_value,
                    "cash": cash,
                    "unit_net_value": total_value / initial_cash if initial_cash else 0.0,
                    "notes": {"runtime": "local_sqlite_backtest"},
                }
            )

        benchmark_curve = _build_benchmark_curve(rows, rqalpha_config)
        metrics = _build_metrics(equity_curve, initial_cash, benchmark_curve=benchmark_curve)
        yearly_returns = _build_yearly_returns(equity_curve, benchmark_curve=benchmark_curve)
        logs = [
            {
                "recorded_at": f"{equity_curve[-1][0]}T15:00:00+08:00",
                "level": "INFO",
                "stage": "local_sqlite_runtime",
                "message": f"completed {symbol} with {len(rows)} bars and {len(trades)} trades",
            }
        ]
        return {
            "run_id": str(payload.get("run_id") or "local-sqlite-run"),
            "strategy_name": strategy_name,
            "status": "completed",
            "start_date": start_date,
            "end_date": end_date,
            "benchmark": str(payload.get("benchmark") or "000300.XSHG"),
            "metrics": metrics,
            "raw_result": {
                "engine": "local_sqlite_backtest_runtime",
                "data_source": "local_sqlite_market_data",
                "adjustment": adjustment,
                "symbol": symbol,
                "bar_count": len(rows),
                "rqalpha_local": rqalpha_config,
                "strategy_template": _build_strategy_template(strategy_name, symbol, parameters, rqalpha_config),
                "strategy_binding": {
                    "strategy_id": strategy_snapshot.get("strategy_id") if strategy_snapshot else strategy_id or None,
                    "strategy_version": strategy_snapshot.get("latest_version") if strategy_snapshot else strategy_version,
                    "source_sha256": strategy_snapshot.get("source_sha256") if strategy_snapshot else None,
                    "execution_contract": strategy_snapshot.get("execution_contract") if strategy_snapshot else "legacy-ma-fallback",
                },
                "signal_evidence": {
                    "version": "stage80-point-in-time-signal-v1",
                    "status": "ready" if raw_scores is not None else "unavailable",
                    "reason": None if raw_scores is not None else score_contract,
                    "signal_name": f"{strategy_id or strategy_name}:raw_score",
                    "signal_version": strategy_snapshot.get("latest_version") if strategy_snapshot else strategy_version,
                    "source_sha256": strategy_snapshot.get("source_sha256") if strategy_snapshot else None,
                    "observed_at": "bar_close",
                    "normalization": "cross_section_required_not_applied_in_single_run",
                    "fields": ["date", "raw_score", "target_weight"],
                    "rows": [
                        [
                            str(row.get("date") or "")[:10],
                            raw_scores[index] if raw_scores is not None else None,
                            target_weights[index] if target_weights is not None else None,
                        ]
                        for index, row in enumerate(rows)
                    ] if raw_scores is not None else [],
                },
                "price_bars": [
                    {
                        "date": str(row.get("date") or "")[:10],
                        "symbol": symbol,
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "volume": row.get("volume"),
                        "amount": row.get("amount"),
                    }
                    for row in rows
                ] if str(extra_config.get("mode") or "") == "single" else [],
                "benchmark_alignment": {"mode": rqalpha_config["benchmark_alignment"], "rows": len(benchmark_curve)},
                "logs": logs,
                "trades": trades,
                "positions": positions,
                "accounts": accounts,
                "yearly_returns": yearly_returns,
            },
        }


def _build_metrics(equity_curve: Sequence[tuple[str, float]], initial_cash: float, *, benchmark_curve: Sequence[tuple[str, float]] | None = None) -> dict[str, float]:
    final_value = equity_curve[-1][1]
    total_returns = final_value / initial_cash - 1.0 if initial_cash else 0.0
    days = max(len(equity_curve), 1)
    annualized_returns = (1.0 + total_returns) ** (252.0 / days) - 1.0 if total_returns > -1 else -1.0
    returns = []
    previous = equity_curve[0][1]
    peak = previous
    max_drawdown = 0.0
    for _, value in equity_curve[1:]:
        if previous:
            returns.append(value / previous - 1.0)
        peak = max(peak, value)
        drawdown = value / peak - 1.0 if peak else 0.0
        max_drawdown = min(max_drawdown, drawdown)
        previous = value
    sharpe = _sharpe(returns)
    benchmark_return = _curve_return(benchmark_curve or [])
    return {
        "total_returns": round(total_returns, 6),
        "annualized_returns": round(annualized_returns, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(sharpe, 6),
        "final_value": round(final_value, 4),
        "benchmark_return": round(benchmark_return, 6),
        "excess_return": round(total_returns - benchmark_return, 6),
    }


def _build_yearly_returns(equity_curve: Sequence[tuple[str, float]], *, benchmark_curve: Sequence[tuple[str, float]] | None = None) -> list[dict[str, Any]]:
    by_year: dict[str, list[tuple[str, float]]] = {}
    benchmark_by_year: dict[str, list[tuple[str, float]]] = {}
    for date, value in benchmark_curve or []:
        benchmark_by_year.setdefault(date[:4], []).append((date, value))
    for date, value in equity_curve:
        by_year.setdefault(date[:4], []).append((date, value))
    rows: list[dict[str, Any]] = []
    for year, values in sorted(by_year.items()):
        start_value = values[0][1]
        end_value = values[-1][1]
        portfolio_return = end_value / start_value - 1.0 if start_value else 0.0
        rows.append(
            {
                "year": year,
                "portfolio_return": round(portfolio_return, 6),
                "benchmark_return": 0.0,
                "excess_return": round(portfolio_return, 6),
                "notes": {"runtime": "local_sqlite_backtest"},
            }
        )
    return rows



def _normalize_rqalpha_local_config(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return {
        "strategy_template": str(raw.get("strategy_template") or "handle_bar_ma_cross"),
        "commission_rate": _bounded_float(raw.get("commission_rate"), default=0.0003, minimum=0.0, maximum=0.02),
        "tax_rate": _bounded_float(raw.get("tax_rate"), default=0.001, minimum=0.0, maximum=0.02),
        "min_commission": _bounded_float(raw.get("min_commission"), default=5.0, minimum=0.0, maximum=100.0),
        "slippage_rate": _bounded_float(raw.get("slippage_rate"), default=0.0005, minimum=0.0, maximum=0.05),
        "benchmark_alignment": str(raw.get("benchmark_alignment") or "same_symbol_buy_hold"),
    }


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _build_benchmark_curve(rows: Sequence[Mapping[str, Any]], config: Mapping[str, Any]) -> list[tuple[str, float]]:
    mode = str(config.get("benchmark_alignment") or "same_symbol_buy_hold")
    if mode == "zero_return":
        return []
    closes = [(str(row.get("date") or "")[:10], float(row.get("close") or 0.0)) for row in rows if float(row.get("close") or 0.0) > 0]
    if not closes:
        return []
    base = closes[0][1]
    return [(date, close / base) for date, close in closes if base]


def _curve_return(curve: Sequence[tuple[str, float]]) -> float:
    if len(curve) < 2:
        return 0.0
    start = curve[0][1]
    end = curve[-1][1]
    return end / start - 1.0 if start else 0.0


def _build_strategy_template(strategy_name: str, symbol: str, parameters: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "template_id": config.get("strategy_template") or "handle_bar_ma_cross",
        "strategy_name": strategy_name,
        "symbol": symbol,
        "parameter_mapping": {
            "short_window": parameters.get("short_window", 5),
            "long_window": parameters.get("long_window", 20),
            "position_size": parameters.get("position_size", 1.0),
        },
        "rqalpha_style_entrypoints": ["init", "handle_bar"],
        "execution_note": "Local runtime applies an rqalpha-style template and cost model; real rqalpha package execution is still gated by environment approval.",
    }
def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _market_vwap(row: Mapping[str, Any], close: float) -> float | None:
    """Infer provider volume units only when amount/volume reconciles to the bar price."""

    amount = _positive_float(row.get("amount"))
    volume = _positive_float(row.get("volume"))
    if amount is None or volume is None or close <= 0:
        return None
    for divisor in (1.0, 100.0):
        candidate = amount / volume / divisor
        if close * 0.2 <= candidate <= close * 5.0:
            return round(candidate, 6)
    return None


def _sharpe(returns: Sequence[float]) -> float:
    if len(returns) < 2:
        return 0.0
    avg = _mean(list(returns))
    variance = sum((item - avg) ** 2 for item in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    return (avg / std) * math.sqrt(252.0) if std else 0.0


