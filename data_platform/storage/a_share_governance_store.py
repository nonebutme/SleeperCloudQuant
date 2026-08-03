"""Additive stage-78 governance storage for the canonical A-share database."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "78.1.0"


class AShareGovernanceStore:
    """Persist context facts, quality evidence and immutable data releases."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = NORMAL;

                CREATE TABLE IF NOT EXISTS market_schema_migrations (
                    schema_version TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS market_trade_calendar (
                    market TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    is_open INTEGER NOT NULL CHECK (is_open IN (0, 1)),
                    session_status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    PRIMARY KEY (market, trade_date)
                );

                CREATE INDEX IF NOT EXISTS idx_market_trade_calendar_open
                    ON market_trade_calendar (market, is_open, trade_date);

                CREATE TABLE IF NOT EXISTS security_lifecycle_events (
                    event_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    effective_from TEXT,
                    effective_to TEXT,
                    announced_at TEXT,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_security_lifecycle_asof
                    ON security_lifecycle_events (symbol, effective_from, effective_to);

                CREATE TABLE IF NOT EXISTS security_trading_status_daily (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('normal', 'suspended', 'resumed', 'unknown')
                    ),
                    is_tradable INTEGER CHECK (is_tradable IN (0, 1) OR is_tradable IS NULL),
                    suspension_reason TEXT,
                    expected_resume_date TEXT,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (symbol, trade_date)
                );

                CREATE INDEX IF NOT EXISTS idx_security_trading_status_date
                    ON security_trading_status_daily (trade_date, status);

                CREATE TABLE IF NOT EXISTS corporate_action_events (
                    action_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    report_period TEXT,
                    announcement_date TEXT,
                    record_date TEXT,
                    ex_date TEXT,
                    pay_date TEXT,
                    cash_ratio REAL,
                    bonus_ratio REAL,
                    transfer_ratio REAL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    evidence_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_corporate_action_symbol_ex_date
                    ON corporate_action_events (symbol, ex_date, announcement_date);

                CREATE TABLE IF NOT EXISTS price_adjustment_factors (
                    symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    factor_method TEXT NOT NULL,
                    factor REAL NOT NULL CHECK (factor > 0),
                    base_date TEXT,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    derived_from_action_version TEXT,
                    quality_status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (symbol, trade_date, factor_method)
                );

                CREATE TABLE IF NOT EXISTS market_index_daily_prices (
                    index_symbol TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    amount REAL,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    PRIMARY KEY (index_symbol, trade_date)
                );

                CREATE INDEX IF NOT EXISTS idx_market_index_daily_date
                    ON market_index_daily_prices (trade_date, index_symbol);

                CREATE TABLE IF NOT EXISTS data_quality_reports (
                    quality_report_id TEXT PRIMARY KEY,
                    rule_version TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('passed', 'failed', 'needs_attention')
                    ),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_versions (
                    data_version_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (
                        status IN ('draft', 'validating', 'published', 'rejected', 'superseded')
                    ),
                    as_of_trade_date TEXT NOT NULL,
                    parent_version_id TEXT,
                    quality_report_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    manifest_hash TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (quality_report_id)
                        REFERENCES data_quality_reports (quality_report_id)
                );

                CREATE INDEX IF NOT EXISTS idx_data_versions_status_asof
                    ON data_versions (status, as_of_trade_date DESC, published_at DESC);

                CREATE TABLE IF NOT EXISTS data_version_members (
                    data_version_id TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    adjustment TEXT NOT NULL DEFAULT '',
                    symbol_scope TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    symbol_count INTEGER NOT NULL,
                    min_date TEXT,
                    max_date TEXT,
                    source TEXT NOT NULL,
                    sync_run_ref TEXT,
                    content_hash TEXT NOT NULL,
                    quality_status TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    PRIMARY KEY (data_version_id, dataset, adjustment),
                    FOREIGN KEY (data_version_id)
                        REFERENCES data_versions (data_version_id)
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO market_schema_migrations
                    (schema_version, description, applied_at)
                VALUES (?, ?, ?)
                """,
                (
                    SCHEMA_VERSION,
                    "Add stage 78.1 context facts, quality reports and data versions",
                    _utc_now(),
                ),
            )

    def upsert_trade_calendar(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            (
                str(row.get("market") or "CN"),
                str(row.get("trade_date") or ""),
                1 if bool(row.get("is_open")) else 0,
                str(row.get("session_status") or ("open" if row.get("is_open") else "closed")),
                str(row.get("source") or "unknown"),
                str(row.get("source_observed_at") or _utc_now()),
                str(row.get("source_payload_hash") or _payload_hash(row)),
            )
            for row in rows
            if row.get("trade_date")
        ]
        return self._upsert_many(
            """
            INSERT INTO market_trade_calendar (
                market, trade_date, is_open, session_status, source,
                source_observed_at, source_payload_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market, trade_date) DO UPDATE SET
                is_open=excluded.is_open,
                session_status=excluded.session_status,
                source=excluded.source,
                source_observed_at=excluded.source_observed_at,
                source_payload_hash=excluded.source_payload_hash
            """,
            payload,
        )

    def upsert_lifecycle_events(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = []
        for row in rows:
            evidence = dict(row.get("evidence") or {})
            payload.append(
                (
                    str(row.get("event_id") or _lifecycle_id(row)),
                    _symbol(row.get("symbol")),
                    str(row.get("event_type") or "unknown"),
                    _optional_text(row.get("effective_from")),
                    _optional_text(row.get("effective_to")),
                    _optional_text(row.get("announced_at")),
                    str(row.get("source") or "unknown"),
                    str(row.get("source_observed_at") or _utc_now()),
                    str(row.get("source_payload_hash") or _payload_hash(evidence or row)),
                    _dump(evidence),
                )
            )
        return self._upsert_many(
            """
            INSERT INTO security_lifecycle_events (
                event_id, symbol, event_type, effective_from, effective_to,
                announced_at, source, source_observed_at, source_payload_hash,
                evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                effective_to=excluded.effective_to,
                announced_at=excluded.announced_at,
                source_observed_at=excluded.source_observed_at,
                source_payload_hash=excluded.source_payload_hash,
                evidence_json=excluded.evidence_json
            """,
            payload,
        )

    def upsert_trading_statuses(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = []
        for row in rows:
            status = str(row.get("status") or "unknown")
            if status not in {"normal", "suspended", "resumed", "unknown"}:
                raise ValueError(f"unsupported trading status: {status}")
            tradable = row.get("is_tradable")
            evidence = dict(row.get("evidence") or {})
            payload.append(
                (
                    _symbol(row.get("symbol")),
                    str(row.get("trade_date") or ""),
                    status,
                    None if tradable is None else (1 if bool(tradable) else 0),
                    _optional_text(row.get("suspension_reason")),
                    _optional_text(row.get("expected_resume_date")),
                    str(row.get("source") or "unknown"),
                    str(row.get("source_observed_at") or _utc_now()),
                    str(row.get("source_payload_hash") or _payload_hash(evidence or row)),
                    _dump(evidence),
                )
            )
        return self._upsert_many(
            """
            INSERT INTO security_trading_status_daily (
                symbol, trade_date, status, is_tradable, suspension_reason,
                expected_resume_date, source, source_observed_at,
                source_payload_hash, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, trade_date) DO UPDATE SET
                status=excluded.status,
                is_tradable=excluded.is_tradable,
                suspension_reason=excluded.suspension_reason,
                expected_resume_date=excluded.expected_resume_date,
                source=excluded.source,
                source_observed_at=excluded.source_observed_at,
                source_payload_hash=excluded.source_payload_hash,
                evidence_json=excluded.evidence_json
            """,
            payload,
        )

    def upsert_corporate_actions(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = []
        for row in rows:
            evidence = dict(row.get("evidence") or {})
            payload.append(
                (
                    str(row.get("action_id") or _corporate_action_id(row)),
                    _symbol(row.get("symbol")),
                    str(row.get("action_type") or "distribution"),
                    _optional_text(row.get("report_period")),
                    _optional_text(row.get("announcement_date")),
                    _optional_text(row.get("record_date")),
                    _optional_text(row.get("ex_date")),
                    _optional_text(row.get("pay_date")),
                    _optional_float(row.get("cash_ratio")),
                    _optional_float(row.get("bonus_ratio")),
                    _optional_float(row.get("transfer_ratio")),
                    str(row.get("status") or "unknown"),
                    str(row.get("source") or "unknown"),
                    str(row.get("source_observed_at") or _utc_now()),
                    str(row.get("source_payload_hash") or _payload_hash(evidence or row)),
                    _dump(evidence),
                )
            )
        return self._upsert_many(
            """
            INSERT INTO corporate_action_events (
                action_id, symbol, action_type, report_period, announcement_date,
                record_date, ex_date, pay_date, cash_ratio, bonus_ratio,
                transfer_ratio, status, source, source_observed_at,
                source_payload_hash, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_id) DO UPDATE SET
                record_date=excluded.record_date,
                ex_date=excluded.ex_date,
                pay_date=excluded.pay_date,
                status=excluded.status,
                source_observed_at=excluded.source_observed_at,
                source_payload_hash=excluded.source_payload_hash,
                evidence_json=excluded.evidence_json
            """,
            payload,
        )

    def upsert_adjustment_factors(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [
            (
                _symbol(row.get("symbol")),
                str(row.get("trade_date") or ""),
                str(row.get("factor_method") or ""),
                float(row.get("factor") or 0),
                _optional_text(row.get("base_date")),
                str(row.get("source") or "unknown"),
                str(row.get("source_observed_at") or _utc_now()),
                _optional_text(row.get("derived_from_action_version")),
                str(row.get("quality_status") or "unknown"),
                _dump(dict(row.get("evidence") or {})),
            )
            for row in rows
        ]
        if any(item[3] <= 0 for item in payload):
            raise ValueError("adjustment factors must be positive")
        return self._upsert_many(
            """
            INSERT INTO price_adjustment_factors (
                symbol, trade_date, factor_method, factor, base_date, source,
                source_observed_at, derived_from_action_version,
                quality_status, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, trade_date, factor_method) DO UPDATE SET
                factor=excluded.factor,
                base_date=excluded.base_date,
                source=excluded.source,
                source_observed_at=excluded.source_observed_at,
                derived_from_action_version=excluded.derived_from_action_version,
                quality_status=excluded.quality_status,
                evidence_json=excluded.evidence_json
            """,
            payload,
        )

    def upsert_index_prices(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = []
        for row in rows:
            evidence = dict(row)
            payload.append(
                (
                    str(row.get("index_symbol") or ""),
                    str(row.get("trade_date") or ""),
                    _optional_float(row.get("open")),
                    _optional_float(row.get("high")),
                    _optional_float(row.get("low")),
                    _optional_float(row.get("close")),
                    _optional_float(row.get("volume")),
                    _optional_float(row.get("amount")),
                    str(row.get("source") or "unknown"),
                    str(row.get("source_observed_at") or _utc_now()),
                    str(row.get("source_payload_hash") or _payload_hash(evidence)),
                )
            )
        return self._upsert_many(
            """
            INSERT INTO market_index_daily_prices (
                index_symbol, trade_date, open, high, low, close, volume,
                amount, source, source_observed_at, source_payload_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(index_symbol, trade_date) DO UPDATE SET
                open=excluded.open,
                high=excluded.high,
                low=excluded.low,
                close=excluded.close,
                volume=excluded.volume,
                amount=excluded.amount,
                source=excluded.source,
                source_observed_at=excluded.source_observed_at,
                source_payload_hash=excluded.source_payload_hash
            """,
            payload,
        )

    def save_quality_report(
        self,
        *,
        quality_report_id: str,
        rule_version: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        if status not in {"passed", "failed", "needs_attention"}:
            raise ValueError(f"unsupported quality status: {status}")
        serialized = _dump(payload)
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT payload_hash FROM data_quality_reports WHERE quality_report_id=?",
                (quality_report_id,),
            ).fetchone()
            payload_hash = sha256(serialized.encode("utf-8")).hexdigest()
            if existing and str(existing["payload_hash"]) != payload_hash:
                raise ValueError("quality reports are immutable")
            connection.execute(
                """
                INSERT OR IGNORE INTO data_quality_reports (
                    quality_report_id, rule_version, status, created_at,
                    payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    quality_report_id,
                    rule_version,
                    status,
                    _utc_now(),
                    serialized,
                    payload_hash,
                ),
            )
        return self.fetch_quality_report(quality_report_id)

    def publish_data_version(
        self,
        *,
        as_of_trade_date: str,
        quality_report_id: str,
        members: Sequence[Mapping[str, Any]],
        notes: str = "",
    ) -> dict[str, Any]:
        self.ensure_schema()
        normalized_members = [_normalize_member(member) for member in members]
        if not normalized_members:
            raise ValueError("data version requires at least one member")
        if any(member["quality_status"] != "passed" for member in normalized_members):
            raise ValueError("all published data version members must pass quality")
        manifest = {
            "as_of_trade_date": str(as_of_trade_date),
            "quality_report_id": quality_report_id,
            "members": sorted(
                normalized_members,
                key=lambda item: (item["dataset"], item["adjustment"]),
            ),
        }
        manifest_json = _dump(manifest)
        manifest_hash = sha256(manifest_json.encode("utf-8")).hexdigest()
        data_version_id = f"scq-{as_of_trade_date.replace('-', '')}-{manifest_hash[:16]}"
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            report = connection.execute(
                "SELECT status FROM data_quality_reports WHERE quality_report_id=?",
                (quality_report_id,),
            ).fetchone()
            if report is None or str(report["status"]) != "passed":
                raise ValueError("published data version requires a passed quality report")
            existing = connection.execute(
                "SELECT manifest_hash FROM data_versions WHERE data_version_id=?",
                (data_version_id,),
            ).fetchone()
            if existing and str(existing["manifest_hash"]) != manifest_hash:
                raise ValueError("data versions are immutable")
            parent = connection.execute(
                """
                SELECT data_version_id FROM data_versions
                WHERE status='published' AND data_version_id<>?
                ORDER BY as_of_trade_date DESC, published_at DESC
                LIMIT 1
                """,
                (data_version_id,),
            ).fetchone()
            connection.execute(
                """UPDATE data_versions SET status='superseded'
                   WHERE status='published' AND data_version_id<>?""",
                (data_version_id,),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO data_versions (
                    data_version_id, status, as_of_trade_date, parent_version_id,
                    quality_report_id, created_at, published_at, manifest_hash, notes
                ) VALUES (?, 'published', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data_version_id,
                    str(as_of_trade_date),
                    str(parent["data_version_id"]) if parent else None,
                    quality_report_id,
                    now,
                    now,
                    manifest_hash,
                    str(notes),
                ),
            )
            connection.execute(
                """
                UPDATE data_versions SET
                    status='published',
                    published_at=?,
                    notes=?
                WHERE data_version_id=?
                """,
                (now, str(notes), data_version_id),
            )
            for member in normalized_members:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_version_members (
                        data_version_id, dataset, adjustment, symbol_scope,
                        row_count, symbol_count, min_date, max_date, source,
                        sync_run_ref, content_hash, quality_status, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data_version_id,
                        member["dataset"],
                        member["adjustment"],
                        member["symbol_scope"],
                        member["row_count"],
                        member["symbol_count"],
                        member["min_date"],
                        member["max_date"],
                        member["source"],
                        member["sync_run_ref"],
                        member["content_hash"],
                        member["quality_status"],
                        _dump(member["details"]),
                    ),
                )
        return self.fetch_data_version(data_version_id)

    def resolve_published_data_version(
        self,
        *,
        symbol: str,
        adjustment: str,
        start_date: str,
        end_date: str,
        benchmark: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        code = _symbol(symbol)
        mode = str(adjustment or "raw").lower()
        with closing(self._connect(read_only=True)) as connection:
            version = connection.execute(
                """
                SELECT * FROM data_versions
                WHERE status='published'
                ORDER BY as_of_trade_date DESC, published_at DESC
                LIMIT 1
                """
            ).fetchone()
            if version is None:
                return {
                    "status": "data_not_ready",
                    "reason": "no_published_data_version",
                    "symbol": code,
                    "adjustment": mode,
                }
            member = connection.execute(
                """
                SELECT * FROM data_version_members
                WHERE data_version_id=?
                  AND dataset='market_daily_prices'
                  AND adjustment=?
                """,
                (version["data_version_id"], mode),
            ).fetchone()
            if (
                member is None
                or str(member["min_date"] or "") > str(start_date)
                or str(member["max_date"] or "") < str(end_date)
            ):
                return {
                    "status": "data_not_ready",
                    "reason": "published_version_does_not_cover_requested_window",
                    "data_version": version["data_version_id"],
                    "symbol": code,
                    "adjustment": mode,
                }
            symbol_range = connection.execute(
                """
                SELECT COUNT(*) AS row_count, MIN(trade_date) AS min_date,
                       MAX(trade_date) AS max_date
                FROM market_daily_prices
                WHERE symbol=? AND adjustment=?
                  AND trade_date>=? AND trade_date<=?
                """,
                (code, mode, str(start_date), str(end_date)),
            ).fetchone()
            if int(symbol_range["row_count"] or 0) <= 0:
                return {
                    "status": "data_not_ready",
                    "reason": "symbol_has_no_rows_in_requested_window",
                    "data_version": version["data_version_id"],
                    "symbol": code,
                    "adjustment": mode,
                }
            members = connection.execute(
                """
                SELECT dataset, adjustment, symbol_scope, row_count, symbol_count,
                       min_date, max_date, source, content_hash, quality_status
                FROM data_version_members WHERE data_version_id=?
                ORDER BY dataset, adjustment
                """,
                (version["data_version_id"],),
            ).fetchall()
        return {
            "status": "bound",
            "source": "canonical_a_share_sqlite",
            "dataset": "market_daily_prices",
            "data_version": str(version["data_version_id"]),
            "quality_report_id": str(version["quality_report_id"]),
            "quality_status": "passed",
            "coverage_status": "active",
            "symbol": code,
            "adjustment": mode,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "row_count": int(symbol_range["row_count"] or 0),
            "as_of_trade_date": str(version["as_of_trade_date"]),
            "benchmark": benchmark,
            "members": [dict(row) for row in members],
        }

    def fetch_index_price_history(
        self,
        index_symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return ascending bars from the formally governed index dataset."""

        self.ensure_schema()
        code = str(index_symbol).split(".")[0].strip()
        conditions = ["index_symbol=?"]
        parameters: list[Any] = [code]
        if start_date:
            conditions.append("trade_date>=?")
            parameters.append(str(start_date))
        if end_date:
            conditions.append("trade_date<=?")
            parameters.append(str(end_date))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""
                SELECT trade_date AS date, open, high, low, close, volume, amount,
                       source, source_observed_at
                FROM market_index_daily_prices
                WHERE {' AND '.join(conditions)}
                ORDER BY trade_date ASC
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]
    def list_index_price_assets(self) -> list[dict[str, Any]]:
        """Summarize the governed index series currently available locally."""

        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """
                SELECT index_symbol, COUNT(*) AS row_count,
                       MIN(trade_date) AS min_date, MAX(trade_date) AS max_date,
                       MAX(source_observed_at) AS source_observed_at
                FROM market_index_daily_prices
                GROUP BY index_symbol
                ORDER BY index_symbol
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_index_daily_prices(
        self,
        *,
        index_symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return one governed index series with stable pagination."""

        code = str(index_symbol).split(".")[0].strip()
        rows = self.fetch_index_price_history(
            code,
            start_date=start_date,
            end_date=end_date,
        )
        previous_close: float | None = None
        normalized = []
        for row in rows:
            current = dict(row)
            close = _optional_float(current.get("close"))
            current["index_symbol"] = code
            current["change_pct"] = (
                round((close / previous_close - 1) * 100, 4)
                if close is not None and previous_close not in {None, 0}
                else None
            )
            if close is not None:
                previous_close = close
            normalized.append(current)
        normalized.reverse()
        safe_limit = max(1, min(int(limit), 2000))
        safe_offset = max(0, int(offset))
        page = normalized[safe_offset:safe_offset + safe_limit]
        return {
            "status": "ready" if normalized else "empty",
            "source": "canonical_a_share_sqlite",
            "dataset": "market_index_daily_prices",
            "index_symbol": code,
            "total": len(normalized),
            "rows": page,
            "limit": safe_limit,
            "offset": safe_offset,
            "read_only": True,
        }

    def fetch_data_version(self, data_version_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            version = connection.execute(
                "SELECT * FROM data_versions WHERE data_version_id=?",
                (data_version_id,),
            ).fetchone()
            if version is None:
                return {"status": "not_found", "data_version_id": data_version_id}
            members = connection.execute(
                """
                SELECT * FROM data_version_members
                WHERE data_version_id=? ORDER BY dataset, adjustment
                """,
                (data_version_id,),
            ).fetchall()
        return {**dict(version), "members": [dict(row) for row in members]}

    def fetch_quality_report(self, quality_report_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM data_quality_reports WHERE quality_report_id=?",
                (quality_report_id,),
            ).fetchone()
        if row is None:
            return {"status": "not_found", "quality_report_id": quality_report_id}
        payload = dict(row)
        payload["payload"] = json.loads(str(payload.pop("payload_json") or "{}"))
        return payload

    def get_overview(self) -> dict[str, Any]:
        self.ensure_schema()
        tables = (
            "market_trade_calendar",
            "security_lifecycle_events",
            "security_trading_status_daily",
            "corporate_action_events",
            "price_adjustment_factors",
            "market_index_daily_prices",
            "data_quality_reports",
            "data_versions",
            "data_version_members",
        )
        with closing(self._connect(read_only=True)) as connection:
            counts = {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }
            published = connection.execute(
                """
                SELECT data_version_id, as_of_trade_date, quality_report_id, published_at
                FROM data_versions WHERE status='published'
                ORDER BY as_of_trade_date DESC, published_at DESC LIMIT 1
                """
            ).fetchone()
        return {
            "status": "ready",
            "schema_version": SCHEMA_VERSION,
            "database_path": str(self.database_path.resolve()),
            "counts": counts,
            "published_version": dict(published) if published else None,
        }

    def _upsert_many(self, sql: str, payload: Sequence[Sequence[Any]]) -> int:
        if not payload:
            return 0
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.executemany(sql, payload)
        return len(payload)

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"file:{self.database_path.resolve().as_posix()}?mode=ro",
                uri=True,
            )
            connection.execute("PRAGMA query_only = ON")
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection


def _normalize_member(member: Mapping[str, Any]) -> dict[str, Any]:
    details = dict(member.get("details") or {})
    normalized = {
        "dataset": str(member.get("dataset") or ""),
        "adjustment": str(member.get("adjustment") or ""),
        "symbol_scope": str(member.get("symbol_scope") or "all"),
        "row_count": int(member.get("row_count") or 0),
        "symbol_count": int(member.get("symbol_count") or 0),
        "min_date": _optional_text(member.get("min_date")),
        "max_date": _optional_text(member.get("max_date")),
        "source": str(member.get("source") or "unknown"),
        "sync_run_ref": _optional_text(member.get("sync_run_ref")),
        "quality_status": str(member.get("quality_status") or "unknown"),
        "details": details,
    }
    normalized["content_hash"] = str(
        member.get("content_hash") or _payload_hash(normalized)
    )
    if not normalized["dataset"]:
        raise ValueError("data version member dataset is required")
    return normalized


def _lifecycle_id(payload: Mapping[str, Any]) -> str:
    identity = {
        "symbol": _symbol(payload.get("symbol")),
        "event_type": str(payload.get("event_type") or "unknown"),
        "effective_from": _optional_text(payload.get("effective_from")),
        "announced_at": _optional_text(payload.get("announced_at")),
    }
    return _stable_id("lifecycle", identity)


def _corporate_action_id(payload: Mapping[str, Any]) -> str:
    identity = {
        "symbol": _symbol(payload.get("symbol")),
        "action_type": str(payload.get("action_type") or "distribution"),
        "report_period": _optional_text(payload.get("report_period")),
        "announcement_date": _optional_text(payload.get("announcement_date")),
        "ex_date": _optional_text(payload.get("ex_date")),
    }
    return _stable_id("action", identity)

def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return f"{prefix}-{_payload_hash(payload)[:24]}"


def _payload_hash(payload: Mapping[str, Any]) -> str:
    return sha256(_dump(payload).encode("utf-8")).hexdigest()


def _symbol(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text.zfill(6)


def _optional_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    return None if number != number else number


def _dump(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
