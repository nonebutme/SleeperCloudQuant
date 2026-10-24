"""Additive stage-78 governance storage for the canonical A-share database."""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from data_platform.research_data_version import ResearchDataVersionResolver


SCHEMA_VERSION = "78.1.0"
GLOBAL_INDEX_QUALITY_RULE_VERSION = "global-index-append-only-v1"


class GlobalIndexQualityError(ValueError):
    """Raised after a rejected global-index batch has been recorded."""


class GlobalIndexHistoryConflict(RuntimeError):
    """Raised when an upstream row would change a persisted historical bar."""


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

                CREATE TABLE IF NOT EXISTS security_master_intervals (
                    interval_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    name TEXT NOT NULL DEFAULT '',
                    listing_status TEXT NOT NULL,
                    risk_warning INTEGER NOT NULL CHECK (risk_warning IN (0, 1)),
                    available_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_observed_at TEXT NOT NULL,
                    source_payload_hash TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
                );

                CREATE INDEX IF NOT EXISTS idx_security_master_intervals_asof
                    ON security_master_intervals (symbol, valid_from, valid_to, available_at);

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

                CREATE TABLE IF NOT EXISTS global_index_releases (
                    release_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    start_trade_date TEXT NOT NULL,
                    target_trade_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    quality_rule_version TEXT NOT NULL,
                    item_count INTEGER NOT NULL DEFAULT 0,
                    passed_items INTEGER NOT NULL DEFAULT 0,
                    rejected_items INTEGER NOT NULL DEFAULT 0,
                    inserted_rows INTEGER NOT NULL DEFAULT 0,
                    unchanged_rows INTEGER NOT NULL DEFAULT 0,
                    conflict_rows INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    published_at TEXT
                );

                CREATE TABLE IF NOT EXISTS global_index_release_items (
                    release_id TEXT NOT NULL,
                    index_symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    received_rows INTEGER NOT NULL,
                    inserted_rows INTEGER NOT NULL,
                    unchanged_rows INTEGER NOT NULL,
                    conflict_rows INTEGER NOT NULL,
                    min_trade_date TEXT,
                    max_trade_date TEXT,
                    quality_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY (release_id, index_symbol),
                    FOREIGN KEY (release_id) REFERENCES global_index_releases (release_id)
                );

                CREATE TABLE IF NOT EXISTS global_index_release_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    release_id TEXT NOT NULL,
                    index_symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    received_rows INTEGER NOT NULL,
                    inserted_rows INTEGER NOT NULL,
                    unchanged_rows INTEGER NOT NULL,
                    conflict_rows INTEGER NOT NULL,
                    quality_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY (release_id) REFERENCES global_index_releases (release_id)
                );

                CREATE INDEX IF NOT EXISTS idx_global_index_release_attempts
                    ON global_index_release_attempts
                    (release_id, index_symbol, recorded_at);

                CREATE TABLE IF NOT EXISTS global_index_market_sessions (
                    market TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    source TEXT NOT NULL,
                    first_observed_at TEXT NOT NULL,
                    last_observed_at TEXT NOT NULL,
                    PRIMARY KEY (market, trade_date)
                );

                CREATE TABLE IF NOT EXISTS global_index_calendar_observations (
                    release_id TEXT NOT NULL,
                    index_symbol TEXT NOT NULL,
                    market TEXT NOT NULL,
                    range_start TEXT NOT NULL,
                    range_end TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (release_id, index_symbol),
                    FOREIGN KEY (release_id) REFERENCES global_index_releases (release_id)
                );

                CREATE INDEX IF NOT EXISTS idx_global_index_calendar_market_range
                    ON global_index_calendar_observations
                    (market, range_start, range_end);

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

                CREATE TABLE IF NOT EXISTS trading_status_remediation_release_bindings (
                    run_id TEXT PRIMARY KEY,
                    consuming_data_version_id TEXT NOT NULL,
                    change_set_hash TEXT NOT NULL,
                    quality_report_id TEXT NOT NULL,
                    run_binding_hash TEXT NOT NULL,
                    checkpoint_hash TEXT NOT NULL,
                    candidate_manifest_hash TEXT NOT NULL,
                    written_key_hashes_hash TEXT NOT NULL,
                    physical_key_count INTEGER NOT NULL,
                    physical_key_fingerprint_hash TEXT NOT NULL,
                    physical_row_content_hash TEXT NOT NULL,
                    bound_at TEXT NOT NULL,
                    FOREIGN KEY (consuming_data_version_id)
                        REFERENCES data_versions (data_version_id),
                    FOREIGN KEY (quality_report_id)
                        REFERENCES data_quality_reports (quality_report_id)
                );

                CREATE INDEX IF NOT EXISTS idx_status_remediation_bindings_version
                    ON trading_status_remediation_release_bindings (
                        consuming_data_version_id, bound_at
                    );

                CREATE TRIGGER IF NOT EXISTS trg_status_remediation_bindings_no_update
                BEFORE UPDATE ON trading_status_remediation_release_bindings
                BEGIN
                    SELECT RAISE(ABORT, 'trading-status release bindings are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS trg_status_remediation_bindings_no_delete
                BEFORE DELETE ON trading_status_remediation_release_bindings
                BEGIN
                    SELECT RAISE(ABORT, 'trading-status release bindings are append-only');
                END;
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute(
                    "PRAGMA table_info(security_master_intervals)"
                ).fetchall()
            }
            if "is_active" not in columns:
                connection.execute(
                    "ALTER TABLE security_master_intervals "
                    "ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 "
                    "CHECK (is_active IN (0, 1))"
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
            connection.execute(
                """
                INSERT OR IGNORE INTO market_schema_migrations
                    (schema_version, description, applied_at)
                VALUES ('stage2.status-remediation-release-bindings.v1', ?, ?)
                """,
                (
                    "Add append-only trading-status remediation release bindings",
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

    def upsert_security_master_intervals(
        self,
        rows: Iterable[Mapping[str, Any]],
    ) -> int:
        """Persist validated point-in-time security-master intervals."""

        from data_platform.security_master_history import validate_security_master_intervals

        materialized = [dict(row) for row in rows]
        validation = validate_security_master_intervals(materialized)
        if not validation["ok"]:
            raise ValueError(f"security master interval validation failed: {validation['issues']}")
        payload = []
        for row in materialized:
            evidence = dict(row.get("evidence") or {})
            identity = {
                "symbol": _symbol(row.get("symbol")),
                "valid_from": str(row.get("valid_from") or "")[:10],
                "source": str(row.get("source") or "unknown"),
            }
            snapshot_ref = str(evidence.get("job_id") or "")
            interval_id = (
                _stable_id("security-master", {**identity, "snapshot_ref": snapshot_ref})
                if snapshot_ref
                else str(row.get("interval_id") or _stable_id("security-master", identity))
            )
            payload.append(
                (
                    interval_id,
                    identity["symbol"],
                    identity["valid_from"],
                    _optional_text(row.get("valid_to")),
                    str(row.get("name") or ""),
                    str(row.get("listing_status") or "unknown").strip().lower(),
                    1 if bool(row.get("risk_warning")) else 0,
                    str(row.get("available_at") or ""),
                    identity["source"],
                    str(row.get("source_observed_at") or _utc_now()),
                    str(row.get("source_payload_hash") or _payload_hash(evidence or row)),
                    _dump(evidence),
                )
            )
        active_keys = sorted({(row[1], row[8]) for row in payload})
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                UPDATE security_master_intervals SET is_active=0
                WHERE symbol=? AND source=? AND is_active=1
                """,
                active_keys,
            )
            connection.executemany(
                """
                INSERT INTO security_master_intervals (
                    interval_id, symbol, valid_from, valid_to, name, listing_status,
                    risk_warning, available_at, source, source_observed_at,
                    source_payload_hash, evidence_json, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(interval_id) DO UPDATE SET
                    valid_to=excluded.valid_to,
                    name=excluded.name,
                    listing_status=excluded.listing_status,
                    risk_warning=excluded.risk_warning,
                    available_at=excluded.available_at,
                    source_observed_at=excluded.source_observed_at,
                    source_payload_hash=excluded.source_payload_hash,
                    evidence_json=excluded.evidence_json,
                    is_active=1
                """,
                payload,
            )
        return len(payload)

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

    def inspect_trading_status_repair(
        self, *, symbol: str, trade_date: str,
    ) -> dict[str, Any]:
        """Classify one status/bar conflict without changing persisted facts."""

        code = _symbol(symbol)
        day = str(trade_date)[:10]
        with closing(self._connect(read_only=True)) as connection:
            status_row = connection.execute(
                """
                SELECT symbol, trade_date, status, is_tradable, suspension_reason,
                       expected_resume_date, source, source_observed_at,
                       source_payload_hash, evidence_json
                FROM security_trading_status_daily
                WHERE symbol=? AND trade_date=?
                """,
                (code, day),
            ).fetchone()
            price_row = connection.execute(
                """
                SELECT COUNT(*) AS bar_count,
                       SUM(CASE WHEN COALESCE(volume, 0)>0 THEN 1 ELSE 0 END)
                           AS positive_bar_count,
                       MAX(COALESCE(volume, 0)) AS max_volume,
                       GROUP_CONCAT(DISTINCT adjustment) AS adjustments
                FROM market_daily_prices
                WHERE symbol=? AND trade_date=?
                """,
                (code, day),
            ).fetchone()
        before = dict(status_row) if status_row is not None else None
        if before is not None:
            before["evidence"] = json.loads(str(before.pop("evidence_json") or "{}"))
            before["is_tradable"] = (
                None if before["is_tradable"] is None else bool(before["is_tradable"])
            )
        bars = {
            "bar_count": int(price_row["bar_count"] or 0),
            "positive_bar_count": int(price_row["positive_bar_count"] or 0),
            "max_volume": float(price_row["max_volume"] or 0),
            "adjustments": sorted(
                item for item in str(price_row["adjustments"] or "").split(",") if item
            ),
        }
        repairability, reason = _classify_trading_status_repair(day, before, bars)
        snapshot = {
            "symbol": code, "trade_date": day, "before": before, "bars": bars,
            "repairability": repairability, "reason": reason,
        }
        snapshot["evidence_fingerprint"] = _payload_hash(snapshot)
        snapshot["proposed_after"] = (
            {"status": "normal", "is_tradable": True}
            if repairability == "auto_repairable" else None
        )
        return snapshot

    def repair_trading_status_from_canonical_bar(
        self, *, symbol: str, trade_date: str, expected_fingerprint: str,
        issue_id: str, operator: str,
    ) -> dict[str, Any]:
        """Apply only a still-valid, deterministic positive-bar repair plan."""

        preview = self.inspect_trading_status_repair(
            symbol=symbol, trade_date=trade_date,
        )
        if preview["evidence_fingerprint"] != str(expected_fingerprint):
            raise ValueError("trading status evidence changed after preview")
        if preview["repairability"] != "auto_repairable":
            raise ValueError(
                f"trading status is not auto repairable: {preview['reason']}"
            )
        before = dict(preview["before"] or {})
        self.upsert_trading_statuses([{
            "symbol": preview["symbol"], "trade_date": preview["trade_date"],
            "status": "normal", "is_tradable": True,
            "source": "quality_remediation:canonical_positive_bar",
            "source_observed_at": _utc_now(),
            "evidence": {
                "issue_id": str(issue_id), "operator": str(operator or "local-user"),
                "repair_reason": preview["reason"],
                "canonical_bar_evidence": preview["bars"],
                "superseded_status_fact": before,
            },
        }])
        return {
            "status": "repaired", "before": before,
            "after": self.inspect_trading_status_repair(
                symbol=preview["symbol"], trade_date=preview["trade_date"],
            ),
        }

    def scan_trading_status_repair_candidates(
        self, *, after_symbol: str = "", after_trade_date: str = "",
        limit: int = 1_000, current_symbols_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Return a read-only, stable keyset page of repair candidates."""

        page_limit = max(1, min(int(limit), 10_000))
        current_sql = (
            "AND EXISTS (SELECT 1 FROM market_symbols current_symbol "
            "WHERE current_symbol.symbol=status.symbol "
            "AND current_symbol.listing_status='current')"
            if current_symbols_only else ""
        )
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""
                SELECT status.symbol, status.trade_date, status.status,
                       status.is_tradable, status.suspension_reason,
                       status.expected_resume_date, status.source,
                       status.source_observed_at, status.source_payload_hash,
                       status.evidence_json,
                       (SELECT COUNT(*) FROM market_daily_prices bars
                        WHERE bars.symbol=status.symbol
                          AND bars.trade_date=status.trade_date) AS bar_count,
                       (SELECT COUNT(*) FROM market_daily_prices positive_bars
                        WHERE positive_bars.symbol=status.symbol
                          AND positive_bars.trade_date=status.trade_date
                          AND COALESCE(positive_bars.volume, 0)>0) AS positive_bar_count,
                       (SELECT MAX(COALESCE(volume_bars.volume, 0))
                        FROM market_daily_prices volume_bars
                        WHERE volume_bars.symbol=status.symbol
                          AND volume_bars.trade_date=status.trade_date) AS max_volume,
                       (SELECT GROUP_CONCAT(DISTINCT adjustment_bars.adjustment)
                        FROM market_daily_prices adjustment_bars
                        WHERE adjustment_bars.symbol=status.symbol
                          AND adjustment_bars.trade_date=status.trade_date) AS adjustments
                FROM security_trading_status_daily status
                WHERE (
                    status.symbol>? OR (
                        status.symbol=? AND status.trade_date>?
                    )
                )
                  {current_sql}
                  AND (
                    status.is_tradable IS NULL
                    OR (
                        status.is_tradable=0 AND EXISTS (
                            SELECT 1 FROM market_daily_prices conflict_bar
                            WHERE conflict_bar.symbol=status.symbol
                              AND conflict_bar.trade_date=status.trade_date
                              AND COALESCE(conflict_bar.volume, 0)>0
                        )
                    )
                  )
                ORDER BY status.symbol, status.trade_date
                LIMIT ?
                """,
                (str(after_symbol), str(after_symbol), str(after_trade_date), page_limit),
            ).fetchall()
        return [_trading_status_candidate_from_row(row) for row in rows]

    def load_trading_status_repair_candidates(
        self, keys: Sequence[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        """Load only immutable-manifest keys; unrelated new candidates are excluded."""

        normalized = [
            (_symbol(symbol), str(trade_date)[:10])
            for symbol, trade_date in keys
        ]
        if not normalized:
            return []
        if len(normalized) > 1_000:
            raise ValueError("at most 1000 trading status repair keys can be loaded")
        values_sql = ",".join("(?, ?)" for _ in normalized)
        parameters = [value for pair in normalized for value in pair]
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""
                WITH requested(symbol, trade_date) AS (VALUES {values_sql})
                SELECT status.symbol, status.trade_date, status.status,
                       status.is_tradable, status.suspension_reason,
                       status.expected_resume_date, status.source,
                       status.source_observed_at, status.source_payload_hash,
                       status.evidence_json,
                       (SELECT COUNT(*) FROM market_daily_prices bars
                        WHERE bars.symbol=status.symbol
                          AND bars.trade_date=status.trade_date) AS bar_count,
                       (SELECT COUNT(*) FROM market_daily_prices positive_bars
                        WHERE positive_bars.symbol=status.symbol
                          AND positive_bars.trade_date=status.trade_date
                          AND COALESCE(positive_bars.volume, 0)>0) AS positive_bar_count,
                       (SELECT MAX(COALESCE(volume_bars.volume, 0))
                        FROM market_daily_prices volume_bars
                        WHERE volume_bars.symbol=status.symbol
                          AND volume_bars.trade_date=status.trade_date) AS max_volume,
                       (SELECT GROUP_CONCAT(DISTINCT adjustment_bars.adjustment)
                        FROM market_daily_prices adjustment_bars
                        WHERE adjustment_bars.symbol=status.symbol
                          AND adjustment_bars.trade_date=status.trade_date) AS adjustments
                FROM requested
                JOIN security_trading_status_daily status
                  ON status.symbol=requested.symbol
                 AND status.trade_date=requested.trade_date
                ORDER BY requested.symbol, requested.trade_date
                """,
                parameters,
            ).fetchall()
        return [_trading_status_candidate_from_row(row) for row in rows]

    def apply_trading_status_repair_batch(
        self, candidates: Sequence[Mapping[str, Any]], *, run_id: str,
        operator: str,
    ) -> dict[str, Any]:
        """Conditionally update one batch; changed status or bar evidence is skipped."""

        if not str(run_id).strip():
            raise ValueError("trading status repair run_id is required")
        if len(candidates) > 1_000:
            raise ValueError("at most 1000 trading status repair candidates can be applied")
        now = _utc_now()
        requested = 0
        written = 0
        written_keys: list[str] = []
        skipped_keys: list[str] = []
        written_key_digest = sha256()
        with closing(self._connect()) as connection, connection:
            for raw_candidate in candidates:
                candidate = dict(raw_candidate)
                before = dict(candidate.get("before") or {})
                bars = dict(candidate.get("bars") or {})
                expected_classification = _classify_trading_status_repair(
                    str(candidate.get("trade_date") or "")[:10], before, bars,
                )
                fingerprint_payload = {
                    "symbol": _symbol(candidate.get("symbol")),
                    "trade_date": str(candidate.get("trade_date") or "")[:10],
                    "before": before, "bars": bars,
                    "repairability": candidate.get("repairability"),
                    "reason": candidate.get("reason"),
                }
                if _payload_hash(fingerprint_payload) != str(
                    candidate.get("evidence_fingerprint") or ""
                ):
                    raise ValueError("trading status repair candidate fingerprint is invalid")
                if (
                    candidate.get("repairability"), candidate.get("reason")
                ) != expected_classification or expected_classification[0] != "auto_repairable":
                    continue
                requested += 1
                symbol = _symbol(candidate.get("symbol"))
                trade_date = str(candidate.get("trade_date") or "")[:10]
                original_null = before.get("is_tradable") is None
                evidence = {
                    "run_id": str(run_id),
                    "operator": str(operator or "administrator"),
                    "repair_reason": str(candidate.get("reason") or ""),
                    "candidate_fingerprint": str(
                        candidate.get("evidence_fingerprint") or ""
                    ),
                    "canonical_bar_evidence": bars,
                    "superseded_status_fact": before,
                }
                changed = connection.execute(
                    """
                    UPDATE security_trading_status_daily
                    SET status='normal', is_tradable=1,
                        suspension_reason=NULL, expected_resume_date=NULL,
                        source='admin_batch_remediation:canonical_positive_bar',
                        source_observed_at=?, source_payload_hash=?, evidence_json=?
                    WHERE symbol=? AND trade_date=? AND source_payload_hash=?
                      AND (
                        (?=1 AND is_tradable IS NULL)
                        OR (?=0 AND is_tradable=0)
                      )
                      AND (
                        SELECT COUNT(*) FROM market_daily_prices current_bars
                        WHERE current_bars.symbol=security_trading_status_daily.symbol
                          AND current_bars.trade_date=security_trading_status_daily.trade_date
                      )=?
                      AND (
                        SELECT COUNT(*) FROM market_daily_prices current_positive_bars
                        WHERE current_positive_bars.symbol=security_trading_status_daily.symbol
                          AND current_positive_bars.trade_date=security_trading_status_daily.trade_date
                          AND COALESCE(current_positive_bars.volume, 0)>0
                      )=?
                      AND COALESCE((
                        SELECT MAX(COALESCE(current_volume_bars.volume, 0))
                        FROM market_daily_prices current_volume_bars
                        WHERE current_volume_bars.symbol=security_trading_status_daily.symbol
                          AND current_volume_bars.trade_date=security_trading_status_daily.trade_date
                      ), 0)=?
                    """,
                    (
                        now, _payload_hash(evidence), _dump(evidence), symbol, trade_date,
                        str(before.get("source_payload_hash") or ""),
                        int(original_null), int(original_null),
                        int(bars.get("bar_count") or 0),
                        int(bars.get("positive_bar_count") or 0),
                        float(bars.get("max_volume") or 0),
                    ),
                ).rowcount
                key = f"{symbol}|{trade_date}"
                if changed:
                    written += 1
                    written_keys.append(key)
                    written_key_digest.update(key.encode("ascii"))
                else:
                    skipped_keys.append(key)
        return {
            "requested": requested, "written": written,
            "skipped": requested - written,
            "written_keys": written_keys,
            "skipped_keys": skipped_keys,
            "skipped_key_samples": skipped_keys[:100],
            "written_key_hash": written_key_digest.hexdigest(),
        }

    def inspect_admin_trading_status_change_set(
        self, *, excluded_run_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Return the exact current administrator-written rows not in a base release.

        The result is intentionally derived from the current physical rows rather
        than from checkpoint counters.  A later remediation of the same key therefore
        replaces the earlier run in the next aggregate change set.
        """

        excluded = {
            str(run_id).strip()
            for run_id in excluded_run_ids
            if str(run_id).strip()
        }
        key_digest = sha256()
        row_digest = sha256()
        included_key_digest = sha256()
        included_row_digest = sha256()
        exact_keys: list[str] = []
        included_key_count = 0
        included_key_samples: list[str] = []
        run_ids: set[str] = set()
        physical_run_ids: set[str] = set()
        physical_run_key_counts: dict[str, int] = {}
        physical_run_fingerprint_digests: dict[str, Any] = {}
        physical_run_row_digests: dict[str, Any] = {}
        run_key_counts: dict[str, int] = {}
        symbols: set[str] = set()
        dates: list[str] = []
        invalid_evidence: list[dict[str, Any]] = []
        with closing(self._connect(read_only=True)) as connection:
            cursor = connection.execute(
                """
                SELECT symbol, trade_date, status, is_tradable,
                       suspension_reason, expected_resume_date, source,
                       source_observed_at, source_payload_hash, evidence_json
                FROM security_trading_status_daily
                WHERE source='admin_batch_remediation:canonical_positive_bar'
                ORDER BY symbol, trade_date
                """
            )
            for row in cursor:
                evidence = _decode_json(str(row["evidence_json"] or "{}"))
                run_id = str(
                    evidence.get("run_id") if isinstance(evidence, Mapping) else ""
                ).strip()
                candidate_fingerprint = str(
                    evidence.get("candidate_fingerprint")
                    if isinstance(evidence, Mapping) else ""
                ).strip()
                key = f"{row['symbol']}|{row['trade_date']}"
                if not run_id or not candidate_fingerprint:
                    invalid_evidence.append({
                        "key": key,
                        "reason": (
                            "admin remediation row is missing evidence.run_id or "
                            "evidence.candidate_fingerprint"
                        ),
                    })
                    continue
                physical_run_ids.add(run_id)
                physical_run_key_counts[run_id] = (
                    physical_run_key_counts.get(run_id, 0) + 1
                )
                run_fingerprint_digest = physical_run_fingerprint_digests.setdefault(
                    run_id, sha256(),
                )
                run_fingerprint_digest.update((
                    _dump({
                        "key": key,
                        "candidate_fingerprint": candidate_fingerprint,
                    }) + "\n"
                ).encode("utf-8"))
                descriptor = {
                    "symbol": str(row["symbol"]),
                    "trade_date": str(row["trade_date"]),
                    "status": str(row["status"]),
                    "is_tradable": (
                        None if row["is_tradable"] is None
                        else int(row["is_tradable"])
                    ),
                    "suspension_reason": row["suspension_reason"],
                    "expected_resume_date": row["expected_resume_date"],
                    "source": str(row["source"]),
                    "source_observed_at": str(row["source_observed_at"]),
                    "source_payload_hash": str(row["source_payload_hash"]),
                    "evidence": evidence,
                }
                encoded_key = (_dump(key) + "\n").encode("utf-8")
                encoded_row = (_dump(descriptor) + "\n").encode("utf-8")
                physical_run_row_digests.setdefault(run_id, sha256()).update(
                    encoded_row
                )
                if run_id in excluded:
                    included_key_digest.update(encoded_key)
                    included_row_digest.update(encoded_row)
                    included_key_count += 1
                    if len(included_key_samples) < 20:
                        included_key_samples.append(key)
                    continue
                key_digest.update(encoded_key)
                row_digest.update(encoded_row)
                exact_keys.append(key)
                run_ids.add(run_id)
                run_key_counts[run_id] = run_key_counts.get(run_id, 0) + 1
                symbols.add(str(row["symbol"]))
                dates.append(str(row["trade_date"]))
        return {
            "source": "admin_batch_remediation:canonical_positive_bar",
            "scope": "all_symbols",
            "excluded_run_ids": sorted(excluded),
            "included_key_count": included_key_count,
            "included_key_hash": included_key_digest.hexdigest(),
            "included_row_content_hash": included_row_digest.hexdigest(),
            "included_key_samples": included_key_samples,
            "physical_run_ids": sorted(physical_run_ids),
            "physical_run_key_counts": dict(sorted(physical_run_key_counts.items())),
            "physical_run_key_fingerprint_hashes": {
                run_id: digest.hexdigest()
                for run_id, digest in sorted(physical_run_fingerprint_digests.items())
            },
            "physical_run_row_content_hashes": {
                run_id: digest.hexdigest()
                for run_id, digest in sorted(physical_run_row_digests.items())
            },
            "run_ids": sorted(run_ids),
            "run_count": len(run_ids),
            "run_key_counts": dict(sorted(run_key_counts.items())),
            "key_count": len(exact_keys),
            "exact_keys": exact_keys,
            "key_hash": key_digest.hexdigest(),
            "row_content_hash": row_digest.hexdigest(),
            "symbol_count": len(symbols),
            "min_date": min(dates) if dates else None,
            "max_date": max(dates) if dates else None,
            "invalid_evidence_count": len(invalid_evidence),
            "invalid_evidence_samples": invalid_evidence[:20],
        }

    def inspect_trading_status_member_content(self) -> dict[str, Any]:
        """Hash the complete physical trading-status member in canonical key order."""

        with closing(self._connect(read_only=True)) as connection:
            return self._inspect_trading_status_member_content(connection)

    @staticmethod
    def _inspect_trading_status_member_content(
        connection: sqlite3.Connection,
    ) -> dict[str, Any]:
        digest = sha256()
        row_count = 0
        symbols: set[str] = set()
        min_date: str | None = None
        max_date: str | None = None
        cursor = connection.execute(
            """
            SELECT symbol, trade_date, status, is_tradable,
                   suspension_reason, expected_resume_date, source,
                   source_observed_at, source_payload_hash, evidence_json
            FROM security_trading_status_daily
            ORDER BY symbol, trade_date
            """
        )
        for row in cursor:
            trade_date = str(row["trade_date"])
            descriptor = {
                "symbol": str(row["symbol"]),
                "trade_date": trade_date,
                "status": str(row["status"]),
                "is_tradable": (
                    None if row["is_tradable"] is None
                    else int(row["is_tradable"])
                ),
                "suspension_reason": row["suspension_reason"],
                "expected_resume_date": row["expected_resume_date"],
                "source": str(row["source"]),
                "source_observed_at": str(row["source_observed_at"]),
                "source_payload_hash": str(row["source_payload_hash"]),
                "evidence": _decode_json(str(row["evidence_json"] or "{}")),
            }
            digest.update((_dump(descriptor) + "\n").encode("utf-8"))
            row_count += 1
            symbols.add(str(row["symbol"]))
            min_date = trade_date if min_date is None else min(min_date, trade_date)
            max_date = trade_date if max_date is None else max(max_date, trade_date)
        return {
            "dataset": "security_trading_status_daily",
            "adjustment": "",
            "row_count": row_count,
            "symbol_count": len(symbols),
            "min_date": min_date,
            "max_date": max_date,
            "content_hash": digest.hexdigest(),
            "hash_semantics": "canonical_physical_rows_v1",
        }

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

    def begin_global_index_release(
        self, *, release_id: str, job_id: str,
        start_trade_date: str, target_trade_date: str,
    ) -> dict[str, Any]:
        """Create or reopen the lightweight audit release owned by one sync job."""

        self.ensure_schema()
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO global_index_releases (
                    release_id, job_id, start_trade_date, target_trade_date,
                    status, quality_rule_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'validating', ?, ?, ?)
                ON CONFLICT(release_id) DO UPDATE SET
                    status='validating', updated_at=excluded.updated_at,
                    published_at=NULL
                """,
                (
                    str(release_id), str(job_id), str(start_trade_date)[:10],
                    str(target_trade_date)[:10],
                    GLOBAL_INDEX_QUALITY_RULE_VERSION, now, now,
                ),
            )
        return self.get_global_index_release(job_id=job_id)

    def append_global_index_prices(
        self, rows: Iterable[Mapping[str, Any]], *, release_id: str,
        index_symbol: str, market: str, start_trade_date: str,
        target_trade_date: str,
        runtime_config: Mapping[str, Any] | None = None,
        calendar_range_start: str | None = None,
        calendar_range_end: str | None = None,
    ) -> dict[str, Any]:
        """Validate and append bars, rejecting any change to an existing history row."""

        self.ensure_schema()
        symbol = str(index_symbol or "").strip().upper()
        market_code = str(market or "").strip().upper()
        start = str(start_trade_date)[:10]
        target = str(target_trade_date)[:10]
        normalized, quality_issues = self._normalize_global_index_rows(
            rows, index_symbol=symbol, start_trade_date=start,
            target_trade_date=target,
        )
        source = str(normalized[0]["source"] if normalized else "unknown")
        content_hash = _payload_hash(normalized)
        dates = [str(row["trade_date"]) for row in normalized]
        min_date = min(dates) if dates else None
        max_date = max(dates) if dates else None
        conflict_details: list[dict[str, Any]] = []
        inserted = 0
        unchanged = 0
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            existing: dict[str, sqlite3.Row] = {}
            if dates:
                existing = {
                    str(row["trade_date"]): row
                    for row in connection.execute(
                        """
                        SELECT * FROM market_index_daily_prices
                        WHERE index_symbol=? AND trade_date BETWEEN ? AND ?
                        """,
                        (symbol, min_date, max_date),
                    ).fetchall()
                }
            pending: list[tuple[Any, ...]] = []
            for row in normalized:
                current = existing.get(str(row["trade_date"]))
                if current is None:
                    pending.append((
                        symbol, row["trade_date"], row["open"], row["high"],
                        row["low"], row["close"], row["volume"], row["amount"],
                        row["source"], row["source_observed_at"],
                        row["source_payload_hash"],
                    ))
                    continue
                differences = [
                    field for field in (
                        "open", "high", "low", "close", "volume", "amount"
                    )
                    if not _same_optional_number(current[field], row[field])
                ]
                if differences:
                    conflict_details.append({
                        "trade_date": row["trade_date"],
                        "fields": differences,
                    })
                else:
                    unchanged += 1
            if conflict_details:
                quality_issues.append({
                    "code": "historical_value_conflict",
                    "count": len(conflict_details),
                    "examples": conflict_details[:20],
                })
            status = "rejected" if quality_issues else "passed"
            if status == "passed":
                if pending:
                    connection.executemany(
                    """
                    INSERT INTO market_index_daily_prices (
                        index_symbol, trade_date, open, high, low, close,
                        volume, amount, source, source_observed_at,
                        source_payload_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        pending,
                    )
                    inserted = len(pending)
                session_rows = [
                    (market_code, row["trade_date"], row["source"], now, now)
                    for row in normalized
                ]
                connection.executemany(
                    """
                    INSERT INTO global_index_market_sessions (
                        market, trade_date, source, first_observed_at,
                        last_observed_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(market, trade_date) DO UPDATE SET
                        source=excluded.source,
                        last_observed_at=excluded.last_observed_at
                    """,
                    session_rows,
                )
            if status == "passed":
                connection.execute(
                    """
                    INSERT INTO global_index_calendar_observations (
                        release_id, index_symbol, market, range_start,
                        range_end, source, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(release_id, index_symbol) DO UPDATE SET
                        market=excluded.market, range_start=excluded.range_start,
                        range_end=excluded.range_end, source=excluded.source,
                        observed_at=excluded.observed_at
                    """,
                    (
                        release_id, symbol, market_code,
                        str(calendar_range_start or start)[:10],
                        str(calendar_range_end or target)[:10], source, now,
                    ),
                )
            quality = {
                "rule_version": GLOBAL_INDEX_QUALITY_RULE_VERSION,
                "status": status,
                "issues": quality_issues,
                "append_only": True,
                "historical_rows_updated": 0,
                "runtime_config": dict(runtime_config or {}),
            }
            connection.execute(
                """
                INSERT INTO global_index_release_attempts (
                    attempt_id, release_id, index_symbol, status,
                    received_rows, inserted_rows, unchanged_rows, conflict_rows,
                    quality_json, content_hash, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"gira-{uuid.uuid4().hex}", release_id, symbol, status,
                    len(normalized), inserted, unchanged, len(conflict_details),
                    _dump(quality), content_hash, now,
                ),
            )
            connection.execute(
                """
                INSERT INTO global_index_release_items (
                    release_id, index_symbol, market, source, status,
                    received_rows, inserted_rows, unchanged_rows, conflict_rows,
                    min_trade_date, max_trade_date, quality_json, content_hash,
                    recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id, index_symbol) DO UPDATE SET
                    market=excluded.market, source=excluded.source,
                    status=excluded.status, received_rows=excluded.received_rows,
                    inserted_rows=excluded.inserted_rows,
                    unchanged_rows=excluded.unchanged_rows,
                    conflict_rows=excluded.conflict_rows,
                    min_trade_date=excluded.min_trade_date,
                    max_trade_date=excluded.max_trade_date,
                    quality_json=excluded.quality_json,
                    content_hash=excluded.content_hash,
                    recorded_at=excluded.recorded_at
                """,
                (
                    release_id, symbol, market_code, source, status,
                    len(normalized), inserted, unchanged, len(conflict_details),
                    min_date, max_date, _dump(quality), content_hash, now,
                ),
            )
            self._refresh_global_index_release_summary(connection, release_id, now)
        result = {
            "release_id": release_id, "index_symbol": symbol,
            "market": market_code, "status": status,
            "received_rows": len(normalized), "inserted_rows": inserted,
            "unchanged_rows": unchanged,
            "conflict_rows": len(conflict_details), "quality": quality,
            "content_hash": content_hash,
        }
        if conflict_details:
            raise GlobalIndexHistoryConflict(
                f"append-only history conflict: {symbol}: "
                f"{len(conflict_details)} row(s) differ"
            )
        if quality_issues:
            raise GlobalIndexQualityError(
                f"global-index quality check failed: {symbol}: "
                + ", ".join(str(item["code"]) for item in quality_issues)
            )
        return result

    @staticmethod
    def _normalize_global_index_rows(
        rows: Iterable[Mapping[str, Any]], *, index_symbol: str,
        start_trade_date: str, target_trade_date: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        normalized: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        seen: set[str] = set()
        for position, source_row in enumerate(rows):
            row = dict(source_row)
            symbol = str(row.get("index_symbol") or "").strip().upper()
            trade_date = str(row.get("trade_date") or "")[:10]
            row_issues: list[str] = []
            if symbol != index_symbol:
                row_issues.append("symbol_mismatch")
            try:
                datetime.fromisoformat(trade_date)
            except ValueError:
                row_issues.append("invalid_trade_date")
            if trade_date in seen:
                row_issues.append("duplicate_trade_date")
            seen.add(trade_date)
            if trade_date < start_trade_date or trade_date > target_trade_date:
                row_issues.append("date_outside_requested_range")
            values: dict[str, float | None] = {}
            for field in ("open", "high", "low", "close", "volume", "amount"):
                try:
                    values[field] = _optional_float(row.get(field))
                except (TypeError, ValueError):
                    values[field] = None
                    row_issues.append(f"invalid_{field}")
            for field in ("open", "high", "low", "close"):
                value = values[field]
                if value is None or not math.isfinite(value) or value <= 0:
                    row_issues.append(f"invalid_{field}")
            for field in ("volume", "amount"):
                value = values[field]
                if value is not None and (not math.isfinite(value) or value < 0):
                    row_issues.append(f"invalid_{field}")
            if not any(item.startswith("invalid_") for item in row_issues):
                if values["high"] < max(values["open"], values["close"], values["low"]):
                    row_issues.append("high_below_ohlc")
                if values["low"] > min(values["open"], values["close"], values["high"]):
                    row_issues.append("low_above_ohlc")
            if row_issues:
                issues.append({
                    "code": "invalid_row", "position": position,
                    "trade_date": trade_date, "reasons": row_issues,
                })
            evidence = {**row, **values, "index_symbol": index_symbol,
                        "trade_date": trade_date}
            normalized.append({
                **evidence,
                "source": str(row.get("source") or "unknown"),
                "source_observed_at": str(
                    row.get("source_observed_at") or _utc_now()
                ),
                "source_payload_hash": str(
                    row.get("source_payload_hash") or _payload_hash(evidence)
                ),
            })
        if not normalized:
            issues.append({"code": "empty_batch"})
        return normalized, issues

    @staticmethod
    def _refresh_global_index_release_summary(
        connection: sqlite3.Connection, release_id: str, now: str,
    ) -> None:
        summary = connection.execute(
            """
            SELECT COUNT(*) item_count,
                   SUM(CASE WHEN status='passed' THEN 1 ELSE 0 END) passed,
                   SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) rejected,
                   SUM(inserted_rows) inserted,
                   SUM(unchanged_rows) unchanged,
                   SUM(conflict_rows) conflicts
            FROM global_index_release_items WHERE release_id=?
            """,
            (release_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE global_index_releases SET
                item_count=?, passed_items=?, rejected_items=?,
                inserted_rows=?, unchanged_rows=?, conflict_rows=?, updated_at=?
            WHERE release_id=?
            """,
            (
                int(summary["item_count"] or 0), int(summary["passed"] or 0),
                int(summary["rejected"] or 0), int(summary["inserted"] or 0),
                int(summary["unchanged"] or 0), int(summary["conflicts"] or 0),
                now, release_id,
            ),
        )

    def finalize_global_index_release(
        self, *, release_id: str, status: str,
    ) -> dict[str, Any]:
        allowed = {"published", "partial_failure", "failed", "stopped"}
        if status not in allowed:
            status = "failed"
        now = _utc_now()
        self.ensure_schema()
        with closing(self._connect()) as connection, connection:
            self._refresh_global_index_release_summary(connection, release_id, now)
            row = connection.execute(
                "SELECT rejected_items FROM global_index_releases WHERE release_id=?",
                (release_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"global-index release not found: {release_id}")
            if status == "published" and int(row["rejected_items"] or 0):
                status = "partial_failure"
            connection.execute(
                """
                UPDATE global_index_releases
                SET status=?, updated_at=?, published_at=? WHERE release_id=?
                """,
                (status, now, now if status == "published" else None, release_id),
            )
            job_id = connection.execute(
                "SELECT job_id FROM global_index_releases WHERE release_id=?",
                (release_id,),
            ).fetchone()["job_id"]
        return self.get_global_index_release(job_id=str(job_id))

    def get_global_index_release(self, *, job_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            release = connection.execute(
                "SELECT * FROM global_index_releases WHERE job_id=?", (job_id,)
            ).fetchone()
            if release is None:
                return {"status": "not_found", "job_id": job_id}
            items = connection.execute(
                """
                SELECT * FROM global_index_release_items
                WHERE release_id=? ORDER BY market, index_symbol
                """,
                (release["release_id"],),
            ).fetchall()
            attempts = connection.execute(
                """
                SELECT * FROM global_index_release_attempts
                WHERE release_id=? ORDER BY recorded_at, attempt_id
                """,
                (release["release_id"],),
            ).fetchall()
        payload_items = []
        for row in items:
            item = dict(row)
            item["quality"] = json.loads(str(item.pop("quality_json") or "{}"))
            payload_items.append(item)
        payload_attempts = []
        for row in attempts:
            attempt = dict(row)
            attempt["quality"] = json.loads(
                str(attempt.pop("quality_json") or "{}")
            )
            payload_attempts.append(attempt)
        return {
            **dict(release), "items": payload_items,
            "attempts": payload_attempts,
        }

    def global_index_calendar_dates(
        self, *, market: str, start_trade_date: str, target_trade_date: str,
    ) -> list[str]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """
                SELECT trade_date FROM global_index_market_sessions
                WHERE market=? AND trade_date BETWEEN ? AND ?
                ORDER BY trade_date
                """,
                (str(market).upper(), start_trade_date, target_trade_date),
            ).fetchall()
        return [str(row["trade_date"]) for row in rows]

    def global_index_calendar_covers(
        self, *, market: str, start_trade_date: str, target_trade_date: str,
    ) -> bool:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """
                SELECT range_start, range_end
                FROM global_index_calendar_observations
                WHERE market=? AND range_end>=? AND range_start<=?
                ORDER BY range_start, range_end
                """,
                (str(market).upper(), start_trade_date, target_trade_date),
            ).fetchall()
        cursor = start_trade_date
        for row in rows:
            range_start = str(row["range_start"])
            range_end = str(row["range_end"])
            if range_start > cursor:
                return False
            if range_end >= target_trade_date:
                return True
            cursor = (
                datetime.fromisoformat(range_end).date() + timedelta(days=1)
            ).isoformat()
        return False

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

    def fetch_current_published_data_version(self) -> dict[str, Any]:
        """Return the one live published release, never a superseded fallback."""

        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """
                SELECT * FROM data_versions
                WHERE status='published'
                ORDER BY published_at DESC, created_at DESC, data_version_id DESC
                """
            ).fetchall()
            if not rows:
                return {"status": "not_found", "data_version_id": None, "members": []}
            if len(rows) != 1:
                raise ValueError("exactly one published data version is required")
            version = rows[0]
            members = connection.execute(
                """
                SELECT * FROM data_version_members
                WHERE data_version_id=? ORDER BY dataset, adjustment
                """,
                (version["data_version_id"],),
            ).fetchall()
        return {**dict(version), "members": [dict(row) for row in members]}

    def fetch_trading_status_remediation_release_bindings(
        self,
    ) -> list[dict[str, Any]]:
        """Read the durable, append-only run-consumption ledger."""

        with closing(self._connect(read_only=True)) as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table'
                  AND name='trading_status_remediation_release_bindings'
                """
            ).fetchone()
            if exists is None:
                return []
            rows = connection.execute(
                """
                SELECT * FROM trading_status_remediation_release_bindings
                ORDER BY bound_at, run_id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def publish_trading_status_correction_version(
        self,
        *,
        as_of_trade_date: str,
        quality_report_id: str,
        expected_quality_report_hash: str,
        change_set_hash: str,
        run_bindings: Sequence[Mapping[str, Any]],
        members: Sequence[Mapping[str, Any]],
        expected_parent_version_id: str,
        expected_parent_manifest_hash: str,
        expected_trading_status_content_hash: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """CAS-publish a correction that changes only the trading-status member.

        Unlike ``publish_data_version`` this path cannot republish an old version:
        idempotency is accepted only when the exact target is still the sole live
        published release.  Physical trading-status rows are hashed again inside
        the same write transaction that advances the release pointer.
        """

        self.ensure_schema()
        normalized_members = [_normalize_member(member) for member in members]
        if not normalized_members:
            raise ValueError("data version requires at least one member")
        if any(member["quality_status"] != "passed" for member in normalized_members):
            raise ValueError("all published data version members must pass quality")
        member_keys = [
            (member["dataset"], member["adjustment"])
            for member in normalized_members
        ]
        if len(member_keys) != len(set(member_keys)):
            raise ValueError("data version member keys must be unique")
        status_key = ("security_trading_status_daily", "")
        if member_keys.count(status_key) != 1:
            raise ValueError("correction release requires one trading-status member")
        expected_change_set_hash = str(change_set_hash or "").lower()
        if not _is_sha256(expected_change_set_hash):
            raise ValueError("correction change-set hash must be SHA-256")
        normalized_run_bindings = sorted(
            [_normalize_remediation_release_binding(item) for item in run_bindings],
            key=lambda item: item["run_id"],
        )
        if not normalized_run_bindings:
            raise ValueError("correction release requires at least one remediation run")
        if len({item["run_id"] for item in normalized_run_bindings}) != len(
            normalized_run_bindings
        ):
            raise ValueError("correction remediation run bindings must be unique")
        manifest = {
            "as_of_trade_date": str(as_of_trade_date),
            "quality_report_id": str(quality_report_id),
            "members": sorted(
                normalized_members,
                key=lambda item: (item["dataset"], item["adjustment"]),
            ),
        }
        manifest_hash = sha256(_dump(manifest).encode("utf-8")).hexdigest()
        data_version_id = (
            f"scq-{str(as_of_trade_date).replace('-', '')}-{manifest_hash[:16]}"
        )
        expected_status_hash = str(expected_trading_status_content_hash or "").lower()
        if not _is_sha256(expected_status_hash):
            raise ValueError("expected trading-status content hash must be SHA-256")
        expected_report_hash = str(expected_quality_report_hash or "").lower()
        if not _is_sha256(expected_report_hash):
            raise ValueError("expected quality-report hash must be SHA-256")
        now = _utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            report = connection.execute(
                """
                SELECT status, payload_hash, payload_json FROM data_quality_reports
                WHERE quality_report_id=?
                """,
                (quality_report_id,),
            ).fetchone()
            if (
                report is None
                or str(report["status"]) != "passed"
                or str(report["payload_hash"]) != expected_report_hash
            ):
                raise ValueError(
                    "correction release quality report status or hash changed"
                )
            report_payload = _decode_json(str(report["payload_json"] or "{}"))
            report_change_set = dict(
                report_payload.get("change_set")
                if isinstance(report_payload, Mapping) else {}
                or {}
            )
            if str(report_change_set.get("change_set_hash") or "") != (
                expected_change_set_hash
            ):
                raise ValueError(
                    "correction release quality report change-set hash changed"
                )
            try:
                report_run_bindings = sorted(
                    [
                        _normalize_remediation_release_binding(item)
                        for item in report_change_set.get("run_bindings") or []
                    ],
                    key=lambda item: item["run_id"],
                )
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "correction release quality report run bindings are invalid"
                ) from error
            if report_run_bindings != normalized_run_bindings:
                raise ValueError(
                    "correction release quality report run bindings changed"
                )
            expected_ledger_bindings = [
                {
                    "run_id": item["run_id"],
                    "consuming_data_version_id": data_version_id,
                    "change_set_hash": expected_change_set_hash,
                    "quality_report_id": str(quality_report_id),
                    **item,
                }
                for item in normalized_run_bindings
            ]

            live_rows = connection.execute(
                "SELECT * FROM data_versions WHERE status='published'"
            ).fetchall()
            existing = connection.execute(
                "SELECT * FROM data_versions WHERE data_version_id=?",
                (data_version_id,),
            ).fetchone()
            if existing is not None:
                if str(existing["manifest_hash"]) != manifest_hash:
                    raise ValueError("data versions are immutable")
                if (
                    str(existing["status"]) != "published"
                    or len(live_rows) != 1
                    or str(live_rows[0]["data_version_id"]) != data_version_id
                ):
                    raise ValueError(
                        "idempotent correction target is not the current published version"
                    )
                stored_members = connection.execute(
                    """
                    SELECT * FROM data_version_members
                    WHERE data_version_id=? ORDER BY dataset, adjustment
                    """,
                    (data_version_id,),
                ).fetchall()
                stored_normalized = [
                    _normalize_member({
                        **dict(row),
                        "details": _decode_json(str(row["details_json"] or "{}")),
                    })
                    for row in stored_members
                ]
                if stored_normalized != manifest["members"]:
                    raise ValueError("idempotent correction members changed")
                stored_release_bindings = connection.execute(
                    """
                    SELECT * FROM trading_status_remediation_release_bindings
                    WHERE consuming_data_version_id=? ORDER BY run_id
                    """,
                    (data_version_id,),
                ).fetchall()
                if (
                    [_release_binding_identity(dict(row)) for row in stored_release_bindings]
                    != sorted(expected_ledger_bindings, key=lambda item: item["run_id"])
                ):
                    raise ValueError(
                        "idempotent correction remediation bindings conflict or are missing"
                    )
                target_status = next(
                    member for member in normalized_members
                    if (member["dataset"], member["adjustment"]) == status_key
                )
                physical = self._inspect_trading_status_member_content(connection)
                if (
                    str(physical["content_hash"]) != expected_status_hash
                    or str(target_status["content_hash"]) != expected_status_hash
                ):
                    raise ValueError(
                        "trading-status content hash drifted after correction publish"
                    )
                for field in ("row_count", "symbol_count", "min_date", "max_date"):
                    if target_status[field] != physical[field]:
                        raise ValueError(
                            f"trading-status member {field} differs from physical storage"
                        )
                connection.commit()
                result = self.fetch_data_version(data_version_id)
                result["publication_status"] = "already_published"
                return result

            if len(live_rows) != 1:
                raise ValueError("correction release requires exactly one published parent")
            parent = live_rows[0]
            if (
                str(parent["data_version_id"]) != str(expected_parent_version_id)
                or str(parent["manifest_hash"]) != str(expected_parent_manifest_hash)
            ):
                raise ValueError("published parent version changed; rerun closure recheck")
            if str(parent["as_of_trade_date"]) != str(as_of_trade_date):
                raise ValueError("correction release cannot change the parent cutoff")

            parent_rows = connection.execute(
                """
                SELECT * FROM data_version_members
                WHERE data_version_id=? ORDER BY dataset, adjustment
                """,
                (expected_parent_version_id,),
            ).fetchall()
            parent_members = [
                _normalize_member({
                    **dict(row),
                    "details": _decode_json(str(row["details_json"] or "{}")),
                })
                for row in parent_rows
            ]
            parent_by_key = {
                (item["dataset"], item["adjustment"]): item
                for item in parent_members
            }
            target_by_key = {
                (item["dataset"], item["adjustment"]): item
                for item in normalized_members
            }
            if set(parent_by_key) != set(target_by_key):
                raise ValueError("correction release cannot change member keys")
            changed_keys = [
                key for key in parent_by_key
                if parent_by_key[key] != target_by_key[key]
            ]
            if changed_keys != [status_key]:
                raise ValueError(
                    "correction release must change only the trading-status member"
                )

            physical = self._inspect_trading_status_member_content(connection)
            target_status = target_by_key[status_key]
            if (
                str(physical["content_hash"]) != expected_status_hash
                or str(target_status["content_hash"]) != expected_status_hash
            ):
                raise ValueError("trading-status content hash drifted before publish")
            for field in ("row_count", "symbol_count", "min_date", "max_date"):
                if target_status[field] != physical[field]:
                    raise ValueError(
                        f"trading-status member {field} differs from physical storage"
                    )

            run_ids = [item["run_id"] for item in expected_ledger_bindings]
            placeholders = ",".join("?" for _ in run_ids)
            consumed = connection.execute(
                f"""
                SELECT * FROM trading_status_remediation_release_bindings
                WHERE run_id IN ({placeholders}) ORDER BY run_id
                """,
                tuple(run_ids),
            ).fetchall()
            if consumed:
                raise ValueError(
                    "correction remediation run was already consumed by another release"
                )

            updated = connection.execute(
                """
                UPDATE data_versions SET status='superseded'
                WHERE data_version_id=? AND status='published' AND manifest_hash=?
                """,
                (expected_parent_version_id, expected_parent_manifest_hash),
            ).rowcount
            if updated != 1:
                raise ValueError("published parent version changed during correction publish")
            connection.execute(
                """
                INSERT INTO data_versions (
                    data_version_id, status, as_of_trade_date, parent_version_id,
                    quality_report_id, created_at, published_at, manifest_hash, notes
                ) VALUES (?, 'published', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data_version_id,
                    str(as_of_trade_date),
                    str(expected_parent_version_id),
                    str(quality_report_id),
                    now,
                    now,
                    manifest_hash,
                    str(notes),
                ),
            )
            connection.executemany(
                """
                INSERT INTO data_version_members (
                    data_version_id, dataset, adjustment, symbol_scope,
                    row_count, symbol_count, min_date, max_date, source,
                    sync_run_ref, content_hash, quality_status, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        data_version_id,
                        member["dataset"], member["adjustment"],
                        member["symbol_scope"], member["row_count"],
                        member["symbol_count"], member["min_date"],
                        member["max_date"], member["source"],
                        member["sync_run_ref"], member["content_hash"],
                        member["quality_status"], _dump(member["details"]),
                    )
                    for member in normalized_members
                ],
            )
            connection.executemany(
                """
                INSERT INTO trading_status_remediation_release_bindings (
                    run_id, consuming_data_version_id, change_set_hash,
                    quality_report_id, run_binding_hash, checkpoint_hash,
                    candidate_manifest_hash, written_key_hashes_hash,
                    physical_key_count, physical_key_fingerprint_hash,
                    physical_row_content_hash, bound_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["run_id"], item["consuming_data_version_id"],
                        item["change_set_hash"], item["quality_report_id"],
                        item["run_binding_hash"], item["checkpoint_hash"],
                        item["candidate_manifest_hash"],
                        item["written_key_hashes_hash"],
                        item["physical_key_count"],
                        item["physical_key_fingerprint_hash"],
                        item["physical_row_content_hash"], now,
                    )
                    for item in expected_ledger_bindings
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        result = self.fetch_data_version(data_version_id)
        result["publication_status"] = "published"
        return result

    def resolve_published_data_version(
        self,
        *,
        symbol: str,
        adjustment: str,
        start_date: str,
        end_date: str,
        benchmark: str | None = None,
        data_version_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        code = _symbol(symbol)
        mode = str(adjustment or "raw").lower()
        resolved = ResearchDataVersionResolver(self.database_path).resolve(
            data_version_id=data_version_id,
            required_members=(("market_daily_prices", mode),),
        )
        if resolved.get("status") != "ready":
            return {
                "status": "data_not_ready",
                "reason": resolved.get("reason") or "no_governed_data_version",
                "symbol": code,
                "adjustment": mode,
            }
        with closing(self._connect(read_only=True)) as connection:
            version = connection.execute(
                "SELECT * FROM data_versions WHERE data_version_id=?",
                (resolved["data_version_id"],),
            ).fetchone()
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
            "selection_policy": resolved.get("selection_policy"),
        }

    def fetch_trade_calendar(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        *,
        market: str = "CN",
    ) -> list[dict[str, Any]]:
        """Return governed trading-session facts in ascending date order."""

        self.ensure_schema()
        conditions = ["market=?"]
        parameters: list[Any] = [str(market or "CN")]
        if start_date:
            conditions.append("trade_date>=?")
            parameters.append(str(start_date))
        if end_date:
            conditions.append("trade_date<=?")
            parameters.append(str(end_date))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""SELECT market, trade_date, is_open, session_status, source,
                           source_observed_at
                    FROM market_trade_calendar
                    WHERE {' AND '.join(conditions)} ORDER BY trade_date""",
                parameters,
            ).fetchall()
        return [{**dict(row), "is_open": bool(row["is_open"])} for row in rows]

    def fetch_trading_status_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return point-in-time daily tradability evidence for one security."""

        self.ensure_schema()
        code = str(symbol).split(".")[0].strip()
        conditions = ["symbol=?"]
        parameters: list[Any] = [code]
        if start_date:
            conditions.append("trade_date>=?")
            parameters.append(str(start_date))
        if end_date:
            conditions.append("trade_date<=?")
            parameters.append(str(end_date))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""SELECT symbol, trade_date, status, is_tradable,
                           suspension_reason, expected_resume_date, source,
                           source_observed_at
                    FROM security_trading_status_daily
                    WHERE {' AND '.join(conditions)} ORDER BY trade_date""",
                parameters,
            ).fetchall()
        return [{**dict(row), "is_tradable": None if row["is_tradable"] is None else bool(row["is_tradable"])} for row in rows]

    def fetch_corporate_action_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return announced corporate actions without exposing future announcements."""

        self.ensure_schema()
        code = str(symbol).split(".")[0].strip()
        event_date = "COALESCE(ex_date, record_date, announcement_date)"
        conditions = ["symbol=?", f"{event_date} IS NOT NULL"]
        parameters: list[Any] = [code]
        if start_date:
            conditions.append(f"{event_date}>=?")
            parameters.append(str(start_date))
        if end_date:
            conditions.extend((f"{event_date}<=?", "(announcement_date IS NULL OR announcement_date<=?)"))
            parameters.extend((str(end_date), str(end_date)))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"""SELECT action_id, symbol, action_type AS event_type,
                           {event_date} AS event_date, announcement_date AS available_at,
                           record_date, ex_date, pay_date, cash_ratio, bonus_ratio,
                           transfer_ratio, status, source, source_observed_at
                    FROM corporate_action_events
                    WHERE {' AND '.join(conditions)} ORDER BY event_date, action_id""",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

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
            "security_master_intervals",
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
        from data_platform.maintenance_transaction import transaction_connection
        active = transaction_connection(self.database_path)
        if active is not None:
            return active
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


def _is_sha256(value: Any) -> bool:
    text = str(value or "").lower()
    return bool(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text)
    )


def _normalize_remediation_release_binding(
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("remediation run binding must be an object")
    run_id = str(raw.get("run_id") or "").strip()
    if (
        not run_id
        or len(run_id) > 80
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in run_id
        )
    ):
        raise ValueError("remediation run binding has an invalid run_id")
    supplied_binding_hash = str(raw.get("binding_hash") or "").lower()
    binding_payload = {
        str(key): value for key, value in raw.items()
        if str(key) != "binding_hash"
    }
    actual_binding_hash = sha256(
        _dump(binding_payload).encode("utf-8")
    ).hexdigest()
    if (
        not _is_sha256(supplied_binding_hash)
        or supplied_binding_hash != actual_binding_hash
    ):
        raise ValueError("remediation run binding hash changed")
    hash_fields = (
        "checkpoint_hash",
        "candidate_manifest_hash",
        "physical_key_fingerprint_hash",
        "physical_row_content_hash",
    )
    normalized_hashes = {
        field: str(raw.get(field) or "").lower() for field in hash_fields
    }
    if any(not _is_sha256(value) for value in normalized_hashes.values()):
        raise ValueError("remediation run binding evidence hash is invalid")
    written_key_hashes = [
        str(value or "").lower() for value in raw.get("written_key_hashes") or []
    ]
    if any(not _is_sha256(value) for value in written_key_hashes):
        raise ValueError("remediation written-key hash is invalid")
    physical_key_count = int(raw.get("physical_key_count") or 0)
    if physical_key_count < 0:
        raise ValueError("remediation physical key count is invalid")
    return {
        "run_id": run_id,
        "run_binding_hash": supplied_binding_hash,
        "checkpoint_hash": normalized_hashes["checkpoint_hash"],
        "candidate_manifest_hash": normalized_hashes["candidate_manifest_hash"],
        "written_key_hashes_hash": sha256(
            _dump(written_key_hashes).encode("utf-8")
        ).hexdigest(),
        "physical_key_count": physical_key_count,
        "physical_key_fingerprint_hash": normalized_hashes[
            "physical_key_fingerprint_hash"
        ],
        "physical_row_content_hash": normalized_hashes[
            "physical_row_content_hash"
        ],
    }


def _release_binding_identity(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(raw.get("run_id") or ""),
        "consuming_data_version_id": str(
            raw.get("consuming_data_version_id") or ""
        ),
        "change_set_hash": str(raw.get("change_set_hash") or ""),
        "quality_report_id": str(raw.get("quality_report_id") or ""),
        "run_binding_hash": str(raw.get("run_binding_hash") or ""),
        "checkpoint_hash": str(raw.get("checkpoint_hash") or ""),
        "candidate_manifest_hash": str(raw.get("candidate_manifest_hash") or ""),
        "written_key_hashes_hash": str(raw.get("written_key_hashes_hash") or ""),
        "physical_key_count": int(raw.get("physical_key_count") or 0),
        "physical_key_fingerprint_hash": str(
            raw.get("physical_key_fingerprint_hash") or ""
        ),
        "physical_row_content_hash": str(
            raw.get("physical_row_content_hash") or ""
        ),
    }


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


def _decode_json(value: str) -> Any:
    try:
        return json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {"_invalid_json": str(value)}


def _suspension_interval_excludes(trade_date: str, evidence: Mapping[str, Any]) -> bool:
    start = _evidence_date(
        evidence, "\u505c\u724c\u65f6\u95f4", "source_suspension_start_date",
    )
    end = _evidence_date(
        evidence, "\u505c\u724c\u622a\u6b62\u65f6\u95f4", "source_suspension_end_date",
    )
    resume = _evidence_date(evidence, "\u9884\u8ba1\u590d\u724c\u65f6\u95f4")
    day = str(trade_date)[:10]
    return bool(
        (start and day < start)
        or (end and day > end)
        or (resume and day >= resume)
    )


def _classify_trading_status_repair(
    trade_date: str, before: Mapping[str, Any] | None,
    bars: Mapping[str, Any],
) -> tuple[str, str]:
    if before is None:
        return "manual_evidence_required", "trading_status_fact_missing"
    if before.get("is_tradable") is True:
        return "already_consistent", "status_is_already_tradable"
    if int(bars.get("positive_bar_count") or 0) <= 0:
        return "manual_evidence_required", "positive_bar_evidence_required"
    if before.get("is_tradable") is None:
        return "auto_repairable", "positive_bar_resolves_unknown_tradability"
    if str(before.get("source") or "") == "canonical_history_gap_inference":
        return "auto_repairable", "positive_bar_refutes_gap_inference"
    if _suspension_interval_excludes(
        str(trade_date)[:10], dict(before.get("evidence") or {}),
    ):
        return "auto_repairable", "source_suspension_interval_excludes_trade_date"
    return "manual_evidence_required", "explicit_suspension_conflicts_with_positive_bar"


def _trading_status_candidate_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    before = {
        key: row[key]
        for key in (
            "symbol", "trade_date", "status", "is_tradable",
            "suspension_reason", "expected_resume_date", "source",
            "source_observed_at", "source_payload_hash",
        )
    }
    before["is_tradable"] = (
        None if before["is_tradable"] is None else bool(before["is_tradable"])
    )
    before["evidence"] = json.loads(str(row["evidence_json"] or "{}"))
    bars = {
        "bar_count": int(row["bar_count"] or 0),
        "positive_bar_count": int(row["positive_bar_count"] or 0),
        "max_volume": float(row["max_volume"] or 0),
        "adjustments": sorted(
            item for item in str(row["adjustments"] or "").split(",") if item
        ),
    }
    repairability, reason = _classify_trading_status_repair(
        str(row["trade_date"]), before, bars,
    )
    candidate = {
        "symbol": str(row["symbol"]), "trade_date": str(row["trade_date"]),
        "before": before, "bars": bars,
        "repairability": repairability, "reason": reason,
    }
    candidate["evidence_fingerprint"] = _payload_hash(candidate)
    return candidate


def _evidence_date(evidence: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = evidence.get(key)
        if value is None:
            continue
        digits = "".join(character for character in str(value) if character.isdigit())
        if len(digits) >= 8:
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


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


def _same_optional_number(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(
        float(left), float(right), rel_tol=1e-12, abs_tol=1e-12,
    )


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
