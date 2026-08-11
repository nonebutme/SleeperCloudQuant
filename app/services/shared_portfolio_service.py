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

from backtest_kernel.strategy_execution import execute_strategy_evidence


class SharedPortfolioService:
    """Run one frozen A-share universe through a single simulated account."""

    def __init__(
        self,
        market_data_service: Any,
        strategy_service: Any,
        runtime_store: Any,
        database_path: str | Path = "var/runtime/shared_portfolio.sqlite3",
        dataset_resolver: Any | None = None,
    ) -> None:
        self._market_data_service = market_data_service
        self._strategy_service = strategy_service
        self._runtime_store = runtime_store
        self._dataset_resolver = dataset_resolver
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
        data_version_binding = {"status": "unsupported"}
        if hasattr(self._market_data_service, "get_published_data_version"):
            data_version_binding = dict(self._market_data_service.get_published_data_version(
                symbol=str(universe[0]["symbol"]),
                adjustment=adjustment,
                start_date=start_date,
                end_date=end_date,
                benchmark=benchmark,
            ))
            if data_version_binding.get("status") == "data_not_ready":
                raise ValueError(
                    f"data_not_ready:{data_version_binding.get('reason') or 'published_version_unavailable'}"
                )
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
            "rebalance": "daily_open_sell_then_buy" if str(parameters.get("execution_price") or "close").lower() == "open" else "daily_close_sell_then_buy",
            "universe_source": "canonical_a_share_sqlite",
            "data_version_binding": data_version_binding,
        }
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO portfolio_tasks (
                    task_id, status, config_json, universe_json, summary_json, progress_json,
                    run_id, error_message, created_at, updated_at, started_at, finished_at
                ) VALUES (?, 'ready', ?, ?, '{}', ?, NULL, NULL, ?, ?, NULL, NULL)""",
                (
                    normalized_task_id,
                    _dump(config),
                    _dump(universe),
                    _dump({"phase": "ready", "processed": 0, "total": len(universe), "percent": 0.0}),
                    now,
                    now,
                ),
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
                "SELECT task_id FROM portfolio_tasks WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self.get_task(str(row["task_id"])) for row in rows]

    def delete_task(self, task_id: str, *, reason: str = "用户从 Web 工作台删除") -> dict[str, Any]:
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return task
        if task.get("deleted_at"):
            return task
        if task.get("status") in {"pending", "running", "pause_requested", "cancel_requested"}:
            raise ValueError("running task must be canceled before deletion")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE portfolio_tasks SET deleted_at=?, deleted_reason=?, updated_at=? WHERE task_id=?",
                (now, str(reason or "用户从 Web 工作台删除")[:500], now, task_id),
            )
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM portfolio_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            return {"task_id": task_id, "status": "not_found"}
        universe = _load(row["universe_json"])
        progress = dict(_load(row["progress_json"]) or {})
        total = len(universe)
        processed = min(max(int(progress.get("processed") or 0), 0), total)
        elapsed = _elapsed_seconds(row["started_at"], row["finished_at"])
        throughput = processed / elapsed * 60.0 if elapsed > 0 else 0.0
        remaining = max(total - processed, 0)
        calculated_percent = round(processed / total * 90.0, 2) if total else 0.0
        progress.update({
            "processed": processed,
            "total": total,
            "percent": float(progress.get("percent", calculated_percent)),
            "elapsed_seconds": round(elapsed, 2),
            "throughput_per_minute": round(throughput, 2),
            "estimated_remaining_seconds": round(remaining / (throughput / 60.0), 2) if throughput > 0 and remaining else None,
        })
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "config": _load(row["config_json"]),
            "universe": universe,
            "universe_count": len(universe),
            "progress": progress,
            "summary": _load(row["summary_json"]),
            "run_id": row["run_id"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "deleted_at": row["deleted_at"],
            "deleted_reason": row["deleted_reason"],
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
            prepared, excluded = self._prepare_symbols(task_id, universe, config, strategy)
            if not prepared:
                raise RuntimeError("no symbols have usable local bars and strategy signals")
            self._update_progress(
                task_id,
                phase="simulating_account",
                processed=len(universe),
                total=len(universe),
                prepared=len(prepared),
                excluded=len(excluded),
            )
            benchmark_rows: list[dict[str, Any]] = []
            if config.get("benchmark"):
                try:
                    benchmark_rows = self._market_data_service.get_a_share_price_history(
                        symbol=str(config.get("benchmark") or ""),
                        adjustment=str(config.get("adjustment") or "raw"),
                        start_date=str(config["date_window"]["start_date"]),
                        end_date=str(config["date_window"]["end_date"]),
                    )
                except Exception:
                    benchmark_rows = []
            raw_result, metrics = _run_shared_account(
                prepared,
                config,
                strategy,
                excluded,
                benchmark_rows=benchmark_rows,
            )
            binding = dict(config.get("data_version_binding") or {})
            if binding.get("status") == "bound":
                raw_result["data_asset_trace"] = {
                    "status": "bound",
                    "source": "canonical_a_share_sqlite",
                    "symbol": f"shared:{len(prepared)} A-shares",
                    "start_date": config["date_window"]["start_date"],
                    "end_date": config["date_window"]["end_date"],
                    "bound_at": started_at,
                    "asset": {
                        **binding,
                        "symbol": f"shared:{len(prepared)} A-shares",
                        "symbol_count": len(prepared),
                    },
                    "manifest": {
                        "scope": "published_canonical_a_share_release",
                        "members": binding.get("members") or [],
                        "quality_report_id": binding.get("quality_report_id"),
                    },
                }
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
                "trade_count": int(metrics.get("trade_count") or 0),
                "trade_fill_count": len(raw_result["trades"]),
                "account_points": len(raw_result["accounts"]),
                "final_holdings": raw_result.get("final_holdings", []),
            }
            with self._connect() as connection:
                connection.execute(
                    """UPDATE portfolio_tasks SET status=?, summary_json=?, updated_at=?,
                       finished_at=?, error_message=NULL WHERE task_id=?""",
                    (status, _dump(summary), finished_at, finished_at, task_id),
                )
            self._update_progress(
                task_id,
                phase="completed",
                processed=len(universe),
                total=len(universe),
                prepared=len(prepared),
                excluded=len(excluded),
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
        self, task_id: str, universe: list[dict[str, Any]], config: dict[str, Any], strategy: dict[str, Any]
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
                for row in rows:
                    row.setdefault("symbol", symbol)
                    row.setdefault("name", str(item.get("name") or ""))
                    row.setdefault("listing_status", str(item.get("listing_status") or ""))
                    row.setdefault("trade_date", str(row.get("date") or "")[:10])
                if len(rows) < 2:
                    raise RuntimeError("not enough local bars")
                dataset_evidence: list[dict[str, Any]] = []
                if self._dataset_resolver is not None:
                    resolved = self._dataset_resolver(
                        str(strategy.get("source_code") or ""), rows, dict(config.get("parameters") or {})
                    )
                    rows = [dict(row) for row in resolved.get("bars") or rows]
                    dataset_evidence = [dict(item) for item in resolved.get("evidence") or []]
                strategy_evidence = execute_strategy_evidence(
                    str(strategy.get("source_code") or ""),
                    rows,
                    dict(config.get("parameters") or {}),
                    timeout_seconds=10.0,
                )
                return symbol, {
                    "meta": item,
                    "rows": rows,
                    "weights": list(strategy_evidence["weights"]),
                    "scores": strategy_evidence.get("raw_scores"),
                    "dataset_evidence": dataset_evidence,
                }, None
            except Exception as exc:
                return symbol, None, f"{type(exc).__name__}: {exc}"

        workers = max(1, min(int(config.get("max_workers") or 4), 16, len(universe)))
        processed = 0
        update_interval = max(1, min(25, len(universe) // 200 or 1))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="portfolio-prepare") as executor:
            futures = [executor.submit(prepare, item) for item in universe]
            for future in as_completed(futures):
                symbol, payload, error = future.result()
                if payload is None:
                    excluded.append({"symbol": symbol, "reason": str(error)})
                else:
                    prepared[symbol] = payload
                processed += 1
                if processed % update_interval == 0 or processed == len(universe):
                    self._update_progress(
                        task_id,
                        phase="preparing_symbols",
                        processed=processed,
                        total=len(universe),
                        prepared=len(prepared),
                        excluded=len(excluded),
                    )
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
        if hasattr(self._runtime_store, "save_backtest_input_snapshot"):
            self._runtime_store.save_backtest_input_snapshot(
                run_id=run_id,
                data_asset_trace=raw_result.get("data_asset_trace") or {},
            )

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
        task = self.get_task(task_id)
        total = int(task.get("universe_count") or 0)
        with self._connect() as connection:
            connection.execute(
                """UPDATE portfolio_tasks SET status='running', run_id=?, error_message=NULL,
                   progress_json=?, started_at=?, finished_at=NULL, updated_at=? WHERE task_id=?""",
                (
                    run_id,
                    _dump({"phase": "preparing_symbols", "processed": 0, "total": total, "percent": 0.0}),
                    now,
                    now,
                    task_id,
                ),
            )

    def _update_progress(
        self,
        task_id: str,
        *,
        phase: str,
        processed: int,
        total: int,
        prepared: int,
        excluded: int,
    ) -> None:
        stock_percent = int(processed) / int(total) * 90.0 if total else 0.0
        overall_percent = 100.0 if phase == "completed" else (95.0 if phase == "simulating_account" else stock_percent)
        progress = {
            "phase": phase,
            "processed": int(processed),
            "total": int(total),
            "percent": round(overall_percent, 2),
            "prepared": int(prepared),
            "excluded": int(excluded),
        }
        with self._connect() as connection:
            connection.execute(
                "UPDATE portfolio_tasks SET progress_json=?, updated_at=? WHERE task_id=?",
                (_dump(progress), _utc_now(), task_id),
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
                    progress_json TEXT NOT NULL DEFAULT '{}',
                    run_id TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    deleted_at TEXT,
                    deleted_reason TEXT
                )"""
            )
            columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(portfolio_tasks)").fetchall()}
            if "progress_json" not in columns:
                connection.execute("ALTER TABLE portfolio_tasks ADD COLUMN progress_json TEXT NOT NULL DEFAULT '{}'")
            if "deleted_at" not in columns:
                connection.execute("ALTER TABLE portfolio_tasks ADD COLUMN deleted_at TEXT")
            if "deleted_reason" not in columns:
                connection.execute("ALTER TABLE portfolio_tasks ADD COLUMN deleted_reason TEXT")

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
    benchmark_rows: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
    weight_by_symbol: dict[str, dict[str, float]] = {}
    score_by_symbol: dict[str, dict[str, float | None]] = {}
    all_dates: set[str] = set()
    for symbol, payload in prepared.items():
        by_symbol[symbol] = {}
        weight_by_symbol[symbol] = {}
        score_by_symbol[symbol] = {}
        scores = payload.get("scores") or [None] * len(payload["rows"])
        for row, weight, score in zip(payload["rows"], payload["weights"], scores):
            date = str(row.get("date") or "")[:10]
            if date:
                by_symbol[symbol][date] = dict(row)
                weight_by_symbol[symbol][date] = float(weight)
                score_by_symbol[symbol][date] = float(score) if score is not None else None
                all_dates.add(date)
    dates = sorted(all_dates)
    if len(dates) < 2:
        raise RuntimeError("portfolio calendar has fewer than two trading dates")

    initial_cash = float(config["initial_cash"])
    cash = initial_cash
    quantities = {symbol: 0 for symbol in prepared}
    available = {symbol: 0 for symbol in prepared}
    average_costs = {symbol: 0.0 for symbol in prepared}
    last_prices: dict[str, float] = {}
    previous_closes: dict[str, float] = {}
    trades: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    accounts: list[dict[str, Any]] = []
    curve: list[tuple[str, float]] = []
    rejected_orders = 0
    execution_mode = "open" if str((config.get("parameters") or {}).get("execution_price") or "close").lower() == "open" else "close"

    for date in dates:
        available = dict(quantities)
        rows_today: dict[str, dict[str, Any]] = {}
        for symbol in prepared:
            row = by_symbol[symbol].get(date)
            if row is not None and float(row.get("close") or 0) > 0:
                rows_today[symbol] = row
                last_prices[symbol] = float(row["close"])
        execution_prices = {
            symbol: float(row.get("open") or row["close"]) if execution_mode == "open" else float(row["close"])
            for symbol, row in rows_today.items()
        }
        total_before = cash + sum(quantities[s] * execution_prices.get(s, last_prices.get(s, 0.0)) for s in prepared)
        signals = {
            symbol: weight_by_symbol[symbol][date]
            for symbol in rows_today
            if weight_by_symbol[symbol].get(date, 0.0) > 0
        }
        selected = sorted(
            signals,
            key=lambda symbol: (
                -(score_by_symbol[symbol].get(date) if score_by_symbol[symbol].get(date) is not None else signals[symbol]),
                symbol,
            ),
        )[: int(config["max_positions"])]
        signal_total = sum(signals[symbol] for symbol in selected)
        target_weights = {
            symbol: float(config["portfolio_exposure"]) * signals[symbol] / signal_total
            for symbol in selected
        } if signal_total else {}
        targets: dict[str, int] = {}
        for symbol in prepared:
            price = execution_prices.get(symbol, last_prices.get(symbol, 0.0))
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
            reference_price = execution_prices[symbol]
            if _at_price_limit(symbol, str(prepared[symbol]["meta"].get("name") or ""), reference_price, previous_closes.get(symbol), up=False):
                rejected_orders += 1
                continue
            execution_price = reference_price * (1.0 - float(config["slippage_rate"]))
            amount = sell_quantity * execution_price
            commission = max(amount * float(config["commission_rate"]), float(config["min_commission"]))
            tax = amount * float(config["tax_rate"])
            realized_pnl = amount - commission - tax - sell_quantity * average_costs[symbol]
            cash += amount - commission - tax
            quantities[symbol] -= sell_quantity
            available[symbol] -= sell_quantity
            trades.append(_trade(date, symbol, "SELL", execution_price, sell_quantity, amount, commission, tax, target_weights.get(symbol, 0.0), realized_pnl=realized_pnl, market_vwap=_market_vwap(row, close), market_volume=_positive_float(row.get("volume")), execution_mode=execution_mode, raw_signal_score=score_by_symbol[symbol].get(date)))
            if quantities[symbol] == 0:
                average_costs[symbol] = 0.0

        for symbol in selected:
            buy_quantity = max(targets[symbol] - quantities[symbol], 0)
            row = rows_today.get(symbol)
            if buy_quantity < 100 or row is None:
                continue
            close = float(row["close"])
            reference_price = execution_prices[symbol]
            if _at_price_limit(symbol, str(prepared[symbol]["meta"].get("name") or ""), reference_price, previous_closes.get(symbol), up=True):
                rejected_orders += 1
                continue
            execution_price = reference_price * (1.0 + float(config["slippage_rate"]))
            buy_quantity = _affordable_quantity(
                buy_quantity, cash, execution_price, float(config["commission_rate"]), float(config["min_commission"])
            )
            if buy_quantity < 100:
                continue
            amount = buy_quantity * execution_price
            commission = max(amount * float(config["commission_rate"]), float(config["min_commission"]))
            previous_quantity = quantities[symbol]
            average_costs[symbol] = (previous_quantity * average_costs[symbol] + amount + commission) / (previous_quantity + buy_quantity)
            cash -= amount + commission
            quantities[symbol] += buy_quantity
            trades.append(_trade(date, symbol, "BUY", execution_price, buy_quantity, amount, commission, 0.0, target_weights.get(symbol, 0.0), market_vwap=_market_vwap(row, close), market_volume=_positive_float(row.get("volume")), execution_mode=execution_mode, raw_signal_score=score_by_symbol[symbol].get(date)))

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
                "avg_price": round(average_costs[symbol], 6),
                "price": round(last_prices.get(symbol, 0.0), 6),
                "unrealized_pnl": round(value - quantity * average_costs[symbol], 6),
                "weight": value / total_value if total_value else 0.0,
                "notes": {"symbol": symbol, "weight": value / total_value if total_value else 0.0, "settlement": "T+1"},
            })
        accounts.append({
            "snapshot_time": snapshot_time,
            "total_value": round(total_value, 6),
            "market_value": round(market_value, 6),
            "cash": round(cash, 6),
            "unit_net_value": round(total_value / initial_cash, 8),
            "daily_return": round(total_value / (curve[-1][1] if curve else initial_cash) - 1.0, 8),
            "notes": {"holding_count": sum(quantity > 0 for quantity in quantities.values()), "mode": "shared_cash_portfolio"},
        })
        curve.append((date, total_value))
        for symbol, row in rows_today.items():
            previous_closes[symbol] = float(row["close"])

    benchmark_curve = _align_benchmark_curve(dates, benchmark_rows or [])
    metrics = _build_metrics(curve, initial_cash, benchmark_curve=benchmark_curve)
    realized = [float(row["pnl"]) for row in trades if row.get("pnl") is not None]
    wins = [value for value in realized if value > 0]
    losses = [value for value in realized if value < 0]
    metrics.update({
        "trade_count": len(realized),
        "trade_fill_count": len(trades),
        "win_rate": len(wins) / len(realized) if realized else None,
        "profit_loss_ratio": statistics.mean(wins) / abs(statistics.mean(losses)) if wins and losses else None,
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
            "score_contract": "point_in_time_raw_score_v1" if any(payload.get("scores") is not None for payload in prepared.values()) else "unavailable_generate_signal_scores_missing",
            "datasets": _dataset_evidence(prepared),
        },
        "execution_rules": {
            "shared_cash": True,
            "t_plus_one": True,
            "lot_size": 100,
            "sell_before_buy": True,
            "suspension": "missing_bar_no_trade_last_close_valuation",
            "price_limit": "5/10/20/30_percent_approximation",
            "execution_price": execution_mode,
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
        "yearly_returns": _yearly_returns(curve, initial_cash, benchmark_curve),
        "benchmark_curve": _normalized_curve(benchmark_curve),
        "excess_curve": _excess_curve(curve, initial_cash, benchmark_curve),
        "benchmark_status": "ready" if benchmark_curve else "unavailable",
        "final_holdings": final_holdings,
    }
    return raw_result, metrics


def _dataset_evidence(prepared: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for payload in prepared.values():
        for item in payload.get("dataset_evidence") or []:
            dataset_id = str(item.get("dataset_id") or "")
            if dataset_id and dataset_id not in by_id:
                by_id[dataset_id] = dict(item)
    return [by_id[key] for key in sorted(by_id)]

def _trade(date: str, symbol: str, side: str, price: float, quantity: int, amount: float, commission: float, tax: float, target_weight: float, *, realized_pnl: float | None = None, market_vwap: float | None = None, market_volume: float | None = None, execution_mode: str = "close", raw_signal_score: float | None = None) -> dict[str, Any]:
    return {
        "trade_time": f"{date}T{'09:30:00' if execution_mode == 'open' else '15:00:00'}+08:00",
        "order_book_id": symbol,
        "side": side,
        "price": round(price, 6),
        "quantity": quantity,
        "amount": round(amount, 6),
        "commission": round(commission, 6),
        "tax": round(tax, 6),
        "pnl": round(realized_pnl, 6) if realized_pnl is not None else None,
        "notes": {
            "target_weight": target_weight,
            "mode": "shared_cash_portfolio",
            "market_vwap": market_vwap,
            "market_volume": market_volume,
            "execution_price_mode": execution_mode,
            "raw_signal_score": raw_signal_score,
        },
    }


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _market_vwap(row: dict[str, Any], close: float) -> float | None:
    amount = _positive_float(row.get("amount"))
    volume = _positive_float(row.get("volume"))
    if amount is None or volume is None or close <= 0:
        return None
    for divisor in (1.0, 100.0):
        candidate = amount / volume / divisor
        if close * 0.2 <= candidate <= close * 5.0:
            return round(candidate, 6)
    return None


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


def _build_metrics(
    curve: list[tuple[str, float]],
    initial_cash: float,
    *,
    benchmark_curve: list[tuple[str, float]],
    risk_free_rate: float = 0.0,
) -> dict[str, float | None]:
    portfolio = _performance_metrics([initial_cash, *[value for _, value in curve]], risk_free_rate=risk_free_rate)
    metrics: dict[str, float | None] = {
        "total_returns": portfolio["total_return"],
        "annualized_returns": portfolio["annualized_return"],
        "max_drawdown": portfolio["max_drawdown"],
        "sharpe": portfolio["sharpe"],
        "volatility": portfolio["volatility"],
        "calmar": portfolio["calmar"],
        "final_value": round(curve[-1][1], 4),
        "risk_free_rate": risk_free_rate,
    }
    excess_points = _excess_curve(curve, initial_cash, benchmark_curve)
    if benchmark_curve and excess_points:
        benchmark = _performance_metrics([value for _, value in benchmark_curve], risk_free_rate=risk_free_rate)
        excess = _performance_metrics([point["value"] for point in excess_points], risk_free_rate=0.0)
        portfolio_returns = _period_returns([value for _, value in curve])
        benchmark_returns = _period_returns([value for _, value in benchmark_curve])
        paired = min(len(portfolio_returns), len(benchmark_returns))
        active_returns = [portfolio_returns[index] - benchmark_returns[index] for index in range(paired)]
        tracking_error = statistics.pstdev(active_returns) * math.sqrt(252) if active_returns else None
        information_ratio = (
            statistics.mean(active_returns) / statistics.pstdev(active_returns) * math.sqrt(252)
            if len(active_returns) > 1 and statistics.pstdev(active_returns) else None
        )
        metrics.update({
            "benchmark_return": benchmark["total_return"],
            "benchmark_annualized_return": benchmark["annualized_return"],
            "excess_return": excess["total_return"],
            "excess_annualized_return": excess["annualized_return"],
            "excess_max_drawdown": excess["max_drawdown"],
            "tracking_error": round(tracking_error, 6) if tracking_error is not None else None,
            "information_ratio": round(information_ratio, 6) if information_ratio is not None else None,
        })
    return metrics


def _performance_metrics(values: list[float], *, risk_free_rate: float) -> dict[str, float]:
    returns = _period_returns(values)
    total_return = values[-1] / values[0] - 1.0 if values and values[0] else 0.0
    periods = max(len(values) - 1, 1)
    annualized = (1.0 + total_return) ** (252.0 / periods) - 1.0 if total_return > -1 else -1.0
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1.0 if peak else 0.0)
    volatility = statistics.pstdev(returns) * math.sqrt(252) if returns else 0.0
    daily_risk_free = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
    daily_volatility = statistics.pstdev(returns) if returns else 0.0
    sharpe = (statistics.mean(returns) - daily_risk_free) / daily_volatility * math.sqrt(252) if daily_volatility else 0.0
    calmar = annualized / abs(max_drawdown) if max_drawdown else None
    return {
        "total_return": round(total_return, 6),
        "annualized_return": round(annualized, 6),
        "max_drawdown": round(max_drawdown, 6),
        "sharpe": round(sharpe, 6),
        "volatility": round(volatility, 6),
        "calmar": round(calmar, 6) if calmar is not None else None,
    }


def _period_returns(values: list[float]) -> list[float]:
    return [current / previous - 1.0 for previous, current in zip(values, values[1:]) if previous]


def _align_benchmark_curve(dates: list[str], rows: list[dict[str, Any]]) -> list[tuple[str, float]]:
    prices = {str(row.get("date") or row.get("trade_date") or "")[:10]: float(row.get("close") or 0.0) for row in rows if float(row.get("close") or 0.0) > 0}
    aligned: list[tuple[str, float]] = []
    last_price: float | None = None
    for date in dates:
        if date in prices:
            last_price = prices[date]
        if last_price is not None:
            aligned.append((date, last_price))
    return aligned if len(aligned) == len(dates) and len(aligned) >= 2 else []


def _normalized_curve(curve: list[tuple[str, float]]) -> list[dict[str, Any]]:
    if not curve or not curve[0][1]:
        return []
    base = curve[0][1]
    return [{"date": date, "value": round(value / base, 8)} for date, value in curve]


def _excess_curve(curve: list[tuple[str, float]], initial_cash: float, benchmark_curve: list[tuple[str, float]]) -> list[dict[str, Any]]:
    if not benchmark_curve or len(benchmark_curve) != len(curve) or not benchmark_curve[0][1]:
        return []
    benchmark_base = benchmark_curve[0][1]
    portfolio_base = curve[0][1]
    return [{
        "date": date,
        "value": round((portfolio_value / portfolio_base) / (benchmark_value / benchmark_base), 8),
    } for (date, portfolio_value), (_, benchmark_value) in zip(curve, benchmark_curve)]


def _yearly_returns(
    curve: list[tuple[str, float]],
    initial_cash: float,
    benchmark_curve: list[tuple[str, float]],
) -> list[dict[str, Any]]:
    benchmark_by_date = dict(benchmark_curve)
    rows: list[dict[str, Any]] = []
    previous_portfolio = curve[0][1] if benchmark_curve else initial_cash
    previous_benchmark = benchmark_curve[0][1] if benchmark_curve else None
    grouped: dict[str, list[tuple[str, float]]] = {}
    for date, value in curve:
        grouped.setdefault(date[:4], []).append((date, value))
    for year, values in sorted(grouped.items()):
        portfolio_return = values[-1][1] / previous_portfolio - 1.0 if previous_portfolio else None
        benchmark_return = None
        if previous_benchmark is not None:
            year_benchmark = [benchmark_by_date[date] for date, _ in values if date in benchmark_by_date]
            if year_benchmark:
                benchmark_return = year_benchmark[-1] / previous_benchmark - 1.0
                previous_benchmark = year_benchmark[-1]
        rows.append({
        "year": year,
            "portfolio_return": round(portfolio_return, 6) if portfolio_return is not None else None,
            "benchmark_return": round(benchmark_return, 6) if benchmark_return is not None else None,
            "excess_return": round(portfolio_return - benchmark_return, 6) if portfolio_return is not None and benchmark_return is not None else None,
        })
        previous_portfolio = values[-1][1]
    return rows


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


def _elapsed_seconds(started_at: str | None, finished_at: str | None) -> float:
    if not started_at:
        return 0.0
    try:
        start = datetime.fromisoformat(str(started_at))
        end = datetime.fromisoformat(str(finished_at)) if finished_at else datetime.now(timezone.utc)
        return max((end - start).total_seconds(), 0.0)
    except ValueError:
        return 0.0


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load(value: str) -> Any:
    return json.loads(value or "{}")
