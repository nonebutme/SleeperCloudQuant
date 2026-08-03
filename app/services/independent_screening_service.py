"""Independent-capital concurrent stock screening backtests."""

from __future__ import annotations

import itertools
import json
import math
import os
import sqlite3
import statistics
import threading
from array import array
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from domain.backtest import BacktestRunRequest
from app.services.cross_section_context import (
    build_industry_analysis as _build_industry_analysis,
    build_signal_market_regimes as _build_signal_market_regimes,
    index_industry_intervals as _index_industry_intervals,
    industry_cross_section as _industry_cross_section,
)


class IndependentScreeningService:
    """Freeze one A-share universe and backtest each symbol independently."""

    def __init__(
        self,
        backtest_service: Any,
        market_data_service: Any,
        strategy_service: Any,
        runtime_store: Any,
        database_path: str | Path = "var/runtime/independent_screening.sqlite3",
        classification_store: Any | None = None,
    ) -> None:
        self._backtest_service = backtest_service
        self._market_data_service = market_data_service
        self._strategy_service = strategy_service
        self._runtime_store = runtime_store
        self._classifications = classification_store
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, threading.Thread] = {}
        self._signal_analysis_cache: dict[str, tuple[str, dict[str, Any]]] = {}
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
        retry_count: int,
        symbol_limit: int,
        scheduler_batch_size: int = 0,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        if adjustment not in {"raw", "qfq", "hfq"}:
            raise ValueError("adjustment must be raw, qfq, or hfq")
        strategy = self._strategy_service.resolve_version(strategy_id, strategy_version)
        universe = self._freeze_universe(symbols=symbols or [], market=market, limit=symbol_limit)
        if not universe:
            raise ValueError("selected A-share universe is empty")
        normalized_task_id = _normalize_id(task_id or f"screen-{uuid4().hex[:12]}")
        now = _utc_now()
        config = {
            "mode": "independent_screening",
            "name": name.strip() or normalized_task_id,
            "strategy_id": strategy["strategy_id"],
            "strategy_version": strategy["latest_version"],
            "source_sha256": strategy["source_sha256"],
            "execution_contract": strategy["execution_contract"],
            "market": market.upper(),
            "date_window": {"start_date": start_date, "end_date": end_date},
            "adjustment": adjustment,
            "benchmark": benchmark,
            "initial_cash_per_symbol": float(initial_cash),
            "parameters": dict(parameters),
            "max_workers": max(0, min(int(max_workers), 32)),
            "retry_count": max(0, min(int(retry_count), 3)),
            "scheduler_batch_size": max(0, min(int(scheduler_batch_size), 256)),
            "universe_source": "canonical_a_share_sqlite",
            "entry_definition": "at_least_one_effective_buy_trade",
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO screening_tasks (
                    task_id, status, config_json, summary_json, universe_count,
                    created_at, updated_at, started_at, finished_at
                ) VALUES (?, 'ready', ?, '{}', ?, ?, ?, NULL, NULL)
                """,
                (normalized_task_id, _dump(config), len(universe), now, now),
            )
            connection.executemany(
                """
                INSERT INTO screening_items (
                    task_id, symbol, rqalpha_symbol, name, market, status,
                    entered, attempt_count, run_id, metrics_json, error_message,
                    started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', 0, 0, NULL, '{}', NULL, NULL, NULL)
                """,
                [
                    (
                        normalized_task_id,
                        item["symbol"],
                        item["rqalpha_symbol"],
                        item["name"],
                        item["market"],
                    )
                    for item in universe
                ],
            )
        return self.get_task(normalized_task_id)

    def start_task(self, task_id: str, *, wait: bool = False) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return task
        if task.get("status") in {"completed", "canceled"}:
            return task
        with self._lock:
            active = self._threads.get(task_id)
            if active is None or not active.is_alive():
                thread = threading.Thread(
                    target=self._execute_task,
                    args=(task_id,),
                    name=f"screening-{task_id}",
                    daemon=True,
                )
                self._threads[task_id] = thread
                thread.start()
                active = thread
        if wait:
            active.join()
        return self.get_task(task_id)

    def control_task(self, task_id: str, action: str) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if normalized not in {"pause", "resume", "cancel"}:
            raise ValueError("action must be pause, resume, or cancel")
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return task
        if normalized == "resume":
            return self.start_task(task_id)
        status = str(task.get("status") or "")
        if status in {"completed", "canceled"}:
            return task
        requested_status = "pause_requested" if normalized == "pause" else "cancel_requested"
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE screening_tasks SET status=?, updated_at=? WHERE task_id=?",
                (requested_status, now, task_id),
            )
        active = self._threads.get(task_id)
        if active is None or not active.is_alive():
            if normalized == "pause":
                self._set_task_status(task_id, "paused")
            else:
                self._cancel_remaining(task_id)
        return self.get_task(task_id)

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
                "UPDATE screening_tasks SET deleted_at=?, deleted_reason=?, updated_at=? WHERE task_id=?",
                (now, str(reason or "用户从 Web 工作台删除")[:500], now, task_id),
            )
        return self.get_task(task_id)

    def list_tasks(self, *, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM screening_tasks WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self.get_task(str(row["task_id"])) for row in rows]

    def get_task_version(self, task_id: str) -> str:
        """Return a lightweight cache version without aggregating task items."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT updated_at FROM screening_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return str(row["updated_at"] or "") if row is not None else ""
    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM screening_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                return {"task_id": task_id, "status": "not_found"}
            counts = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status='canceled' THEN 1 ELSE 0 END) AS canceled,
                    SUM(CASE WHEN status IN ('pending','running','interrupted') THEN 1 ELSE 0 END) AS remaining,
                    SUM(CASE WHEN entered=1 THEN 1 ELSE 0 END) AS entered,
                    SUM(CASE WHEN status='completed' AND entered=0 THEN 1 ELSE 0 END) AS no_entry
                FROM screening_items WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        processed = (
            int(counts["completed"] or 0)
            + int(counts["failed"] or 0)
            + int(counts["canceled"] or 0)
        )
        total = int(counts["total"] or 0)
        remaining = int(counts["remaining"] or 0)
        config = _load(row["config_json"])
        effective_workers = _resolve_workers(config.get("max_workers"), total)
        return {
            "task_id": row["task_id"],
            "status": row["status"],
            "config": config,
            "summary": _load(row["summary_json"]),
            "progress": {
                "total": total,
                "processed": processed,
                "completed": int(counts["completed"] or 0),
                "entered": int(counts["entered"] or 0),
                "no_entry": int(counts["no_entry"] or 0),
                "failed": int(counts["failed"] or 0),
                "canceled": int(counts["canceled"] or 0),
                "remaining": remaining,
                "percent": round(processed / total * 100, 4) if total else 0.0,
                **_progress_telemetry(
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                    processed=processed,
                    remaining=remaining,
                ),
            },
            "execution": {
                "scheduler": "bounded_dynamic_batches",
                "requested_workers": int(config.get("max_workers") or 0),
                "effective_workers": effective_workers,
                "batch_size": _resolve_batch_size(
                    config.get("scheduler_batch_size"), effective_workers, total
                ),
            },
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "deleted_at": row["deleted_at"],
            "deleted_reason": row["deleted_reason"],
        }
    def list_items(
        self,
        task_id: str,
        *,
        entered_only: bool = False,
        status: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        filters = ["task_id = ?"]
        values: list[Any] = [task_id]
        if entered_only:
            filters.append("entered = 1")
        if status:
            filters.append("status = ?")
            values.append(status)
        where = " AND ".join(filters)
        page_limit = max(1, min(int(limit), 500))
        page_offset = max(0, int(offset))
        with self._connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM screening_items WHERE {where}", values).fetchone()[0])
            rows = connection.execute(
                f"""SELECT * FROM screening_items WHERE {where}
                    ORDER BY entered DESC, symbol LIMIT ? OFFSET ?""",
                (*values, page_limit, page_offset),
            ).fetchall()
        return {
            "task_id": task_id,
            "total": total,
            "limit": page_limit,
            "offset": page_offset,
            "items": [self._item_payload(row) for row in rows],
        }

    def build_signal_analysis(self, task_id: str) -> dict[str, Any]:
        """Build point-in-time strategy-exposure IC evidence from persisted runs."""
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return _unavailable_signal_analysis("task_not_found")
        persisted = dict(task.get("summary") or {}).get("signal_analysis")
        if isinstance(persisted, dict) and persisted.get("version") == "strategy-exposure-cross-section-v2":
            return dict(persisted)
        cache_version = str(task.get("updated_at") or "")
        cached = self._signal_analysis_cache.get(task_id)
        if cached is not None and cached[0] == cache_version:
            return dict(cached[1])
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM screening_items WHERE task_id=? AND status='completed' ORDER BY symbol",
                (task_id,),
            ).fetchall()
        items = [self._item_payload(row) for row in rows]
        config = dict(task.get("config") or {})
        date_window = dict(config.get("date_window") or {})
        adjustment = str(config.get("adjustment") or "raw")
        cross_sections: dict[str, tuple[array[float], array[float], list[str]]] = {}
        active_signal_counts: dict[str, int] = {}
        symbols_with_signal: set[str] = set()
        price_row_count = 0

        def append_symbol_observations(
            symbol: str,
            snapshots: Any,
        ) -> None:
            nonlocal price_row_count
            position_by_date: dict[str, float] = {}
            account_by_date: dict[str, float] = {}
            for row in snapshots:
                date = str(row.get("snapshot_time") or "")[:10]
                if not date:
                    continue
                position_by_date[date] = float(
                    row.get("position_market_value", row.get("market_value")) or 0.0
                )
                account_by_date[date] = float(row.get("total_value") or 0.0)
            prices = self._read_analysis_prices(
                symbol=symbol,
                adjustment=adjustment,
                start_date=str(date_window.get("start_date") or "") or None,
                end_date=str(date_window.get("end_date") or "") or None,
            )
            price_row_count += len(prices)
            for index in range(len(prices) - 1):
                current = prices[index]
                following = prices[index + 1]
                date = str(current.get("date") or "")[:10]
                current_close = _optional_number(current.get("close"))
                next_close = _optional_number(following.get("close"))
                capital = account_by_date.get(date)
                if not date or current_close is None or next_close is None or current_close <= 0 or not capital:
                    continue
                exposure = max(0.0, position_by_date.get(date, 0.0) / capital)
                future_return = next_close / current_close - 1.0
                signals, outcomes, section_symbols = cross_sections.setdefault(
                    date,
                    (array("d"), array("d"), []),
                )
                signals.append(exposure)
                outcomes.append(future_return)
                section_symbols.append(symbol)
                if exposure > 1e-12:
                    symbols_with_signal.add(symbol)
                    active_signal_counts[date] = active_signal_counts.get(date, 0) + 1

        bulk_reader = getattr(self._runtime_store, "iter_backtest_exposure_snapshots", None)
        if callable(bulk_reader):
            symbol_by_run_id = {
                str(item.get("run_id") or ""): str(item.get("symbol") or "")
                for item in items
                if item.get("run_id") and item.get("symbol")
            }
            snapshots = bulk_reader(f"{task_id}-")
            for run_id, run_snapshots in itertools.groupby(
                snapshots,
                key=lambda row: str(row.get("run_id") or ""),
            ):
                symbol = symbol_by_run_id.get(run_id)
                if symbol:
                    append_symbol_observations(symbol, run_snapshots)
        else:
            for item in items:
                run_id = str(item.get("run_id") or "")
                symbol = str(item.get("symbol") or "")
                if not run_id or not symbol:
                    continue
                positions = list(self._runtime_store.fetch_backtest_positions(run_id))
                accounts = list(self._runtime_store.fetch_backtest_accounts(run_id))
                position_by_date = {
                    str(row.get("snapshot_time") or "")[:10]: float(row.get("market_value") or 0.0)
                    for row in positions
                    if str(row.get("snapshot_time") or "")[:10]
                }
                append_symbol_observations(
                    symbol,
                    (
                        {
                            **row,
                            "position_market_value": position_by_date.get(
                                str(row.get("snapshot_time") or "")[:10],
                                0.0,
                            ),
                        }
                        for row in accounts
                    ),
                )
        interval_reader = getattr(self._classifications, "fetch_intervals", None)
        industry_intervals = (
            _index_industry_intervals(interval_reader([item.get("symbol") for item in items], dimension="industry"))
            if callable(interval_reader)
            else {}
        )
        ic_rows: list[dict[str, Any]] = []
        layered_daily: list[dict[str, Any]] = []
        industry_daily: dict[str, list[float]] = {}
        industry_neutral_rows: list[dict[str, Any]] = []
        for date in sorted(cross_sections):
            signals, outcomes, section_symbols = cross_sections[date]
            section_size = len(signals)
            if section_size >= 3 and _has_variation(signals) and _has_variation(outcomes):
                ic = _pearson(signals, outcomes)
                rank_ic = _spearman_values(signals, outcomes)
                if ic is not None and rank_ic is not None:
                    ic_rows.append({
                        "date": date,
                        "ic": ic,
                        "rank_ic": rank_ic,
                        "sample_size": section_size,
                        "market_return": statistics.mean(outcomes),
                    })
            industry_result = _industry_cross_section(
                date=date,
                signals=signals,
                outcomes=outcomes,
                symbols=section_symbols,
                interval_index=industry_intervals,
            )
            for industry, value in industry_result["industry_ic"].items():
                industry_daily.setdefault(industry, []).append(value)
            if industry_result.get("neutral_ic") is not None:
                industry_neutral_rows.append({
                    "date": date,
                    "ic": industry_result["neutral_ic"],
                    "sample_size": industry_result["neutral_sample_size"],
                })
            if section_size >= 5 and _has_variation(signals):
                ordered_indices = sorted(
                    range(section_size),
                    key=lambda index: (-signals[index], index),
                )
                groups: list[list[float]] = [[] for _ in range(5)]
                for rank, source_index in enumerate(ordered_indices):
                    group_index = min(4, rank * 5 // section_size)
                    groups[group_index].append(outcomes[source_index])
                if all(groups):
                    group_returns = [statistics.mean(group) for group in groups]
                    layered_daily.append({
                        "date": date,
                        **{f"q{index + 1}": value for index, value in enumerate(group_returns)},
                        "long_short": group_returns[0] - group_returns[4],
                        "sample_size": section_size,
                    })
        analysis = _build_signal_analysis_payload(
            task_id=task_id,
            universe_count=len(items),
            price_row_count=price_row_count,
            ic_rows=ic_rows,
            layered_daily=layered_daily,
            active_signal_counts=active_signal_counts,
            symbols_with_signal=symbols_with_signal,
            observation_period_count=len(cross_sections),
            industry_daily=industry_daily,
            industry_neutral_rows=industry_neutral_rows,
        )
        self._signal_analysis_cache[task_id] = (cache_version, dict(analysis))
        return analysis

    def persist_signal_analysis(self, task_id: str) -> dict[str, Any]:
        """Build and persist report evidence for a completed historical task."""
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return _unavailable_signal_analysis("task_not_found")
        if task.get("status") not in {"completed", "partial_failed"}:
            return _unavailable_signal_analysis("task_not_finished")
        analysis = self.build_signal_analysis(task_id)
        summary = dict(task.get("summary") or {})
        summary["signal_analysis"] = analysis
        with self._connect() as connection:
            connection.execute(
                "UPDATE screening_tasks SET summary_json=? WHERE task_id=?",
                (_dump(summary), task_id),
            )
        cache_version = str(task.get("updated_at") or "")
        self._signal_analysis_cache[task_id] = (cache_version, dict(analysis))
        return analysis

    def _read_analysis_prices(
        self,
        *,
        symbol: str,
        adjustment: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._market_data_service.get_a_share_daily_prices(
                symbol=symbol,
                adjustment=adjustment,
                start_date=start_date,
                end_date=end_date,
                limit=2000,
                offset=offset,
            )
            batch = list(page.get("rows") or [])
            rows.extend(dict(row) for row in batch)
            offset += len(batch)
            if not batch or offset >= int(page.get("total") or 0):
                break
        return sorted(rows, key=lambda row: str(row.get("date") or ""))
    def _execute_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        config = dict(task.get("config") or {})
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE screening_tasks SET status='running', started_at=COALESCE(started_at, ?), updated_at=? WHERE task_id=?",
                (now, now, task_id),
            )
            rows = connection.execute(
                "SELECT * FROM screening_items WHERE task_id=? AND status IN ('pending','failed','interrupted') ORDER BY symbol",
                (task_id,),
            ).fetchall()
        if not rows:
            self._finalize_task(task_id)
            return
        workers = _resolve_workers(config.get("max_workers"), len(rows))
        batch_size = _resolve_batch_size(
            config.get("scheduler_batch_size"), workers, len(rows)
        )
        with ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix=f"{task_id}-worker"
        ) as executor:
            for offset in range(0, len(rows), batch_size):
                if not self._continue_execution(task_id):
                    return
                batch = rows[offset : offset + batch_size]
                self._mark_items_running(
                    task_id, [str(row["symbol"]) for row in batch]
                )
                futures = [
                    executor.submit(self._run_item, task_id, dict(row), config)
                    for row in batch
                ]
                results = [future.result() for future in as_completed(futures)]
                self._save_item_results(task_id, results)
                if not self._continue_execution(task_id):
                    return
        self._finalize_task(task_id)
    def _run_item(self, task_id: str, item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        symbol = str(item["rqalpha_symbol"] or item["symbol"])
        run_id = f"{task_id}-{item['symbol']}"
        retry_count = int(config.get("retry_count") or 0)
        last_error = ""
        for attempt in range(1, retry_count + 2):
            try:
                request = BacktestRunRequest(
                    run_id=run_id,
                    strategy_name=str(config.get("name") or config.get("strategy_id")),
                    symbol=symbol,
                    benchmark=str(config.get("benchmark") or "000300.XSHG"),
                    start_date=str(config["date_window"]["start_date"]),
                    end_date=str(config["date_window"]["end_date"]),
                    initial_cash=float(config.get("initial_cash_per_symbol") or 1_000_000),
                    parameters={**dict(config.get("parameters") or {}), "adjustment": config.get("adjustment", "raw")},
                    extra_config={
                        "screening_task_id": task_id,
                        "screening_mode": "independent_capital",
                        "strategy_id": config.get("strategy_id"),
                        "strategy_version": config.get("strategy_version"),
                        "source_sha256": config.get("source_sha256"),
                    },
                    strategy_id=str(config.get("strategy_id") or ""),
                    strategy_version=str(config.get("strategy_version") or "v1"),
                )
                result = self._backtest_service.run_once(request)
                trades = list(self._runtime_store.fetch_backtest_trades(run_id))
                entered = any(
                    str(trade.get("side") or "").upper() == "BUY"
                    and float(trade.get("quantity") or 0) > 0
                    for trade in trades
                )
                return {
                    "symbol": item["symbol"],
                    "status": "completed",
                    "entered": entered,
                    "attempt_count": attempt,
                    "run_id": run_id,
                    "metrics": dict(result.metrics),
                    "error_message": None,
                }
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
        return {
            "symbol": item["symbol"],
            "status": "failed",
            "entered": False,
            "attempt_count": retry_count + 1,
            "run_id": run_id,
            "metrics": {},
            "error_message": last_error,
        }

    def _save_item_results(self, task_id: str, results: list[dict[str, Any]]) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.executemany(
                """
                UPDATE screening_items SET status=?, entered=?, attempt_count=?,
                    run_id=?, metrics_json=?, error_message=?, finished_at=?
                WHERE task_id=? AND symbol=?
                """,
                [
                    (
                        result["status"],
                        1 if result["entered"] else 0,
                        result["attempt_count"],
                        result["run_id"],
                        _dump(result["metrics"]),
                        result["error_message"],
                        now,
                        task_id,
                        result["symbol"],
                    )
                    for result in results
                ],
            )
            connection.execute(
                "UPDATE screening_tasks SET updated_at=? WHERE task_id=?",
                (now, task_id),
            )

    def _mark_items_running(self, task_id: str, symbols: list[str]) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.executemany(
                "UPDATE screening_items SET status='running', started_at=COALESCE(started_at, ?) WHERE task_id=? AND symbol=?",
                [(now, task_id, symbol) for symbol in symbols],
            )

    def _continue_execution(self, task_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM screening_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        status = str(row["status"] if row else "not_found")
        if status == "pause_requested":
            self._set_task_status(task_id, "paused")
            return False
        if status == "cancel_requested":
            self._cancel_remaining(task_id)
            return False
        return status == "running"

    def _set_task_status(self, task_id: str, status: str) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE screening_tasks SET status=?, updated_at=? WHERE task_id=?",
                (status, now, task_id),
            )

    def _cancel_remaining(self, task_id: str) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE screening_items SET status='canceled', finished_at=?
                   WHERE task_id=? AND status IN ('pending','running','interrupted','failed')""",
                (now, task_id),
            )
            connection.execute(
                """UPDATE screening_tasks SET status='canceled', updated_at=?,
                   finished_at=? WHERE task_id=?""",
                (now, now, task_id),
            )
    def _finalize_task(self, task_id: str) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM screening_items WHERE task_id=? AND entered=1 ORDER BY symbol",
                (task_id,),
            ).fetchall()
        entered_rows = [self._item_payload(row) for row in rows]
        returns = [value for row in entered_rows if (value := _metric(row, "total_returns")) is not None]
        annualized = [value for row in entered_rows if (value := _metric(row, "annualized_returns")) is not None]
        task = self.get_task(task_id)
        progress = task["progress"]
        ranked = sorted(
            entered_rows,
            key=lambda row: _metric(row, "annualized_returns") if _metric(row, "annualized_returns") is not None else -10**9,
            reverse=True,
        )
        summary = {
            "statistics_scope": "entered_symbols_only",
            "entry_definition": "at_least_one_effective_buy_trade",
            "funnel": dict(progress),
            "performance": {
                "average_total_returns": _mean(returns),
                "median_total_returns": _median(returns),
                "positive_return_ratio": round(sum(value > 0 for value in returns) / len(returns), 6) if returns else None,
                "average_annualized_returns": _mean(annualized),
            },
            "top_entered": ranked[:20],
            "no_entry_excluded_from_performance": True,
        }
        status = "completed" if progress["failed"] == 0 else ("partial_failed" if progress["completed"] else "failed")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE screening_tasks SET status=?, summary_json=?, updated_at=?, finished_at=? WHERE task_id=?",
                (status, _dump(summary), now, now, task_id),
            )
        try:
            summary["signal_analysis"] = self.build_signal_analysis(task_id)
        except Exception as exc:
            summary["signal_analysis"] = _unavailable_signal_analysis(
                f"{type(exc).__name__}: {exc}"
            )
        with self._connect() as connection:
            connection.execute(
                "UPDATE screening_tasks SET summary_json=? WHERE task_id=?",
                (_dump(summary), task_id),
            )

    def _freeze_universe(self, *, symbols: list[str], market: str, limit: int) -> list[dict[str, Any]]:
        requested = {_symbol_code(item) for item in symbols if str(item).strip()}
        collected: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._market_data_service.list_a_share_symbols(
                market=market,
                limit=500,
                offset=offset,
            )
            items = list(page.get("items") or [])
            for item in items:
                code = _symbol_code(item.get("symbol"))
                if str(item.get("listing_status") or "") != "current":
                    continue
                if requested and code not in requested:
                    continue
                collected.append(
                    {
                        "symbol": code,
                        "rqalpha_symbol": str(item.get("rqalpha_symbol") or code),
                        "name": str(item.get("name") or code),
                        "market": str(item.get("market") or ""),
                    }
                )
                if limit > 0 and len(collected) >= limit:
                    return collected
            offset += len(items)
            if not items or offset >= int(page.get("total") or 0):
                break
        return collected

    def _item_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "symbol": row["symbol"],
            "rqalpha_symbol": row["rqalpha_symbol"],
            "name": row["name"],
            "market": row["market"],
            "status": row["status"],
            "entered": bool(row["entered"]),
            "attempt_count": row["attempt_count"],
            "run_id": row["run_id"],
            "metrics": _load(row["metrics_json"]),
            "error_message": row["error_message"],
            "finished_at": row["finished_at"],
        }

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS screening_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    universe_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    deleted_at TEXT,
                    deleted_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS screening_items (
                    task_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    rqalpha_symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entered INTEGER NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    run_id TEXT,
                    metrics_json TEXT NOT NULL,
                    error_message TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    PRIMARY KEY (task_id, symbol)
                );
                CREATE INDEX IF NOT EXISTS idx_screening_items_task_status
                    ON screening_items (task_id, status, entered);
                """
            )

            columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(screening_tasks)").fetchall()}
            if "deleted_at" not in columns:
                connection.execute("ALTER TABLE screening_tasks ADD COLUMN deleted_at TEXT")
            if "deleted_reason" not in columns:
                connection.execute("ALTER TABLE screening_tasks ADD COLUMN deleted_reason TEXT")

    def _recover_interrupted_tasks(self) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """UPDATE screening_items SET status='canceled', finished_at=?
                   WHERE task_id IN (
                       SELECT task_id FROM screening_tasks
                       WHERE status='cancel_requested'
                   ) AND status IN ('pending','running','interrupted','failed')""",
                (now,),
            )
            connection.execute(
                """UPDATE screening_tasks SET status='canceled', updated_at=?,
                   finished_at=? WHERE status='cancel_requested'""",
                (now, now),
            )
            connection.execute(
                "UPDATE screening_tasks SET status='paused', updated_at=? WHERE status='pause_requested'",
                (now,),
            )
            connection.execute(
                "UPDATE screening_tasks SET status='interrupted', updated_at=? WHERE status='running'",
                (now,),
            )
            connection.execute(
                "UPDATE screening_items SET status='interrupted' WHERE status='running'",
            )
    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection


def _unavailable_signal_analysis(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "signal_definition": "end_of_day_position_market_value_divided_by_total_account_value",
        "outcome_definition": "next_trading_day_adjusted_close_return",
        "ic_analysis": {"status": "unavailable", "reason": reason, "series": [], "monthly": []},
        "layered_returns": {"status": "unavailable", "reason": reason, "series": []},
        "signal_summary": {"status": "unavailable", "reason": reason},
    }


def _build_signal_analysis_payload(
    *,
    task_id: str,
    universe_count: int,
    price_row_count: int,
    ic_rows: list[dict[str, Any]],
    layered_daily: list[dict[str, Any]],
    active_signal_counts: dict[str, int],
    symbols_with_signal: set[str],
    observation_period_count: int,
    industry_daily: dict[str, list[float]],
    industry_neutral_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    ic_values = [float(row["ic"]) for row in ic_rows]
    rank_values = [float(row["rank_ic"]) for row in ic_rows]
    cumulative_ic = 0.0
    cumulative_rank_ic = 0.0
    series = []
    for row in ic_rows:
        cumulative_ic += float(row["ic"])
        cumulative_rank_ic += float(row["rank_ic"])
        series.append({**row, "cumulative_ic": cumulative_ic, "cumulative_rank_ic": cumulative_rank_ic})
    monthly_buckets: dict[str, list[dict[str, Any]]] = {}
    for row in ic_rows:
        monthly_buckets.setdefault(str(row["date"])[:7], []).append(row)
    monthly = [
        {
            "month": month,
            "ic": statistics.mean(float(row["ic"]) for row in rows),
            "rank_ic": statistics.mean(float(row["rank_ic"]) for row in rows),
            "period_count": len(rows),
        }
        for month, rows in sorted(monthly_buckets.items())
    ]
    ic_mean = statistics.mean(ic_values) if ic_values else None
    ic_std = statistics.stdev(ic_values) if len(ic_values) > 1 else None
    ic_analysis = {
        "status": "ready" if ic_values else "insufficient_cross_section",
        "signal_name": "策略收盘持仓权重",
        "signal_definition": "当日收盘后持仓市值/账户总资产",
        "outcome_definition": "下一交易日复权收盘收益率",
        "periodicity": "daily",
        "mean": ic_mean,
        "stddev": ic_std,
        "icir": ic_mean / ic_std * math.sqrt(252) if ic_mean is not None and ic_std else None,
        "newey_west_t": _newey_west_t(ic_values),
        "rank_mean": statistics.mean(rank_values) if rank_values else None,
        "rank_stddev": statistics.stdev(rank_values) if len(rank_values) > 1 else None,
        "positive_ratio": sum(value > 0 for value in ic_values) / len(ic_values) if ic_values else None,
        "period_count": len(ic_values),
        "minimum_cross_section_size": min((int(row["sample_size"]) for row in ic_rows), default=0),
        "maximum_cross_section_size": max((int(row["sample_size"]) for row in ic_rows), default=0),
        "series": series,
        "monthly": monthly,
        "methodology": "Pearson IC and Spearman Rank IC; Newey-West HAC t-statistic; daily ICIR annualized by sqrt(252)",
    }
    layered_returns = _build_layered_returns(layered_daily)
    active_counts = [
        int(active_signal_counts[date])
        for date in sorted(active_signal_counts)
    ]
    industry_analysis = _build_industry_analysis(industry_daily, industry_neutral_rows)
    market_regimes = _build_signal_market_regimes(ic_rows, layered_daily)
    signal_summary = {
        "status": "ready" if observation_period_count else "unavailable",
        "total_signal_stock_count": len(symbols_with_signal),
        "average_per_period": sum(active_counts) / observation_period_count if observation_period_count else None,
        "active_period_count": len(active_counts),
        "observation_period_count": observation_period_count,
        "universe_count": universe_count,
        "definition": "signal means end-of-day position weight greater than zero",
    }
    return {
        "status": "ready" if ic_values or layered_daily else "limited",
        "task_id": task_id,
        "version": "strategy-exposure-cross-section-v2",
        "signal_definition": "end_of_day_position_market_value_divided_by_total_account_value",
        "outcome_definition": "next_trading_day_adjusted_close_return",
        "look_ahead_control": "signal observed after close on t; outcome uses adjusted close return from t to next trading day",
        "universe_scope": "all_completed_independent_accounts",
        "price_row_count": price_row_count,
        "ic_analysis": ic_analysis,
        "layered_returns": layered_returns,
        "signal_summary": signal_summary,
        "industry_analysis": industry_analysis,
        "market_regimes": market_regimes,
    }


def _build_layered_returns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "insufficient_universe",
            "reason": "at_least_five_valid_symbols_per_period_required",
            "minimum_cross_section_size": 5,
            "series": [],
        }
    keys = [f"q{index}" for index in range(1, 6)]
    daily = {key: [float(row[key]) for row in rows] for key in keys}
    daily["long_short"] = [float(row["long_short"]) for row in rows]
    nav = {key: 1.0 for key in (*keys, "long_short")}
    series = []
    for row in rows:
        point = {"date": row["date"], "sample_size": row["sample_size"]}
        for key in (*keys, "long_short"):
            nav[key] *= 1.0 + float(row[key])
            point[key] = nav[key]
        series.append(point)
    annualized = {key: _annualize_daily(daily[key]) for key in (*keys, "long_short")}
    group_values = [annualized[key] for key in keys]
    monotonicity = _spearman_values([1.0, 2.0, 3.0, 4.0, 5.0], group_values)
    return {
        "status": "ready",
        "period_count": len(rows),
        "q1_annualized": annualized["q1"],
        "q5_annualized": annualized["q5"],
        "long_short_annualized": annualized["long_short"],
        "group_annualized": [{"group": key.upper(), "annualized_return": annualized[key]} for key in keys],
        "monotonicity": monotonicity,
        "monotonicity_p_value": _exact_spearman_p(group_values),
        "long_short_max_drawdown": _max_drawdown([float(row["long_short"]) for row in series]),
        "series": series,
        "methodology": "equal-count Q1-Q5 by descending strategy exposure; Q1 minus Q5; exact two-sided Spearman permutation p-value",
    }


def _optional_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _has_variation(values: list[float]) -> bool:
    return len(values) > 1 and max(values) - min(values) > 1e-12


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3 or not _has_variation(left) or not _has_variation(right):
        return None
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else None


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor
        while end + 1 < len(order) and values[order[end + 1]] == values[order[cursor]]:
            end += 1
        rank = (cursor + end) / 2.0 + 1.0
        for position in range(cursor, end + 1):
            ranks[order[position]] = rank
        cursor = end + 1
    return ranks


def _spearman_values(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    return _pearson(_average_ranks(left), _average_ranks(right))


def _newey_west_t(values: list[float]) -> float | None:
    count = len(values)
    if count < 3:
        return None
    mean = statistics.mean(values)
    centered = [value - mean for value in values]
    lag = min(count - 1, max(0, int(4 * (count / 100) ** (2 / 9))))
    long_run_variance = sum(value * value for value in centered) / count
    for offset in range(1, lag + 1):
        covariance = sum(centered[index] * centered[index - offset] for index in range(offset, count)) / count
        long_run_variance += 2.0 * (1.0 - offset / (lag + 1.0)) * covariance
    if long_run_variance <= 0:
        return None
    standard_error = math.sqrt(long_run_variance / count)
    return mean / standard_error if standard_error else None


def _annualize_daily(values: list[float]) -> float:
    nav = 1.0
    for value in values:
        nav *= 1.0 + value
    return nav ** (252 / len(values)) - 1.0 if values and nav > 0 else -1.0


def _exact_spearman_p(group_returns: list[float]) -> float | None:
    observed = _spearman_values([1.0, 2.0, 3.0, 4.0, 5.0], group_returns)
    if observed is None:
        return None
    absolute = abs(observed)
    extreme = 0
    total = 0
    for permutation in itertools.permutations(group_returns):
        candidate = _spearman_values([1.0, 2.0, 3.0, 4.0, 5.0], list(permutation))
        if candidate is not None:
            total += 1
            if abs(candidate) >= absolute - 1e-12:
                extreme += 1
    return extreme / total if total else None


def _max_drawdown(nav_values: list[float]) -> float | None:
    if not nav_values:
        return None
    peak = nav_values[0]
    maximum = 0.0
    for value in nav_values:
        peak = max(peak, value)
        drawdown = value / peak - 1.0 if peak else 0.0
        maximum = min(maximum, drawdown)
    return maximum

def _normalize_id(value: str) -> str:
    normalized = "".join(character if character.isalnum() or character in "-_" else "-" for character in value.strip())
    if not normalized:
        raise ValueError("task_id is required")
    return normalized[:80]


def _symbol_code(value: Any) -> str:
    return str(value or "").split(".", 1)[0].zfill(6)


def _metric(row: dict[str, Any], name: str) -> float | None:
    value = dict(row.get("metrics") or {}).get(name)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 8) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 8) if values else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _resolve_workers(requested: Any, total: int) -> int:
    value = int(requested or 0)
    if value <= 0:
        value = max(2, min(8, (os.cpu_count() or 4) // 2))
    return max(1, min(value, 32, total or 1))


def _resolve_batch_size(requested: Any, workers: int, total: int) -> int:
    value = int(requested or 0)
    if value <= 0:
        value = workers * 4
    return max(1, min(value, 256, total or 1))


def _progress_telemetry(
    *,
    started_at: str | None,
    finished_at: str | None,
    processed: int,
    remaining: int,
) -> dict[str, Any]:
    if not started_at:
        return {
            "elapsed_seconds": 0.0,
            "throughput_per_minute": 0.0,
            "estimated_remaining_seconds": None,
        }
    start = datetime.fromisoformat(str(started_at))
    end = (
        datetime.fromisoformat(str(finished_at))
        if finished_at
        else datetime.now(timezone.utc)
    )
    elapsed = max(0.0, (end - start).total_seconds())
    rate_per_second = processed / elapsed if elapsed > 0 and processed > 0 else 0.0
    return {
        "elapsed_seconds": round(elapsed, 3),
        "throughput_per_minute": round(rate_per_second * 60, 3),
        "estimated_remaining_seconds": (
            round(remaining / rate_per_second, 3)
            if rate_per_second > 0 and remaining > 0
            else None
        ),
    }

def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str) -> Any:
    return json.loads(value or "{}")
