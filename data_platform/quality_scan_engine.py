"""Active, auditable data-quality discovery for the data center."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from data_platform.a_share_sync_scheduler import AShareSyncScheduler
from data_platform.providers.a_share_sqlite_repository import _normalize_symbol
from data_platform.task_ids import new_task_id


QUALITY_RULES: tuple[dict[str, str], ...] = (
    {
        "rule_id": "missing_open_day",
        "name": "交易日完整性",
        "description": "结合交易日历、证券生命周期和停牌状态发现应有但缺失的日线。",
    },
    {
        "rule_id": "ohlcv_validity",
        "name": "OHLCV 合法性",
        "description": "发现空值、负成交量/成交额以及最高价或最低价关系错误。",
    },
    {
        "rule_id": "adjustment_date_consistency",
        "name": "复权口径日期一致性",
        "description": "在各口径共同覆盖期内发现不复权、前复权、后复权日期不一致。",
    },
)
_RULE_IDS = {item["rule_id"] for item in QUALITY_RULES}
_ADJUSTMENTS = {"raw", "qfq", "hfq"}
_TERMINAL_SCAN_STATES = {"passed", "issues_found", "failed"}


class QualityScanEngine:
    """Run bounded rule packs and persist findings into the existing issue ledger."""

    def __init__(self, database_path: str | Path, scheduler: AShareSyncScheduler) -> None:
        self.database_path = Path(database_path)
        self.scheduler = scheduler
        self.ensure_schema()
        self._recover_interrupted_scans()

    def ensure_schema(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_quality_scan_jobs (
                    scan_id TEXT PRIMARY KEY,
                    parent_scan_id TEXT,
                    dataset TEXT NOT NULL,
                    date_from TEXT NOT NULL,
                    date_to TEXT NOT NULL,
                    scope TEXT NOT NULL CHECK (scope IN ('all_current','symbols')),
                    symbols_json TEXT NOT NULL,
                    adjustments_json TEXT NOT NULL,
                    rules_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('queued','running','passed','issues_found','failed')
                    ),
                    current_rule TEXT,
                    total_rules INTEGER NOT NULL,
                    completed_rules INTEGER NOT NULL DEFAULT 0,
                    scanned_rows INTEGER NOT NULL DEFAULT 0,
                    issues_found INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_quality_scan_jobs_created
                    ON data_quality_scan_jobs (created_at DESC);
                CREATE TABLE IF NOT EXISTS data_quality_scan_controls (
                    scan_id TEXT PRIMARY KEY,
                    pause_requested INTEGER NOT NULL DEFAULT 0 CHECK (pause_requested IN (0, 1)),
                    stop_requested INTEGER NOT NULL DEFAULT 0 CHECK (stop_requested IN (0, 1)),
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (scan_id) REFERENCES data_quality_scan_jobs (scan_id)
                );
                """
            )

    def _recover_interrupted_scans(self) -> None:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE data_quality_scan_jobs
                SET status='failed', current_rule=NULL, finished_at=?, updated_at=?,
                    last_error='service_restarted_before_scan_completed'
                WHERE status='running'
                """,
                (now, now),
            )
            connection.execute(
                "UPDATE data_quality_scan_controls SET pause_requested=0, stop_requested=0, updated_at=?",
                (now,),
            )

    @staticmethod
    def list_rules() -> list[dict[str, str]]:
        return [dict(item) for item in QUALITY_RULES]

    def create_scan(
        self, *, dataset: str, date_from: str, date_to: str, scope: str,
        symbols: Sequence[str], adjustments: Sequence[str], rules: Sequence[str],
        parent_scan_id: str = "",
    ) -> dict[str, Any]:
        config = self._validate_config(
            dataset=dataset, date_from=date_from, date_to=date_to, scope=scope,
            symbols=symbols, adjustments=adjustments, rules=rules,
        )
        now = _utc_now()
        scan_id = new_task_id("quality-scan")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_quality_scan_jobs (
                    scan_id, parent_scan_id, dataset, date_from, date_to, scope,
                    symbols_json, adjustments_json, rules_json, status,
                    current_rule, total_rules, completed_rules, scanned_rows,
                    issues_found, last_error, created_at, started_at, finished_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', NULL, ?, 0, 0, 0,
                          NULL, ?, NULL, NULL, ?)
                """,
                (
                    scan_id, parent_scan_id or None, config["dataset"],
                    config["date_from"], config["date_to"], config["scope"],
                    _dump(config["symbols"]), _dump(config["adjustments"]),
                    _dump(config["rules"]), len(config["rules"]), now, now,
                ),
            )
            connection.execute(
                "INSERT INTO data_quality_scan_controls (scan_id, pause_requested, stop_requested, updated_at) VALUES (?, 0, 0, ?)",
                (scan_id, now),
            )
        return self.get_scan(scan_id)

    def recheck(self, scan_id: str) -> dict[str, Any]:
        source = self.get_scan(scan_id)
        if source["status"] not in _TERMINAL_SCAN_STATES:
            raise ValueError("only a completed or failed quality scan can be rechecked")
        return self.create_scan(
            dataset=source["dataset"], date_from=source["date_from"],
            date_to=source["date_to"], scope=source["scope"],
            symbols=source["symbols"], adjustments=source["adjustments"],
            rules=source["rules"], parent_scan_id=scan_id,
        )

    def list_scans(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """SELECT jobs.*, COALESCE(controls.pause_requested, 0) AS pause_requested,
                          COALESCE(controls.stop_requested, 0) AS stop_requested
                   FROM data_quality_scan_jobs jobs
                   LEFT JOIN data_quality_scan_controls controls ON controls.scan_id=jobs.scan_id
                   ORDER BY jobs.created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self._scan_payload(row) for row in rows]

    def get_scan(self, scan_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                """SELECT jobs.*, COALESCE(controls.pause_requested, 0) AS pause_requested,
                          COALESCE(controls.stop_requested, 0) AS stop_requested
                   FROM data_quality_scan_jobs jobs
                   LEFT JOIN data_quality_scan_controls controls ON controls.scan_id=jobs.scan_id
                   WHERE jobs.scan_id=?""", (scan_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"quality scan not found: {scan_id}")
        return self._scan_payload(row)

    def run_scan(self, scan_id: str) -> dict[str, Any]:
        scan = self.get_scan(scan_id)
        if scan["status"] not in {"queued", "failed"}:
            raise ValueError(f"quality scan is not runnable from status={scan['status']}")
        self._update_scan(
            scan_id, status="running", current_rule="preparing", completed_rules=0,
            scanned_rows=0, issues_found=0, last_error=None,
            started_at=_utc_now(), finished_at=None,
        )
        self._set_control(scan_id, pause_requested=0, stop_requested=0)
        issue_ids: set[str] = set()
        completed_rules = 0
        scanned_rows = 0
        try:
            for rule_id in scan["rules"]:
                if not self._wait_until_runnable(scan_id):
                    return self._finish_stopped(scan_id, completed_rules, scanned_rows, len(issue_ids))
                self._update_scan(scan_id, current_rule=rule_id)
                findings, checked = self._run_rule(scan, rule_id)
                scanned_rows += checked
                for finding in findings:
                    issue_ids.add(self._upsert_issue(scan_id, finding))
                completed_rules += 1
                self._update_scan(
                    scan_id, completed_rules=completed_rules,
                    scanned_rows=scanned_rows, issues_found=len(issue_ids),
                )
                if not self._wait_until_runnable(scan_id):
                    return self._finish_stopped(scan_id, completed_rules, scanned_rows, len(issue_ids))
            corrected_count = self._close_resolved_parent_issues(scan, issue_ids)
            status = "issues_found" if issue_ids else "passed"
            self._update_scan(
                scan_id, status=status, current_rule=None,
                completed_rules=completed_rules, scanned_rows=scanned_rows,
                issues_found=len(issue_ids), finished_at=_utc_now(), last_error=None,
            )
            result = self.get_scan(scan_id)
            result["corrected_by_recheck"] = corrected_count
            return result
        except Exception as error:
            self._update_scan(
                scan_id, status="failed", current_rule=None,
                completed_rules=completed_rules, scanned_rows=scanned_rows,
                issues_found=len(issue_ids), finished_at=_utc_now(),
                last_error=f"{type(error).__name__}: {error}",
            )
            raise

    def request_pause(self, scan_id: str) -> dict[str, Any]:
        scan = self.get_scan(scan_id)
        if scan["status"] != "running":
            raise ValueError("only a running quality scan can be paused")
        self._set_control(scan_id, pause_requested=1)
        return self.get_scan(scan_id)

    def resume(self, scan_id: str) -> dict[str, Any]:
        scan = self.get_scan(scan_id)
        if scan["status"] != "running" or not scan.get("pause_requested"):
            raise ValueError("only a paused quality scan can be resumed")
        self._set_control(scan_id, pause_requested=0)
        return self.get_scan(scan_id)

    def request_stop(self, scan_id: str) -> dict[str, Any]:
        scan = self.get_scan(scan_id)
        if scan["status"] == "queued":
            self._update_scan(
                scan_id, status="failed", current_rule=None,
                finished_at=_utc_now(), last_error="stopped_by_user",
            )
            self._set_control(scan_id, pause_requested=0, stop_requested=1)
            return self.get_scan(scan_id)
        if scan["status"] != "running":
            raise ValueError("only a queued or running quality scan can be stopped")
        self._set_control(scan_id, pause_requested=0, stop_requested=1)
        return self.get_scan(scan_id)

    def _wait_until_runnable(self, scan_id: str) -> bool:
        while True:
            scan = self.get_scan(scan_id)
            if scan.get("stop_requested"):
                return False
            if not scan.get("pause_requested"):
                return True
            if scan.get("current_rule") != "paused":
                self._update_scan(scan_id, current_rule="paused")
            time.sleep(0.2)

    def _finish_stopped(
        self, scan_id: str, completed_rules: int, scanned_rows: int, issues_found: int,
    ) -> dict[str, Any]:
        self._update_scan(
            scan_id, status="failed", current_rule=None,
            completed_rules=completed_rules, scanned_rows=scanned_rows,
            issues_found=issues_found, finished_at=_utc_now(), last_error="stopped_by_user",
        )
        return self.get_scan(scan_id)

    def _set_control(self, scan_id: str, **updates: int) -> None:
        allowed = {"pause_requested", "stop_requested"}
        if not updates or set(updates) - allowed:
            raise ValueError("unsupported quality scan control")
        assignments = [f"{key}=?" for key in updates]
        values = [1 if int(updates[key]) else 0 for key in updates]
        assignments.append("updated_at=?")
        values.extend((_utc_now(), scan_id))
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO data_quality_scan_controls(
                    scan_id, pause_requested, stop_requested, updated_at
                ) VALUES (?, 0, 0, ?)
                """,
                (scan_id, _utc_now()),
            )
            changed = connection.execute(
                f"UPDATE data_quality_scan_controls SET {', '.join(assignments)} WHERE scan_id=?",
                values,
            ).rowcount
        if not changed:
            raise KeyError(f"quality scan control not found: {scan_id}")

    def _run_rule(
        self, scan: Mapping[str, Any], rule_id: str,
    ) -> tuple[Iterable[dict[str, Any]], int]:
        if rule_id == "missing_open_day":
            return self._detect_missing_open_days(scan)
        if rule_id == "ohlcv_validity":
            return self._detect_invalid_ohlcv(scan)
        if rule_id == "adjustment_date_consistency":
            return self._detect_adjustment_date_mismatch(scan)
        raise ValueError(f"unsupported quality rule: {rule_id}")

    def _detect_missing_open_days(
        self, scan: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], int]:
        tasks = self.scheduler.scan_gap_tasks(
            target_trade_date=str(scan["date_to"]),
            start_floor=str(scan["date_from"]),
            symbols=scan["symbols"] or None,
            all_current=scan["scope"] == "all_current",
            adjustments=scan["adjustments"],
        )
        findings = [
            {
                "dataset": "a_share_daily", "symbol": task["symbol"],
                "observation_at": task["first_missing_date"],
                "rule_id": "missing_open_day", "severity": "error",
                "field_name": "trade_date",
                "evidence": {
                    "adjustment": task["adjustment"],
                    "first_missing_date": task["first_missing_date"],
                    "last_missing_date": task["last_missing_date"],
                    "missing_date_count": task["missing_date_count"],
                    "scan_date_from": scan["date_from"],
                    "scan_date_to": scan["date_to"],
                },
            }
            for task in tasks
        ]
        return findings, sum(int(task["missing_date_count"]) for task in tasks)

    def _detect_invalid_ohlcv(
        self, scan: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], int]:
        scope_sql, scope_values = self._scope_sql(scan, alias="p")
        adjustments = list(scan["adjustments"])
        adjustment_sql = ",".join("?" for _ in adjustments)
        base_where = (
            f"p.trade_date BETWEEN ? AND ? AND p.adjustment IN ({adjustment_sql})"
            " AND NOT EXISTS ("
            "SELECT 1 FROM security_trading_status_daily trading_status "
            "WHERE trading_status.symbol=p.symbol "
            "AND trading_status.trade_date=p.trade_date "
            "AND trading_status.is_tradable=0)"
            f"{scope_sql}"
        )
        values: list[Any] = [scan["date_from"], scan["date_to"], *adjustments, *scope_values]
        invalid_where = """
            AND (
                p.open IS NULL OR p.high IS NULL OR p.low IS NULL OR p.close IS NULL
                OR p.volume IS NULL OR p.volume < 0 OR p.amount IS NULL OR p.amount < 0
                OR p.high < MAX(p.open, p.close, p.low)
                OR p.low > MIN(p.open, p.close, p.high)
            )
        """
        with closing(self._connect(read_only=True)) as connection:
            checked = int(connection.execute(
                f"SELECT COUNT(*) AS count FROM market_daily_prices p WHERE {base_where}",
                values,
            ).fetchone()["count"])
            rows = connection.execute(
                f"""
                SELECT p.* FROM market_daily_prices p
                WHERE {base_where} {invalid_where}
                ORDER BY p.trade_date, p.symbol, p.adjustment
                """,
                values,
            ).fetchall()
        findings: list[dict[str, Any]] = []
        for row in rows:
            fields = _invalid_ohlcv_fields(row)
            findings.append({
                "dataset": "a_share_daily", "symbol": str(row["symbol"]),
                "observation_at": str(row["trade_date"]),
                "rule_id": "ohlcv_validity", "severity": "error",
                "field_name": ",".join(fields),
                "evidence": {
                    "adjustment": str(row["adjustment"]),
                    "invalid_fields": fields,
                    "values": {name: row[name] for name in ("open", "high", "low", "close", "volume", "amount")},
                },
            })
        return findings, checked

    def _detect_adjustment_date_mismatch(
        self, scan: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], int]:
        adjustments = list(scan["adjustments"])
        if len(adjustments) < 2:
            return [], 0
        adjustment_sql = ",".join("?" for _ in adjustments)
        scope_sql, scope_values = self._scope_sql(scan, alias="p")
        values: list[Any] = [
            *adjustments, *scope_values, len(adjustments), scan["date_from"],
            scan["date_to"], *adjustments, len(adjustments),
        ]
        query = f"""
            WITH first_dates AS (
                SELECT p.symbol, p.adjustment, MIN(p.trade_date) AS first_date
                FROM market_daily_prices p
                WHERE p.adjustment IN ({adjustment_sql}) {scope_sql}
                GROUP BY p.symbol, p.adjustment
            ), common_coverage AS (
                SELECT symbol, MAX(first_date) AS common_start
                FROM first_dates GROUP BY symbol
                HAVING COUNT(DISTINCT adjustment)=?
            )
            SELECT p.symbol, p.trade_date,
                   GROUP_CONCAT(DISTINCT p.adjustment) AS present_adjustments
            FROM market_daily_prices p
            JOIN common_coverage c ON c.symbol=p.symbol
            WHERE p.trade_date BETWEEN MAX(?, c.common_start) AND ?
              AND p.adjustment IN ({adjustment_sql})
              AND NOT EXISTS (
                  SELECT 1 FROM security_trading_status_daily trading_status
                  WHERE trading_status.symbol=p.symbol
                    AND trading_status.trade_date=p.trade_date
                    AND trading_status.is_tradable=0
              )
            GROUP BY p.symbol, p.trade_date
            HAVING COUNT(DISTINCT p.adjustment) < ?
            ORDER BY p.trade_date, p.symbol
        """
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(query, values).fetchall()
        findings: list[dict[str, Any]] = []
        expected = set(adjustments)
        for row in rows:
            present = {item for item in str(row["present_adjustments"] or "").split(",") if item}
            missing = sorted(expected - present)
            findings.append({
                "dataset": "a_share_daily", "symbol": str(row["symbol"]),
                "observation_at": str(row["trade_date"]),
                "rule_id": "adjustment_date_consistency", "severity": "error",
                "field_name": "adjustment",
                "evidence": {
                    "expected_adjustments": sorted(expected),
                    "present_adjustments": sorted(present),
                    "missing_adjustments": missing,
                },
            })
        return findings, len(rows)

    def _scope_sql(
        self, scan: Mapping[str, Any], *, alias: str,
    ) -> tuple[str, list[str]]:
        if scan["scope"] == "all_current":
            return (
                f" AND EXISTS (SELECT 1 FROM market_symbols scope_symbol "
                f"WHERE scope_symbol.symbol={alias}.symbol AND scope_symbol.listing_status='current')",
                [],
            )
        symbols = list(scan["symbols"])
        return f" AND {alias}.symbol IN ({','.join('?' for _ in symbols)})", symbols

    def _upsert_issue(self, scan_id: str, finding: Mapping[str, Any]) -> str:
        evidence = dict(finding.get("evidence") or {})
        fingerprint = "|".join((
            str(finding.get("dataset") or ""), str(finding.get("symbol") or ""),
            str(finding.get("observation_at") or ""), str(finding.get("rule_id") or ""),
            str(finding.get("field_name") or ""), str(evidence.get("adjustment") or ""),
            ",".join(evidence.get("missing_adjustments") or ()),
        ))
        issue_id = f"dqi-scan-{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:24]}"
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_quality_issues (
                    issue_id, dataset, symbol, observation_at, rule_id, severity,
                    status, source, data_version_id, evidence_json, source_task_id,
                    field_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', 'quality_scan_engine', NULL, ?, ?, ?, ?, ?)
                ON CONFLICT(issue_id) DO UPDATE SET
                    severity=excluded.severity,
                    source=excluded.source,
                    evidence_json=excluded.evidence_json,
                    source_task_id=excluded.source_task_id,
                    field_name=excluded.field_name,
                    status=CASE
                        WHEN data_quality_issues.status IN ('corrected','superseded') THEN 'open'
                        ELSE data_quality_issues.status
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    issue_id, str(finding["dataset"]), str(finding.get("symbol") or "") or None,
                    str(finding.get("observation_at") or "") or None,
                    str(finding["rule_id"]), str(finding.get("severity") or "warning"),
                    _dump(evidence), scan_id, str(finding.get("field_name") or "") or None,
                    now, now,
                ),
            )
        return issue_id

    def _close_resolved_parent_issues(
        self, scan: Mapping[str, Any], current_issue_ids: set[str],
    ) -> int:
        parent_scan_id = str(scan.get("parent_scan_id") or "")
        if not parent_scan_id:
            return 0
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                """
                SELECT issue_id FROM data_quality_issues
                WHERE source_task_id=? AND status IN ('open','quarantined')
                """,
                (parent_scan_id,),
            ).fetchall()
            resolved = [str(row["issue_id"]) for row in rows if str(row["issue_id"]) not in current_issue_ids]
            for issue_id in resolved:
                connection.execute(
                    "UPDATE data_quality_issues SET status='corrected', updated_at=? WHERE issue_id=?",
                    (now, issue_id),
                )
                connection.execute(
                    """
                    INSERT INTO data_quality_dispositions (
                        disposition_id, issue_id, action, reason, operator,
                        related_task_id, related_issue_id, created_at
                    ) VALUES (?, ?, 'correct', ?, 'quality-scan-engine', ?, NULL, ?)
                    """,
                    (
                        f"dqd-{uuid.uuid4().hex}", issue_id,
                        "复查未再次发现该问题，自动标记为已修正", str(scan["scan_id"]), now,
                    ),
                )
        return len(resolved)

    def _update_scan(self, scan_id: str, **updates: Any) -> None:
        allowed = {
            "status", "current_rule", "completed_rules", "scanned_rows",
            "issues_found", "last_error", "started_at", "finished_at",
        }
        invalid = set(updates) - allowed
        if invalid:
            raise ValueError(f"unsupported scan update: {sorted(invalid)}")
        assignments = [f"{column}=?" for column in updates]
        values = [updates[column] for column in updates]
        assignments.append("updated_at=?")
        values.extend((_utc_now(), scan_id))
        with closing(self._connect()) as connection, connection:
            changed = connection.execute(
                f"UPDATE data_quality_scan_jobs SET {', '.join(assignments)} WHERE scan_id=?",
                values,
            ).rowcount
        if not changed:
            raise KeyError(f"quality scan not found: {scan_id}")

    @staticmethod
    def _validate_config(
        *, dataset: str, date_from: str, date_to: str, scope: str,
        symbols: Sequence[str], adjustments: Sequence[str], rules: Sequence[str],
    ) -> dict[str, Any]:
        if dataset != "a_share_daily":
            raise ValueError("P0 quality scanning currently supports only a_share_daily")
        start = date.fromisoformat(str(date_from)).isoformat()
        end = date.fromisoformat(str(date_to)).isoformat()
        if start > end:
            raise ValueError("date_from must not be later than date_to")
        normalized_scope = str(scope or "all_current")
        if normalized_scope not in {"all_current", "symbols"}:
            raise ValueError("scope must be all_current or symbols")
        normalized_symbols = list(dict.fromkeys(
            _normalize_symbol(str(item)) for item in symbols if str(item).strip()
        ))
        if normalized_scope == "symbols" and not normalized_symbols:
            raise ValueError("at least one symbol is required for symbol scope")
        if normalized_scope == "all_current":
            normalized_symbols = []
        normalized_adjustments = list(dict.fromkeys(str(item) for item in adjustments))
        if not normalized_adjustments or any(item not in _ADJUSTMENTS for item in normalized_adjustments):
            raise ValueError("adjustments must contain raw, qfq or hfq")
        normalized_rules = list(dict.fromkeys(str(item) for item in rules))
        if not normalized_rules or any(item not in _RULE_IDS for item in normalized_rules):
            raise ValueError("at least one supported quality rule is required")
        return {
            "dataset": dataset, "date_from": start, "date_to": end,
            "scope": normalized_scope, "symbols": normalized_symbols,
            "adjustments": normalized_adjustments, "rules": normalized_rules,
        }

    @staticmethod
    def _scan_payload(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["symbols"] = json.loads(str(payload.pop("symbols_json") or "[]"))
        payload["adjustments"] = json.loads(str(payload.pop("adjustments_json") or "[]"))
        payload["rules"] = json.loads(str(payload.pop("rules_json") or "[]"))
        payload["pause_requested"] = bool(payload.get("pause_requested"))
        payload["stop_requested"] = bool(payload.get("stop_requested"))
        payload["control_state"] = (
            "stopped" if payload.get("last_error") == "stopped_by_user"
            else "stopping" if payload["stop_requested"] and payload["status"] == "running"
            else ("paused" if payload.get("current_rule") == "paused" else "pausing")
            if payload["pause_requested"] and payload["status"] == "running"
            else payload["status"]
        )
        payload["progress_pct"] = (
            round(int(payload["completed_rules"]) * 100 / int(payload["total_rules"]))
            if int(payload["total_rules"]) else 0
        )
        return payload

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"file:{self.database_path.resolve().as_posix()}?mode=ro", uri=True,
                timeout=30,
            )
        else:
            connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection


def _invalid_ohlcv_fields(row: Mapping[str, Any]) -> list[str]:
    fields: list[str] = []
    for name in ("open", "high", "low", "close", "volume", "amount"):
        if row[name] is None:
            fields.append(name)
    if row["volume"] is not None and float(row["volume"]) < 0:
        fields.append("volume")
    if row["amount"] is not None and float(row["amount"]) < 0:
        fields.append("amount")
    prices = [row[name] for name in ("open", "high", "low", "close")]
    if all(value is not None for value in prices):
        if float(row["high"]) < max(float(row["open"]), float(row["close"]), float(row["low"])):
            fields.append("high")
        if float(row["low"]) > min(float(row["open"]), float(row["close"]), float(row["high"])):
            fields.append("low")
    return list(dict.fromkeys(fields))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")