"""Shared-cash multi-stock portfolio backtests."""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from backtest_kernel.strategy_execution import execute_target_weights


class SharedPortfolioService:
    """Run one frozen A-share universe through a single simulated account."""

    def __init__(
        self,
        market_data_service: Any,
        strategy_service: Any,
        runtime_store: Any,
        database_path: str | Path = "var/runtime/shared_portfolio.sqlite3",
    ) -> None:
        self._market_data_service = market_data_service
        self._strategy_service = strategy_service
        self._runtime_store = runtime_store
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._ensure_schema()
        self._recover_interrupted_tasks()

    def create_task(
        self,
        *,
        task_id: str | None,
        name: str,
        strategy_id: str,
        strategy_version: str | None,
        symbols: list[str] | None,
        market: str,
        start_date: str,
        end_date: str,
        adjustment: str,
        benchmark: str,
        initial_cash: float,
        parameters: dict[str, Any],
        max_workers: int,
        symbol_limit: int,
        max_positions: int,
        portfolio_exposure: float,
        commission_rate: float,
        min_commission: float,
        tax_rate: float,
        slippage_rate: float,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        if adjustment not in {"raw", "qfq", "hfq"}:
            raise ValueError("adjustment must be raw, qfq, or hfq")
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        strategy = self._strategy_service.resolve_version(strategy_id, strategy_version)
        universe = self._freeze_universe(symbols=symbols or [], market=market, limit=symbol_limit)
        if not universe:
            raise ValueError("selected A-share universe is empty")
        normalized_task_id = _normalize_id(task_id or f"portfolio-{uuid4().hex[:12]}")
        now = _utc_now()
        config = {
            "mode": "shared_cash_portfolio",
            "name": name.strip() or normalized_task_id,
            "strategy_id": strategy["strategy_id"],
            "strategy_version": strategy["latest_version"],
            "source_sha256": strategy["source_sha256"],
            "execution_contract": strategy["execution_contract"],
            "market": market.upper(),
            "date_window": {"start_date": start_date, "end_date": end_date},
            "adjustment": adjustment,
            "benchmark": benchmark,
            "initial_cash": float(initial_cash),
            "parameters": dict(parameters),
            "max_workers": max(1, min(int(max_workers), 16)),
            "max_positions": max(1, min(int(max_positions), len(universe))),
            "portfolio_exposure": _bounded(portfolio_exposure, 0.0, 1.0),
            "commission_rate": _bounded(commission_rate, 0.0, 0.02),
            "min_commission": max(0.0, float(min_commission)),
            "tax_rate": _bounded(tax_rate, 0.0, 0.02),
            "slippage_rate": _bounded(slippage_rate, 0.0, 0.05),
            "lot_size": 100,
            "settlement": "A-share T+1",
            "rebalance": "daily_close_sell_then_buy",
            "universe_source": "canonical_a_share_sqlite",
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO portfolio_tasks (
                    task_id, status, config_json, universe_json, summary_json,
                    run_id, error_message, created_at, updated_at, started_at, finished_at
                ) VALUES (?, 'ready', ?, ?, '{}', NULL, NULL, ?, ?, NULL, NULL)""",
                (normalized_task_id, _dump(config), _dump(universe), now, now),
            )
        return self.get_task(normalized_task_id)

    def start_task(self, task_id: str, *, wait: bool = False) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return task
        with self._lock:
            active = self._threads.get(task_id)
            if active is None or not active.is_alive():
                active = threading.Thread(
                    target=self._execute_task,
                    args=(task_id,),
                    name=f"portfolio-{task_id}",
                    daemon=True,
                )
                self._threads[task_id] = active
                active.start()
        if wait:
            active.join()
        return self.get_task(task_id)

    def list_tasks(self, *, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM portfolio_tasks ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self.get_task(str(row["task_id"])) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM portfolio_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            return {"task_id": task_id, "status": "not_found"}
        universe = _load(row["universe_json"])
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "config": _load(row["config_json"]),
            "universe": universe,
            "universe_count": len(universe),
            "summary": _load(row["summary_json"]),
            "run_id": row["run_id"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }

    def _execute_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        config = dict(task.get("config") or {})
        universe = list(task.get("universe") or [])
        started_at = _utc_now()
        run_id = f"{task_id}-shared-portfolio"
        self._set_running(task_id, run_id, started_at)
        self._runtime_store.upsert_backtest_run(
            run_id=run_id,
            strategy_name=str(config.get("name") or config.get("strategy_id")),
            strategy_id=str(config.get("strategy_id") or ""),
            status="running",
            benchmark=str(config.get("benchmark") or ""),
            universe=f"shared:{len(universe)} A-shares",
            start_date=str(config["date_window"]["start_date"]),
            end_date=str(config["date_window"]["end_date"]),
            created_at=started_at,
            completed_at=None,
            parameters=dict(config.get("parameters") or {}),
            extra_config=config,
            raw_result={},
        )
        try:
            strategy = self._strategy_service.resolve_version(
                str(config["strategy_id"]), str(config["strategy_version"])
            )
            prepared, excluded = self._prepare_symbols(universe, config, strategy)
            if not prepared:
                raise RuntimeError("no symbols have usable local bars and strategy signals")
            raw_result, metrics = _run_shared_account(prepared, config, strategy, excluded)
            finished_at = _utc_now()
            self._persist_result(run_id, config, raw_result, metrics, started_at, finished_at)
            status = "completed" if not excluded else "partial_completed"
            summary = {
                "run_id": run_id,
                "statistics_scope": "single_shared_account",
                "requested_symbol_count": len(universe),
                "executed_symbol_count": len(prepared),
                "excluded_symbol_count": len(excluded),
                "excluded_symbols": excluded[:100],
                "metrics": metrics,
                "trade_count": len(raw_result["trades"]),
                "account_points": len(raw_result["accounts"]),
                "final_holdings": raw_result.get("final_holdings", []),
            }
            with self._connect() as connection:
                connection.execute(
                    """UPDATE portfolio_tasks SET status=?, summary_json=?, updated_at=?,
                       finished_at=?, error_message=NULL WHERE task_id=?""",
                    (status, _dump(summary), finished_at, finished_at, task_id),
                )
        except Exception as exc:
            finished_at = _utc_now()
            message = f"{type(exc).__name__}: {exc}"
            self._runtime_store.upsert_backtest_run(
                run_id=run_id,
                strategy_name=str(config.get("name") or config.get("strategy_id")),
                strategy_id=str(config.get("strategy_id") or ""),
                status="failed",
                benchmark=str(config.get("benchmark") or ""),
                universe=f"shared:{len(universe)} A-shares",
                start_date=str(config["date_window"]["start_date"]),
                end_date=str(config["date_window"]["end_date"]),
                created_at=started_at,
                completed_at=finished_at,
                parameters=dict(config.get("parameters") or {}),
                extra_config=config,
                raw_result={},
                error_message=message,
            )
            with self._connect() as connection:
                connection.execute(
                    "UPDATE portfolio_tasks SET status='failed', error_message=?, updated_at=?, finished_at=? WHERE task_id=?",
                    (message, finished_at, finished_at, task_id),
                )

    def _prepare_symbols(
        self, universe: list[dict[str, Any]], config: dict[str, Any], strategy: dict[str, Any]
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
        prepared: dict[str, dict[str, Any]] = {}
        excluded: list[dict[str, str]] = []

        def prepare(item: dict[str, Any]) -> tuple[str, dict[str, Any] | None, str | None]:
            symbol = str(item["symbol"])
            try:
                rows = self._market_data_service.get_a_share_price_history(
                    symbol=symbol,
                    adjustment=str(config.get("adjustment") or "raw"),
                    start_date=str(config["date_window"]["start_date"]),
                    end_date=str(config["date_window"]["end_date"]),
                )
                if len(rows) < 2:
                    raise RuntimeError("not enough local bars")
                weights = execute_target_weights(
                    str(strategy.get("source_code") or ""),
                    rows,
                    dict(config.get("parameters") or {}),
                    timeout_seconds=10.0,
                )
                return symbol, {"meta": item, "rows": rows, "weights": weights}, None
            except Exception as exc:
                return symbol, None, f"{type(exc).__name__}: {exc}"

        workers = max(1, min(int(config.get("max_workers") or 4), 16, len(universe)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="portfolio-prepare") as executor:
            futures = [executor.submit(prepare, item) for item in universe]
            for future in as_completed(futures):
                symbol, payload, error = future.result()
                if payload is None:
                    excluded.append({"symbol": symbol, "reason": str(error)})
                else:
                    prepared[symbol] = payload
        return prepared, sorted(excluded, key=lambda row: row["symbol"])

    def _persist_result(
        self,
        run_id: str,
        config: dict[str, Any],
        raw_result: dict[str, Any],
        metrics: dict[str, Any],
        started_at: str,
        finished_at: str,
    ) -> None:
        self._runtime_store.upsert_backtest_run(
            run_id=run_id,
            strategy_name=str(config.get("name") or config.get("strategy_id")),
            strategy_id=str(config.get("strategy_id") or ""),
            status="completed",
            benchmark=str(config.get("benchmark") or ""),
            universe=f"shared:{raw_result['executed_symbol_count']} A-shares",
            start_date=str(config["date_window"]["start_date"]),
            end_date=str(config["date_window"]["end_date"]),
            created_at=started_at,
            completed_at=finished_at,
            parameters=dict(config.get("parameters") or {}),
            extra_config={
                **config,
                "portfolio_mode": "shared_cash",
                "rqalpha_local": {
                    "commission_rate": config["commission_rate"],
                    "min_commission": config["min_commission"],
                    "tax_rate": config["tax_rate"],
                    "slippage_rate": config["slippage_rate"],
                },
                "data_asset_trace": raw_result["data_asset_trace"],
            },
            raw_result=raw_result,
        )
        self._runtime_store.replace_backtest_metrics(run_id=run_id, metrics=metrics)
        self._runtime_store.replace_backtest_logs(run_id=run_id, rows=raw_result["logs"])
        self._runtime_store.replace_backtest_trades(run_id=run_id, rows=raw_result["trades"])
        self._runtime_store.replace_backtest_positions(run_id=run_id, rows=raw_result["positions"])
        self._runtime_store.replace_backtest_accounts(run_id=run_id, rows=raw_result["accounts"])
        self._runtime_store.replace_backtest_yearly_returns(run_id=run_id, rows=raw_result["yearly_returns"])

    def _freeze_universe(self, *, symbols: list[str], market: str, limit: int) -> list[dict[str, Any]]:
        requested = {_symbol_code(item) for item in symbols if str(item).strip()}
        collected: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._market_data_service.list_a_share_symbols(market=market, limit=500, offset=offset)
            items = list(page.get("items") or [])
            for item in items:
                code = _symbol_code(item.get("symbol"))
                if str(item.get("listing_status") or "") != "current":
                    continue
                if requested and code not in requested:
                    continue
                collected.append({
                    "symbol": code,
                    "rqalpha_symbol": str(item.get("rqalpha_symbol") or code),
                    "name": str(item.get("name") or code),
                    "market": str(item.get("market") or ""),
                })
                if limit > 0 and len(collected) >= limit:
                    return collected
            offset += len(items)
            if not items or offset >= int(page.get("total") or 0):
                break
        return collected

    def _set_running(self, task_id: str, run_id: str, now: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE portfolio_tasks SET status='running', run_id=?, error_message=NULL,
                   started_at=COALESCE(started_at, ?), updated_at=? WHERE task_id=?""",
                (run_id, now, now, task_id),
            )

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS portfolio_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    universe_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    run_id TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )"""
            )

    def _recover_interrupted_tasks(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE portfolio_tasks SET status='interrupted', updated_at=? WHERE status='running'",
                (_utc_now(),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _run_shared_account(
    prepared: dict[str, dict[str, Any]],
    config: dict[str, Any],
    strategy: dict[str, Any],
    excluded: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
    weight_by_symbol: dict[str, dict[str, float]] = {}
    all_dates: set[str] = set()
    for symbol, payload in prepared.items():
        by_symbol[symbol] = {}
        weight_by_symbol[symbol] = {}
        for row, weight in zip(payload["rows"], payload["weights"]):
            date = str(row.get("date") or "")[:10]
            if date:
                by_symbol[symbol][date] = dict(row)
                weight_by_symbol[symbol][date] = float(weight)
                all_dates.add(date)
    dates = sorted(all_dates)
    if len(dates) < 2:
        raise RuntimeError("portfolio calendar has fewer than two trading dates")

    initial_cash = float(config["initial_cash"])
    cash = initial_cash
    quantities = {symbol: 0 for symbol in prepared}
    available = {symbol: 0 for symbol in prepared}
    last_prices: dict[str, float] = {}
    previous_closes: dict[str, float] = {}
    trades: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    accounts: list[dict[str, Any]] = []
    curve: list[tuple[str, float]] = []
    rejected_orders = 0

    for date in dates:
        available = dict(quantities)
        rows_today: dict[str, dict[str, Any]] = {}
        for symbol in prepared:
            row = by_symbol[symbol].get(date)
            if row is not None and float(row.get("close") or 0) > 0:
                rows_today[symbol] = row
                last_prices[symbol] = float(row["close"])
        total_before = cash + sum(quantities[s] * last_prices.get(s, 0.0) for s in prepared)
        signals = {
            symbol: weight_by_symbol[symbol][date]
            for symbol in rows_today
            if weight_by_symbol[symbol].get(date, 0.0) > 0
        }
        selected = sorted(signals, key=lambda symbol: (-signals[symbol], symbol))[: int(config["max_positions"])]
        signal_total = sum(signals[symbol] for symbol in selected)
        target_weights = {
            symbol: float(config["portfolio_exposure"]) * signals[symbol] / signal_total
            for symbol in selected
        } if signal_total else {}
        targets: dict[str, int] = {}
        for symbol in prepared:
            price = last_prices.get(symbol, 0.0)
            targets[symbol] = (
                math.floor(total_before * target_weights.get(symbol, 0.0) / price / 100) * 100
                if price > 0 and symbol in rows_today else quantities[symbol]
            )

        for symbol in sorted(prepared):
            sell_quantity = min(max(quantities[symbol] - targets[symbol], 0), available[symbol])
            row = rows_today.get(symbol)
            if sell_quantity < 100 or row is None:
                continue
            close = float(row["close"])
            if _at_price_limit(symbol, str(prepared[symbol]["meta"].get("name") or ""), close, previous_closes.get(symbol), up=False):
                rejected_orders += 1
                continue
            execution_price = close * (1.0 - float(config["slippage_rate"]))
            amount = sell_quantity * execution_price
            commission = max(amount * float(config["commission_rate"]), float(config["min_commission"]))
            tax = amount * float(config["tax_rate"])
            cash += amount - commission - tax
            quantities[symbol] -= sell_quantity
            available[symbol] -= sell_quantity
            trades.append(_trade(date, symbol, "SELL", execution_price, sell_quantity, amount, commission, tax, target_weights.get(symbol, 0.0)))

        for symbol in selected:
            buy_quantity = max(targets[symbol] - quantities[symbol], 0)
            row = rows_today.get(symbol)
            if buy_quantity < 100 or row is None:
                continue
            close = float(row["close"])
            if _at_price_limit(symbol, str(prepared[symbol]["meta"].get("name") or ""), close, previous_closes.get(symbol), up=True):
                rejected_orders += 1
                continue
            execution_price = close * (1.0 + float(config["slippage_rate"]))
            buy_quantity = _affordable_quantity(
                buy_quantity, cash, execution_price, float(config["commission_rate"]), float(config["min_commission"])
            )
            if buy_quantity < 100:
                continue
            amount = buy_quantity * execution_price
            commission = max(amount * float(config["commission_rate"]), float(config["min_commission"]))
            cash -= amount + commission
            quantities[symbol] += buy_quantity
            trades.append(_trade(date, symbol, "BUY", execution_price, buy_quantity, amount, commission, 0.0, target_weights.get(symbol, 0.0)))

        market_value = sum(quantities[s] * last_prices.get(s, 0.0) for s in prepared)
        total_value = cash + market_value
        snapshot_time = f"{date}T15:00:00+08:00"
        for symbol in sorted(prepared):
            quantity = quantities[symbol]
            if quantity <= 0:
                continue
            value = quantity * last_prices.get(symbol, 0.0)
            positions.append({
                "snapshot_time": snapshot_time,
                "order_book_id": str(prepared[symbol]["meta"].get("rqalpha_symbol") or symbol),
                "quantity": quantity,
                "market_value": round(value, 6),
                "notes": {"symbol": symbol, "weight": value / total_value if total_value else 0.0, "settlement": "T+1"},
            })
        accounts.append({
            "snapshot_time": snapshot_time,
            "total_value": round(total_value, 6),
            "market_value": round(market_value, 6),
            "cash": round(cash, 6),
            "unit_net_value": round(total_value / initial_cash, 8),
            "notes": {"holding_count": sum(quantity > 0 for quantity in quantities.values()), "mode": "shared_cash_portfolio"},
        })
        curve.append((date, total_value))
        for symbol, row in rows_today.items():
            previous_closes[symbol] = float(row["close"])

    metrics = _build_metrics(curve, initial_cash)
    metrics.update({
        "trade_count": len(trades),
        "executed_symbol_count": len(prepared),
        "excluded_symbol_count": len(excluded),
        "rejected_order_count": rejected_orders,
        "max_positions": int(config["max_positions"]),
    })
    final_holdings = [
        {"symbol": symbol, "quantity": quantity, "market_value": round(quantity * last_prices.get(symbol, 0.0), 6)}
        for symbol, quantity in sorted(quantities.items()) if quantity > 0
    ]
    raw_result = {
        "engine": "shared_cash_portfolio_runtime",
        "data_source": "canonical_a_share_sqlite",
        "mode": "shared_cash_portfolio",
        "executed_symbol_count": len(prepared),
        "excluded_symbols": excluded,
        "strategy_binding": {
            "strategy_id": strategy.get("strategy_id"),
            "strategy_version": strategy.get("latest_version"),
            "source_sha256": strategy.get("source_sha256"),
            "execution_contract": strategy.get("execution_contract"),
        },
        "execution_rules": {
            "shared_cash": True,
            "t_plus_one": True,
            "lot_size": 100,
            "sell_before_buy": True,
            "suspension": "missing_bar_no_trade_last_close_valuation",
            "price_limit": "5/10/20/30_percent_approximation",
        },
        "data_asset_trace": {
            "status": "bound",
            "source": "canonical_a_share_sqlite",
            "adjustment": config.get("adjustment"),
            "symbol_count": len(prepared),
            "start_date": config["date_window"]["start_date"],
            "end_date": config["date_window"]["end_date"],
        },
        "logs": [{
            "recorded_at": f"{dates[-1]}T15:00:00+08:00",
            "level": "INFO",
            "stage": "shared_cash_portfolio_runtime",
            "message": f"completed shared account with {len(prepared)} symbols, {len(trades)} trades and {len(curve)} account points",
        }],
        "trades": trades,
        "positions": positions,
        "accounts": accounts,
        "yearly_returns": _yearly_returns(curve),
        "final_holdings": final_holdings,
    }
    return raw_result, metrics


def _trade(date: str, symbol: str, side: str, price: float, quantity: int, amount: float, commission: float, tax: float, target_weight: float) -> dict[str, Any]:
    return {
        "trade_time": f"{date}T15:00:00+08:00",
        "order_book_id": symbol,
        "side": side,
        "price": round(price, 6),
        "quantity": quantity,
        "amount": round(amount, 6),
        "commission": round(commission, 6),
        "tax": round(tax, 6),
        "notes": {"target_weight": target_weight, "mode": "shared_cash_portfolio"},
    }


def _affordable_quantity(requested: int, cash: float, price: float, rate: float, minimum: float) -> int:
    quantity = min(requested, math.floor(cash / max(price * (1.0 + rate), 0.000001) / 100) * 100)
    while quantity >= 100:
        amount = quantity * price
        if amount + max(amount * rate, minimum) <= cash + 1e-9:
            return quantity
        quantity -= 100
    return 0


def _at_price_limit(symbol: str, name: str, close: float, previous: float | None, *, up: bool) -> bool:
    if previous is None or previous <= 0:
        return False
    code = _symbol_code(symbol)
    if "ST" in name.upper():
        rate = 0.05
    elif code.startswith(("300", "301", "688")):
        rate = 0.20
    elif code.startswith(("4", "8", "92")):
        rate = 0.30
    else:
        rate = 0.10
    threshold = previous * (1.0 + rate if up else 1.0 - rate)
    return close >= threshold - 0.001 if up else close <= threshold + 0.001


def _build_metrics(curve: list[tuple[str, float]], initial_cash: float) -> dict[str, float]:
    final_value = curve[-1][1]
    total_return = final_value / initial_cash - 1.0
    returns = [current / previous - 1.0 for (_, previous), (_, current) in zip(curve, curve[1:]) if previous]
    peak = curve[0][1]
    max_drawdown = 0.0
    for _, value in curve:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0 if peak else 0.0)
    volatility = statistics.pstdev(returns) if returns else 0.0
    sharpe = statistics.mean(returns) / volatility * math.sqrt(252) if volatility else 0.0
    annualized = (1.0 + total_return) ** (252.0 / max(len(curve), 1)) - 1.0 if total_return > -1 else -1.0
    return {
        "total_returns": round(total_return, 6),
        "annualized_returns": round(annualized, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(sharpe, 6),
        "final_value": round(final_value, 4),
    }


def _yearly_returns(curve: list[tuple[str, float]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    for date, value in curve:
        grouped.setdefault(date[:4], []).append(value)
    return [{
        "year": year,
        "portfolio_return": round(values[-1] / values[0] - 1.0, 6) if values[0] else 0.0,
        "benchmark_return": 0.0,
        "excess_return": round(values[-1] / values[0] - 1.0, 6) if values[0] else 0.0,
    } for year, values in sorted(grouped.items())]


def _normalize_id(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character in "-_" else "-" for character in value.strip())
    if not normalized:
        raise ValueError("task_id is required")
    return normalized


def _symbol_code(value: Any) -> str:
    return str(value or "").strip().split(".")[0].zfill(6)


def _bounded(value: Any, minimum: float, maximum: float) -> float:
    return min(max(float(value), minimum), maximum)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load(value: str) -> Any:
    return json.loads(value or "{}")
