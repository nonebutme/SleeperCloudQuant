"""SQLite-backed runtime persistence for formal backtest and reporting data."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from reporting.store_protocols import ReportingStore


class SqliteRuntimeStore(ReportingStore):
    """Persist runtime tasks and reporting data into one local SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    @property
    def database_path(self) -> Path:
        """Return the runtime database path."""

        return self._database_path

    def ensure_schema(self) -> None:
        """Create runtime and reporting tables if they do not exist yet."""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    run_id TEXT PRIMARY KEY,
                    strategy_name TEXT NOT NULL,
                    strategy_id TEXT,
                    status TEXT NOT NULL,
                    benchmark TEXT,
                    universe TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    parameters_json TEXT NOT NULL,
                    extra_config_json TEXT NOT NULL,
                    raw_result_json TEXT NOT NULL,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS backtest_metrics (
                    run_id TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL,
                    metric_text TEXT,
                    PRIMARY KEY (run_id, metric_name)
                );

                CREATE TABLE IF NOT EXISTS backtest_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    recorded_at TEXT,
                    level TEXT,
                    stage TEXT,
                    message TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backtest_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    trade_time TEXT,
                    order_book_id TEXT,
                    side TEXT,
                    price REAL,
                    quantity REAL,
                    amount REAL
                );

                CREATE TABLE IF NOT EXISTS backtest_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    snapshot_time TEXT,
                    order_book_id TEXT,
                    quantity REAL,
                    market_value REAL,
                    notes_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backtest_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    snapshot_time TEXT,
                    total_value REAL,
                    market_value REAL,
                    cash REAL,
                    unit_net_value REAL,
                    notes_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backtest_yearly_returns (
                    run_id TEXT NOT NULL,
                    year TEXT NOT NULL,
                    portfolio_return REAL,
                    benchmark_return REAL,
                    excess_return REAL,
                    PRIMARY KEY (run_id, year)
                );

                CREATE TABLE IF NOT EXISTS research_runs (
                    run_id TEXT PRIMARY KEY,
                    strategy_name TEXT,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    parameters_json TEXT NOT NULL
                );
                """
            )

    def upsert_backtest_run(
        self,
        *,
        run_id: str,
        strategy_name: str,
        status: str,
        benchmark: str | None,
        universe: str | None,
        start_date: str | None,
        end_date: str | None,
        created_at: str,
        completed_at: str | None,
        parameters: Mapping[str, Any],
        extra_config: Mapping[str, Any],
        raw_result: Mapping[str, Any] | None,
        error_message: str | None = None,
        strategy_id: str | None = None,
    ) -> None:
        """Insert or update one backtest run summary row."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO backtest_runs (
                    run_id,
                    strategy_name,
                    strategy_id,
                    status,
                    benchmark,
                    universe,
                    start_date,
                    end_date,
                    created_at,
                    completed_at,
                    parameters_json,
                    extra_config_json,
                    raw_result_json,
                    error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    strategy_name = excluded.strategy_name,
                    strategy_id = excluded.strategy_id,
                    status = excluded.status,
                    benchmark = excluded.benchmark,
                    universe = excluded.universe,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    created_at = excluded.created_at,
                    completed_at = excluded.completed_at,
                    parameters_json = excluded.parameters_json,
                    extra_config_json = excluded.extra_config_json,
                    raw_result_json = excluded.raw_result_json,
                    error_message = excluded.error_message
                """,
                (
                    run_id,
                    strategy_name,
                    strategy_id,
                    status,
                    benchmark,
                    universe,
                    start_date,
                    end_date,
                    created_at,
                    completed_at,
                    self._dump_json(parameters),
                    self._dump_json(extra_config),
                    self._dump_json(raw_result or {}),
                    error_message,
                ),
            )

    def replace_backtest_metrics(
        self,
        *,
        run_id: str,
        metrics: Mapping[str, Any],
    ) -> None:
        """Replace all metric rows for one backtest run."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM backtest_metrics WHERE run_id = ?",
                (run_id,),
            )
            for metric_name, metric_value in metrics.items():
                numeric_value = None
                text_value = None
                if isinstance(metric_value, bool):
                    numeric_value = float(metric_value)
                elif isinstance(metric_value, (int, float)):
                    numeric_value = float(metric_value)
                elif metric_value is not None:
                    text_value = str(metric_value)
                connection.execute(
                    """
                    INSERT INTO backtest_metrics (
                        run_id,
                        metric_name,
                        metric_value,
                        metric_text
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, str(metric_name), numeric_value, text_value),
                )

    def replace_backtest_logs(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Replace log rows for one backtest run."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute("DELETE FROM backtest_logs WHERE run_id = ?", (run_id,))
            for row in rows:
                payload = dict(row)
                connection.execute(
                    """
                    INSERT INTO backtest_logs (
                        run_id,
                        recorded_at,
                        level,
                        stage,
                        message
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        payload.get("recorded_at"),
                        payload.get("level"),
                        payload.get("stage"),
                        str(payload.get("message") or ""),
                    ),
                )

    def replace_backtest_trades(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Replace trade rows for one backtest run."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute("DELETE FROM backtest_trades WHERE run_id = ?", (run_id,))
            for row in rows:
                payload = dict(row)
                connection.execute(
                    """
                    INSERT INTO backtest_trades (
                        run_id,
                        trade_time,
                        order_book_id,
                        side,
                        price,
                        quantity,
                        amount
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        payload.get("trade_time"),
                        payload.get("order_book_id"),
                        payload.get("side"),
                        self._to_optional_float(payload.get("price")),
                        self._to_optional_float(payload.get("quantity")),
                        self._to_optional_float(payload.get("amount")),
                    ),
                )

    def replace_backtest_positions(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Replace position rows for one backtest run."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute("DELETE FROM backtest_positions WHERE run_id = ?", (run_id,))
            for row in rows:
                payload = dict(row)
                connection.execute(
                    """
                    INSERT INTO backtest_positions (
                        run_id,
                        snapshot_time,
                        order_book_id,
                        quantity,
                        market_value,
                        notes_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        payload.get("snapshot_time"),
                        payload.get("order_book_id"),
                        self._to_optional_float(payload.get("quantity")),
                        self._to_optional_float(payload.get("market_value")),
                        self._dump_json(payload.get("notes") or {}),
                    ),
                )

    def replace_backtest_accounts(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Replace account rows for one backtest run."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute("DELETE FROM backtest_accounts WHERE run_id = ?", (run_id,))
            for row in rows:
                payload = dict(row)
                connection.execute(
                    """
                    INSERT INTO backtest_accounts (
                        run_id,
                        snapshot_time,
                        total_value,
                        market_value,
                        cash,
                        unit_net_value,
                        notes_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        payload.get("snapshot_time"),
                        self._to_optional_float(payload.get("total_value")),
                        self._to_optional_float(payload.get("market_value")),
                        self._to_optional_float(payload.get("cash")),
                        self._to_optional_float(payload.get("unit_net_value")),
                        self._dump_json(payload.get("notes") or {}),
                    ),
                )

    def replace_backtest_yearly_returns(
        self,
        *,
        run_id: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        """Replace yearly return rows for one backtest run."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM backtest_yearly_returns WHERE run_id = ?",
                (run_id,),
            )
            for row in rows:
                payload = dict(row)
                connection.execute(
                    """
                    INSERT INTO backtest_yearly_returns (
                        run_id,
                        year,
                        portfolio_return,
                        benchmark_return,
                        excess_return
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        str(payload.get("year") or ""),
                        self._to_optional_float(payload.get("portfolio_return")),
                        self._to_optional_float(payload.get("benchmark_return")),
                        self._to_optional_float(payload.get("excess_return")),
                    ),
                )

    def upsert_research_run(
        self,
        *,
        run_id: str,
        strategy_name: str | None,
        status: str,
        started_at: str,
        finished_at: str | None,
        parameters: Mapping[str, Any],
    ) -> None:
        """Insert or update one research-run/task row."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_runs (
                    run_id,
                    strategy_name,
                    status,
                    started_at,
                    finished_at,
                    parameters_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    strategy_name = excluded.strategy_name,
                    status = excluded.status,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    parameters_json = excluded.parameters_json
                """,
                (
                    run_id,
                    strategy_name,
                    status,
                    started_at,
                    finished_at,
                    self._dump_json(parameters),
                ),
            )

    def fetch_backtest_run(self, run_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM backtest_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "strategy_name": row["strategy_name"],
            "strategy_id": row["strategy_id"],
            "status": row["status"],
            "benchmark": row["benchmark"],
            "universe": row["universe"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "parameters": self._load_json(row["parameters_json"]),
            "extra_config": self._load_json(row["extra_config_json"]),
            "raw_result": self._load_json(row["raw_result_json"]),
            "error_message": row["error_message"],
        }

    def fetch_backtest_metrics(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        return self._fetch_rows(
            """
            SELECT metric_name, metric_value, metric_text
            FROM backtest_metrics
            WHERE run_id = ?
            ORDER BY metric_name
            """,
            (run_id,),
        )

    def fetch_backtest_logs(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        return self._fetch_rows(
            """
            SELECT recorded_at, level, stage, message
            FROM backtest_logs
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
        )

    def fetch_backtest_trades(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        return self._fetch_rows(
            """
            SELECT trade_time, order_book_id, side, price, quantity, amount
            FROM backtest_trades
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
        )

    def fetch_backtest_positions(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        rows = self._fetch_rows(
            """
            SELECT snapshot_time, order_book_id, quantity, market_value, notes_json
            FROM backtest_positions
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
        )
        return [
            {
                **dict(row),
                "notes": self._load_json(row.get("notes_json")),
            }
            for row in rows
        ]

    def fetch_backtest_accounts(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        rows = self._fetch_rows(
            """
            SELECT snapshot_time, total_value, market_value, cash, unit_net_value, notes_json
            FROM backtest_accounts
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
        )
        return [
            {
                **dict(row),
                "notes": self._load_json(row.get("notes_json")),
            }
            for row in rows
        ]

    def fetch_backtest_yearly_returns(
        self,
        run_id: str,
    ) -> Sequence[Mapping[str, Any]]:
        return self._fetch_rows(
            """
            SELECT year, portfolio_return, benchmark_return, excess_return
            FROM backtest_yearly_returns
            WHERE run_id = ?
            ORDER BY year
            """,
            (run_id,),
        )

    def fetch_research_run(self, run_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row["run_id"],
            "strategy_name": row["strategy_name"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "parameters": self._load_json(row["parameters_json"]),
        }

    def _fetch_rows(
        self,
        sql: str,
        parameters: tuple[Any, ...],
    ) -> list[Mapping[str, Any]]:
        self.ensure_schema()
        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    @contextmanager
    def _connect(self) -> Any:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _dump_json(value: Mapping[str, Any] | Sequence[Any] | Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _load_json(value: Any) -> Any:
        if value in (None, ""):
            return {}
        return json.loads(str(value))

    @staticmethod
    def _to_optional_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)
