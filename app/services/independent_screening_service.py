"""Independent-capital concurrent stock screening backtests."""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from domain.backtest import BacktestRunRequest


class IndependentScreeningService:
    """Freeze one A-share universe and backtest each symbol independently."""

    def __init__(
        self,
        backtest_service: Any,
        market_data_service: Any,
        strategy_service: Any,
        runtime_store: Any,
        database_path: str | Path = "var/runtime/independent_screening.sqlite3",
    ) -> None:
        self._backtest_service = backtest_service
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
    def list_tasks(self, *, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM screening_tasks ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self.get_task(str(row["task_id"])) for row in rows]

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
                    finished_at TEXT
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
