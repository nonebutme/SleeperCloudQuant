"""Persistent asynchronous task wrapper for one-symbol backtests."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from domain.backtest import BacktestRunRequest


class SingleBacktestTaskService:
    """Manage one-symbol backtests with the same task lifecycle used by batch modes."""

    def __init__(
        self,
        backtest_service: Any,
        database_path: str | Path = "var/runtime/single_backtest_tasks.sqlite3",
    ) -> None:
        self._backtest_service = backtest_service
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()
        self._ensure_schema()
        self._recover_interrupted_tasks()

    def create_task(self, **config: Any) -> dict[str, Any]:
        if str(config["start_date"]) > str(config["end_date"]):
            raise ValueError("start_date must not be after end_date")
        task_id = _normalize_id(str(config.get("task_id") or f"single-{uuid4().hex[:12]}"))
        run_id = str(config.get("run_id") or f"{task_id}-run")
        now = _utc_now()
        normalized = {
            "mode": "single",
            "name": str(config.get("name") or f"{config.get('strategy_name') or config.get('strategy_id')} · {config.get('symbol')}"),
            "run_id": run_id,
            "strategy_name": str(config.get("strategy_name") or config.get("strategy_id") or "strategy"),
            "strategy_id": str(config.get("strategy_id") or config.get("strategy_name") or ""),
            "strategy_version": str(config.get("strategy_version") or "v1"),
            "symbol": str(config.get("symbol") or ""),
            "benchmark": str(config.get("benchmark") or "000300.XSHG"),
            "date_window": {"start_date": str(config["start_date"]), "end_date": str(config["end_date"])},
            "initial_cash": float(config.get("initial_cash") or 1_000_000),
            "frequency": str(config.get("frequency") or "1d"),
            "parameters": dict(config.get("parameters") or {}),
            "extra_config": dict(config.get("extra_config") or {}),
            "adjustment": str(config.get("adjustment") or config.get("extra_config", {}).get("adjustment") or "qfq"),
        }
        if not normalized["symbol"]:
            raise ValueError("symbol is required")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO single_backtest_tasks (
                    task_id, status, config_json, run_id, result_json, error_message,
                    created_at, updated_at, started_at, finished_at, deleted_at, deleted_reason
                ) VALUES (?, 'ready', ?, ?, '{}', NULL, ?, ?, NULL, NULL, NULL, NULL)""",
                (task_id, _dump(normalized), run_id, now, now),
            )
        return self.get_task(task_id)

    def start_task(self, task_id: str, *, wait: bool = False) -> dict[str, Any]:
        task = self.get_task(task_id)
        if task.get("status") in {"not_found", "running", "completed"}:
            return task
        with self._lock:
            active = self._threads.get(task_id)
            if active is None or not active.is_alive():
                active = threading.Thread(
                    target=self._execute_task,
                    args=(task_id,),
                    name=f"single-backtest-{task_id}",
                    daemon=True,
                )
                self._threads[task_id] = active
                active.start()
        if wait:
            active.join()
        return self.get_task(task_id)

    def list_tasks(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT task_id FROM single_backtest_tasks WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self.get_task(str(row["task_id"])) for row in rows]

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM single_backtest_tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if row is None:
            return {"task_id": task_id, "status": "not_found"}
        config = _load(row["config_json"])
        status = str(row["status"])
        progress = {
            "phase": "completed" if status == "completed" else "failed" if status == "failed" else status,
            "processed": 1 if status in {"completed", "failed"} else 0,
            "total": 1,
            "percent": 100.0 if status in {"completed", "failed"} else 15.0 if status == "running" else 0.0,
            "elapsed_seconds": _elapsed_seconds(row["started_at"], row["finished_at"]),
        }
        return {
            "task_id": row["task_id"],
            "status": status,
            "config": config,
            "run_id": row["run_id"],
            "result": _load(row["result_json"]),
            "error_message": row["error_message"],
            "progress": progress,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "deleted_at": row["deleted_at"],
            "deleted_reason": row["deleted_reason"],
        }

    def delete_task(self, task_id: str, *, reason: str = "用户从统一任务工作台删除") -> dict[str, Any]:
        task = self.get_task(task_id)
        if task.get("status") == "not_found":
            return task
        if task.get("status") == "running":
            raise ValueError("running single task cannot be deleted")
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE single_backtest_tasks SET deleted_at=?, deleted_reason=?, updated_at=? WHERE task_id=?",
                (now, str(reason)[:500], now, task_id),
            )
        return self.get_task(task_id)

    def _execute_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        config = dict(task.get("config") or {})
        started_at = _utc_now()
        self._update(task_id, status="running", started_at=started_at, finished_at=None, error_message=None)
        try:
            extra_config = dict(config.get("extra_config") or {})
            extra_config.update(
                {
                    "mode": "single",
                    "single_task_id": task_id,
                    "strategy_id": config.get("strategy_id"),
                    "strategy_version": config.get("strategy_version"),
                    "adjustment": config.get("adjustment"),
                }
            )
            result = self._backtest_service.run_once(
                BacktestRunRequest(
                    run_id=str(config["run_id"]),
                    strategy_name=str(config["strategy_name"]),
                    symbol=str(config["symbol"]),
                    benchmark=str(config["benchmark"]),
                    start_date=str(config["date_window"]["start_date"]),
                    end_date=str(config["date_window"]["end_date"]),
                    initial_cash=float(config["initial_cash"]),
                    frequency=str(config["frequency"]),
                    parameters=dict(config.get("parameters") or {}),
                    extra_config=extra_config,
                    strategy_id=str(config.get("strategy_id") or ""),
                    strategy_version=str(config.get("strategy_version") or ""),
                )
            )
            payload = {
                "run_id": result.run_id,
                "strategy_name": result.strategy_name,
                "status": getattr(result.status, "value", str(result.status)),
                "metrics": dict(result.metrics or {}),
            }
            self._update(
                task_id,
                status="completed",
                result_json=_dump(payload),
                finished_at=_utc_now(),
                error_message=None,
            )
        except Exception as error:  # noqa: BLE001 - task boundary records execution failures
            self._update(
                task_id,
                status="failed",
                finished_at=_utc_now(),
                error_message=str(error)[:2000],
            )

    def _recover_interrupted_tasks(self) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                "UPDATE single_backtest_tasks SET status='interrupted', updated_at=?, finished_at=? WHERE status='running'",
                (now, now),
            )

    def _update(self, task_id: str, **values: Any) -> None:
        if not values:
            return
        values["updated_at"] = _utc_now()
        columns = ", ".join(f"{key}=?" for key in values)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE single_backtest_tasks SET {columns} WHERE task_id=?",  # noqa: S608 - fixed internal keys
                (*values.values(), task_id),
            )

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS single_backtest_tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    deleted_at TEXT,
                    deleted_reason TEXT
                )"""
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _normalize_id(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value.strip())
    if not normalized:
        raise ValueError("task_id is empty after normalization")
    return normalized[:120]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None) -> dict[str, Any]:
    return json.loads(value or "{}")


def _elapsed_seconds(started_at: str | None, finished_at: str | None) -> float:
    if not started_at:
        return 0.0
    try:
        start = datetime.fromisoformat(started_at)
        finish = datetime.fromisoformat(finished_at) if finished_at else datetime.now(timezone.utc)
        return round(max((finish - start).total_seconds(), 0.0), 2)
    except ValueError:
        return 0.0
