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
                    error_message TEXT,
                    deleted_at TEXT,
                    deleted_reason TEXT
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
                CREATE TABLE IF NOT EXISTS report_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    report_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_report_snapshots_run_type
                ON report_snapshots (run_id, report_type, created_at DESC);

                CREATE TABLE IF NOT EXISTS ai_workflow_runs (
                    workflow_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    analysis_date TEXT,
                    report_id TEXT,
                    status TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    provider_mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    deleted_at TEXT,
                    deleted_reason TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_ai_workflow_runs_symbol_generated
                ON ai_workflow_runs (symbol, generated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_ai_workflow_runs_report_generated
                ON ai_workflow_runs (report_id, generated_at DESC);

                CREATE TABLE IF NOT EXISTS report_packages (
                    package_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    workflow_id TEXT,
                    snapshot_id TEXT,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    deleted_at TEXT,
                    deleted_reason TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_report_packages_run_created
                ON report_packages (run_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS local_data_assets (
                    asset_key TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    data_version TEXT,
                    quality_status TEXT,
                    coverage_status TEXT,
                    row_count INTEGER,
                    start_date TEXT,
                    end_date TEXT,
                    latest_synced_at TEXT,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_local_data_assets_symbol
                ON local_data_assets (dataset, symbol, updated_at DESC);

                CREATE TABLE IF NOT EXISTS backtest_input_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    data_version TEXT,
                    bound_at TEXT NOT NULL,
                    asset_key TEXT,
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_backtest_input_snapshots_run
                ON backtest_input_snapshots (run_id, bound_at DESC);
                """
            )

            columns = {str(row["name"]) for row in connection.execute("PRAGMA table_info(backtest_runs)").fetchall()}
            if "deleted_at" not in columns:
                connection.execute("ALTER TABLE backtest_runs ADD COLUMN deleted_at TEXT")
            if "deleted_reason" not in columns:
                connection.execute("ALTER TABLE backtest_runs ADD COLUMN deleted_reason TEXT")
            for table in ("ai_workflow_runs", "report_packages"):
                columns = {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
                if "deleted_at" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT")
                if "deleted_reason" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN deleted_reason TEXT")

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


    def save_backtest_input_snapshot(
        self,
        *,
        run_id: str,
        data_asset_trace: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Persist one run input snapshot and refresh the local data asset directory."""

        self.ensure_schema()
        trace = dict(data_asset_trace or {})
        asset = dict(trace.get("asset") or {}) if isinstance(trace.get("asset"), Mapping) else {}
        dataset = str(asset.get("dataset") or "price_history")
        symbol = str(trace.get("symbol") or asset.get("symbol") or "")
        data_version = _optional_text(asset.get("data_version"))
        bound_at = str(trace.get("bound_at") or asset.get("latest_synced_at") or "") or "not_recorded"
        asset_key = f"{dataset}:{symbol}:{data_version or 'unknown'}"
        snapshot_id = f"{run_id}:{asset_key}"
        payload = {
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "asset_key": asset_key,
            "trace": trace,
            "asset": asset,
            "manifest": trace.get("manifest") or {},
        }
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO local_data_assets (
                    asset_key,
                    dataset,
                    symbol,
                    data_version,
                    quality_status,
                    coverage_status,
                    row_count,
                    start_date,
                    end_date,
                    latest_synced_at,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_key) DO UPDATE SET
                    quality_status = excluded.quality_status,
                    coverage_status = excluded.coverage_status,
                    row_count = excluded.row_count,
                    start_date = excluded.start_date,
                    end_date = excluded.end_date,
                    latest_synced_at = excluded.latest_synced_at,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    asset_key,
                    dataset,
                    symbol,
                    data_version,
                    _optional_text(asset.get("quality_status")),
                    _optional_text(asset.get("coverage_status")),
                    _optional_int(asset.get("row_count")),
                    _optional_text(asset.get("start_date")),
                    _optional_text(asset.get("end_date")),
                    _optional_text(asset.get("latest_synced_at")),
                    bound_at,
                    self._dump_json(payload),
                ),
            )
            connection.execute(
                """
                INSERT INTO backtest_input_snapshots (
                    snapshot_id,
                    run_id,
                    dataset,
                    symbol,
                    data_version,
                    bound_at,
                    asset_key,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    dataset = excluded.dataset,
                    symbol = excluded.symbol,
                    data_version = excluded.data_version,
                    bound_at = excluded.bound_at,
                    asset_key = excluded.asset_key,
                    payload_json = excluded.payload_json
                """,
                (snapshot_id, run_id, dataset, symbol, data_version, bound_at, asset_key, self._dump_json(payload)),
            )
        return payload

    def fetch_backtest_input_snapshot(self, run_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM backtest_input_snapshots
                WHERE run_id = ?
                ORDER BY bound_at DESC, snapshot_id DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        payload = self._load_json(row["payload_json"])
        return {
            "snapshot_id": row["snapshot_id"],
            "run_id": row["run_id"],
            "dataset": row["dataset"],
            "symbol": row["symbol"],
            "data_version": row["data_version"],
            "bound_at": row["bound_at"],
            "asset_key": row["asset_key"],
            "payload": payload,
        }

    def fetch_local_data_assets(
        self,
        *,
        symbol: str | None = None,
        dataset: str | None = None,
        data_version: str | None = None,
        quality_status: str | None = None,
        coverage_status: str | None = None,
        limit: int = 100,
    ) -> Sequence[Mapping[str, Any]]:
        self.ensure_schema()
        safe_limit = max(1, min(int(limit), 500))
        filters: list[str] = []
        values: list[Any] = []
        for column, value in (
            ("symbol", symbol),
            ("dataset", dataset),
            ("data_version", data_version),
            ("quality_status", quality_status),
            ("coverage_status", coverage_status),
        ):
            if value:
                filters.append(f"{column} = ?")
                values.append(str(value))
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        query = f"""
                    SELECT *
                    FROM local_data_assets
                    {where_clause}
                    ORDER BY updated_at DESC, asset_key DESC
                    LIMIT ?
                    """
        values.append(safe_limit)
        with self._connect() as connection:
            rows = connection.execute(query, tuple(values)).fetchall()
        return [
            {
                "asset_key": row["asset_key"],
                "dataset": row["dataset"],
                "symbol": row["symbol"],
                "data_version": row["data_version"],
                "quality_status": row["quality_status"],
                "coverage_status": row["coverage_status"],
                "row_count": row["row_count"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "latest_synced_at": row["latest_synced_at"],
                "updated_at": row["updated_at"],
                "payload": self._load_json(row["payload_json"]),
            }
            for row in rows
        ]
    def save_ai_workflow_run(
        self,
        *,
        workflow_id: str,
        symbol: str,
        analysis_date: str | None,
        report_id: str | None,
        status: str,
        generated_at: str,
        provider_mode: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Persist one AI workflow trace for later review."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_workflow_runs (
                    workflow_id,
                    symbol,
                    analysis_date,
                    report_id,
                    status,
                    generated_at,
                    provider_mode,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    symbol = excluded.symbol,
                    analysis_date = excluded.analysis_date,
                    report_id = excluded.report_id,
                    status = excluded.status,
                    generated_at = excluded.generated_at,
                    provider_mode = excluded.provider_mode,
                    payload_json = excluded.payload_json
                """,
                (
                    workflow_id,
                    symbol,
                    analysis_date,
                    report_id,
                    status,
                    generated_at,
                    provider_mode,
                    self._dump_json(payload),
                ),
            )

    def fetch_ai_workflow_run(self, workflow_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM ai_workflow_runs WHERE workflow_id = ? AND deleted_at IS NULL",
                (workflow_id,),
            ).fetchone()
        if row is None:
            return None
        return self._to_ai_workflow_run(row)

    def fetch_ai_workflow_runs(
        self,
        *,
        symbol: str | None = None,
        limit: int = 20,
    ) -> Sequence[Mapping[str, Any]]:
        self.ensure_schema()
        normalized_limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            if symbol:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM ai_workflow_runs
                    WHERE symbol = ? AND deleted_at IS NULL
                    ORDER BY generated_at DESC, workflow_id DESC
                    LIMIT ?
                    """,
                    (symbol, normalized_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM ai_workflow_runs
                    WHERE deleted_at IS NULL
                    ORDER BY generated_at DESC, workflow_id DESC
                    LIMIT ?
                    """,
                    (normalized_limit,),
                ).fetchall()
        return [self._to_ai_workflow_run(row) for row in rows]

    def fetch_ai_workflow_runs_by_report(
        self,
        *,
        report_id: str,
        symbol: str | None = None,
        limit: int = 20,
    ) -> Sequence[Mapping[str, Any]]:
        self.ensure_schema()
        normalized_limit = max(1, min(int(limit), 100))
        with self._connect() as connection:
            if symbol:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM ai_workflow_runs
                    WHERE report_id = ? AND symbol = ? AND deleted_at IS NULL
                    ORDER BY generated_at DESC, workflow_id DESC
                    LIMIT ?
                    """,
                    (report_id, symbol, normalized_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM ai_workflow_runs
                    WHERE report_id = ? AND deleted_at IS NULL
                    ORDER BY generated_at DESC, workflow_id DESC
                    LIMIT ?
                    """,
                    (report_id, normalized_limit),
                ).fetchall()
        return [self._to_ai_workflow_run(row) for row in rows]

    def save_report_package(
        self,
        *,
        package_id: str,
        run_id: str,
        workflow_id: str | None,
        snapshot_id: str | None,
        created_at: str,
        title: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Persist one research report package binding run, AI workflow, and snapshots."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO report_packages (
                    package_id,
                    run_id,
                    workflow_id,
                    snapshot_id,
                    created_at,
                    title,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(package_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    workflow_id = excluded.workflow_id,
                    snapshot_id = excluded.snapshot_id,
                    created_at = excluded.created_at,
                    title = excluded.title,
                    payload_json = excluded.payload_json
                """,
                (package_id, run_id, workflow_id, snapshot_id, created_at, title, self._dump_json(payload)),
            )

    def fetch_report_package(self, package_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_packages WHERE package_id = ? AND deleted_at IS NULL",
                (package_id,),
            ).fetchone()
        if row is None:
            return None
        return self._to_report_package(row)


    def update_report_package_payload(self, package_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        current = self.fetch_report_package(package_id)
        if current is None:
            return None
        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE report_packages
                SET payload_json = ?
                WHERE package_id = ?
                """,
                (self._dump_json(payload), package_id),
            )
        return self.fetch_report_package(package_id)
    def fetch_report_packages(self, run_id: str) -> Sequence[Mapping[str, Any]]:
        rows = self._fetch_rows(
            """
            SELECT *
            FROM report_packages
            WHERE run_id = ? AND deleted_at IS NULL
            ORDER BY created_at DESC, package_id DESC
            """,
            (run_id,),
        )
        return [self._to_report_package(row) for row in rows]


    def fetch_report_package_directory(self, *, run_id: str | None = None, limit: int = 20) -> Sequence[Mapping[str, Any]]:
        self.ensure_schema()
        normalized_limit = max(1, min(int(limit or 20), 200))
        if run_id:
            rows = self._fetch_rows(
                """
                SELECT *
                FROM report_packages
                WHERE run_id = ? AND deleted_at IS NULL
                ORDER BY created_at DESC, package_id DESC
                LIMIT ?
                """,
                (run_id, normalized_limit),
            )
        else:
            rows = self._fetch_rows(
                """
                SELECT *
                FROM report_packages
                WHERE deleted_at IS NULL
                ORDER BY created_at DESC, package_id DESC
                LIMIT ?
                """,
                (normalized_limit,),
            )
        return [self._to_report_package(row) for row in rows]
    def soft_delete_ai_workflow_run(self, workflow_id: str, *, deleted_at: str, reason: str) -> Mapping[str, Any] | None:
        current = self.fetch_ai_workflow_run(workflow_id)
        if current is None: return None
        with self._connect() as connection:
            connection.execute("UPDATE ai_workflow_runs SET deleted_at=?, deleted_reason=? WHERE workflow_id=?", (deleted_at, reason[:500], workflow_id))
        return {**dict(current), "deleted_at": deleted_at, "deleted_reason": reason}

    def soft_delete_report_package(self, package_id: str, *, deleted_at: str, reason: str) -> Mapping[str, Any] | None:
        current = self.fetch_report_package(package_id)
        if current is None: return None
        with self._connect() as connection:
            connection.execute("UPDATE report_packages SET deleted_at=?, deleted_reason=? WHERE package_id=?", (deleted_at, reason[:500], package_id))
        return {**dict(current), "deleted_at": deleted_at, "deleted_reason": reason}

    def _to_report_package(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "package_id": row["package_id"],
            "run_id": row["run_id"],
            "workflow_id": row["workflow_id"],
            "snapshot_id": row["snapshot_id"],
            "created_at": row["created_at"],
            "title": row["title"],
            "payload": self._load_json(row["payload_json"]),
        }
    def _to_ai_workflow_run(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "workflow_id": row["workflow_id"],
            "symbol": row["symbol"],
            "analysis_date": row["analysis_date"],
            "report_id": row["report_id"],
            "status": row["status"],
            "generated_at": row["generated_at"],
            "provider_mode": row["provider_mode"],
            "payload": self._load_json(row["payload_json"]),
        }
    def save_report_snapshot(
        self,
        *,
        snapshot_id: str,
        run_id: str,
        report_type: str,
        report_version: str,
        created_at: str,
        title: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Persist one immutable report snapshot."""

        self.ensure_schema()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO report_snapshots (
                    snapshot_id,
                    run_id,
                    report_type,
                    report_version,
                    created_at,
                    title,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    report_type = excluded.report_type,
                    report_version = excluded.report_version,
                    created_at = excluded.created_at,
                    title = excluded.title,
                    payload_json = excluded.payload_json
                """,
                (
                    snapshot_id,
                    run_id,
                    report_type,
                    report_version,
                    created_at,
                    title,
                    self._dump_json(payload),
                ),
            )

    def fetch_report_snapshot(self, snapshot_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM report_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        return self._to_report_snapshot(row)

    def fetch_report_snapshots(
        self,
        *,
        run_id: str,
        report_type: str | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if report_type is None:
            return self._fetch_rows(
                """
                SELECT snapshot_id, run_id, report_type, report_version, created_at, title, payload_json
                FROM report_snapshots
                WHERE run_id = ?
                ORDER BY created_at DESC, snapshot_id DESC
                """,
                (run_id,),
            )
        return self._fetch_rows(
            """
            SELECT snapshot_id, run_id, report_type, report_version, created_at, title, payload_json
            FROM report_snapshots
            WHERE run_id = ? AND report_type = ?
            ORDER BY created_at DESC, snapshot_id DESC
            """,
            (run_id, report_type),
        )

    def _to_report_snapshot(self, row: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "snapshot_id": row["snapshot_id"],
            "run_id": row["run_id"],
            "report_type": row["report_type"],
            "report_version": row["report_version"],
            "created_at": row["created_at"],
            "title": row["title"],
            "payload": self._load_json(row["payload_json"]),
        }

    def fetch_backtest_runs_by_prefix(self, run_id_prefix: str) -> Sequence[Mapping[str, Any]]:
        """Fetch backtest runs whose IDs share one parameter-scan prefix."""

        rows = self._fetch_rows(
            """
            SELECT *
            FROM backtest_runs
            WHERE run_id LIKE ? AND deleted_at IS NULL
            ORDER BY run_id
            """,
            (f"{run_id_prefix}%",),
        )
        return [
            {
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
            for row in rows
        ]
    def list_backtest_runs(self, limit: int = 50) -> Sequence[Mapping[str, Any]]:
        """List recent non-deleted single-stock backtest runs for workspace history."""
        self.ensure_schema()
        safe_limit = max(1, min(int(limit or 50), 200))
        rows = self._fetch_rows(
            """
            SELECT * FROM backtest_runs
            WHERE deleted_at IS NULL
            ORDER BY created_at DESC, run_id DESC
            LIMIT ?
            """,
            (safe_limit,),
        )
        return [
            {
                "run_id": row["run_id"], "strategy_name": row["strategy_name"],
                "strategy_id": row["strategy_id"], "status": row["status"],
                "benchmark": row["benchmark"], "universe": row["universe"],
                "start_date": row["start_date"], "end_date": row["end_date"],
                "created_at": row["created_at"], "completed_at": row["completed_at"],
                "parameters": self._load_json(row["parameters_json"]),
                "extra_config": self._load_json(row["extra_config_json"]),
                "raw_result": self._load_json(row["raw_result_json"]),
                "error_message": row["error_message"],
            }
            for row in rows
        ]
    def fetch_backtest_run(self, run_id: str) -> Mapping[str, Any] | None:
        self.ensure_schema()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM backtest_runs WHERE run_id = ? AND deleted_at IS NULL",
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

    def soft_delete_backtest_run(self, run_id: str, *, deleted_at: str, reason: str) -> Mapping[str, Any] | None:
        """Hide one terminal run while retaining its audit and reporting evidence."""

        self.ensure_schema()
        run = self.fetch_backtest_run(run_id)
        if run is None:
            return None
        if str(run.get("status") or "") in {"pending", "running"}:
            raise ValueError("running backtest run cannot be deleted")
        with self._connect() as connection:
            connection.execute(
                "UPDATE backtest_runs SET deleted_at=?, deleted_reason=? WHERE run_id=?",
                (deleted_at, str(reason or "用户从 Web 工作台删除")[:500], run_id),
            )
        return {**dict(run), "deleted_at": deleted_at, "deleted_reason": reason}

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

    def iter_backtest_exposure_snapshots(self, run_id_prefix: str) -> Any:
        """Stream only fields needed by cross-sectional exposure analysis."""
        self.ensure_schema()
        escaped_prefix = (
            str(run_id_prefix)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT accounts.run_id, accounts.snapshot_time,
                       accounts.total_value,
                       COALESCE(positions.market_value, 0.0)
                           AS position_market_value
                FROM backtest_accounts AS accounts
                LEFT JOIN backtest_positions AS positions
                  ON positions.run_id = accounts.run_id
                 AND positions.snapshot_time = accounts.snapshot_time
                WHERE accounts.run_id LIKE ? ESCAPE '\\'
                ORDER BY accounts.run_id, accounts.id
                """,
                (f"{escaped_prefix}%",),
            )
            for row in cursor:
                yield dict(row)

    def fetch_first_buy_dates(self, run_id_prefix: str) -> Mapping[str, str]:
        """Read the first effective BUY date for all runs sharing one prefix."""
        escaped_prefix = (
            str(run_id_prefix)
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        rows = self._fetch_rows(
            """
            SELECT run_id, MIN(SUBSTR(trade_time, 1, 10)) AS entry_date
            FROM backtest_trades
            WHERE run_id LIKE ? ESCAPE '\\'
              AND UPPER(side) = 'BUY'
              AND quantity > 0
            GROUP BY run_id
            """,
            (f"{escaped_prefix}%",),
        )
        return {
            str(row["run_id"]): str(row["entry_date"])
            for row in rows
            if row.get("run_id") and row.get("entry_date")
        }
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
        if "payload_json" in rows[0] if rows else False:
            return [self._to_report_snapshot(row) for row in rows]
        return [dict(row) for row in rows]

    @contextmanager
    def _connect(self) -> Any:
        connection = sqlite3.connect(self._database_path, timeout=30)
        connection.execute("PRAGMA busy_timeout=30000")
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


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)









