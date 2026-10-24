"""Publish the confirmed Fujing V7 strategy-scoped security-master member."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


EXCLUDED_PREFIXES = ("688", "689", "8", "43", "83", "87", "92", "900", "200")
START_DATE = "2015-01-05"
END_DATE = "2026-08-10"


def main() -> None:
    ensure_project_root_on_sys_path()
    from data_platform.storage.a_share_governance_store import AShareGovernanceStore
    from data_platform.storage.data_center_store import DataCenterStore

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="var/market/a_share_market.sqlite3")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--set-default", action="store_true")
    args = parser.parse_args()
    path = Path(args.database).resolve()
    audit, member = _build_release_evidence(path)
    if audit["status"] != "passed":
        raise SystemExit(json.dumps({"status": "blocked", "audit": audit}, ensure_ascii=False))

    governance = AShareGovernanceStore(path)
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        default_row = connection.execute(
            "SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'"
        ).fetchone()
        published_row = connection.execute(
            """SELECT data_version_id FROM data_versions WHERE status='published'
               ORDER BY as_of_trade_date DESC, published_at DESC LIMIT 1"""
        ).fetchone()
    if published_row is None:
        raise SystemExit("published governed data version is unavailable")
    previous_default_id = str(default_row["setting_value"]) if default_row else None
    parent_id = str(published_row["data_version_id"])
    parent = _fetch_version_readonly(path, parent_id)
    if parent.get("status") not in {"published", "superseded"}:
        raise SystemExit(f"default data version is not publishable parent: {parent_id}")
    members = [_clone_member(item) for item in parent.get("members") or []]
    members = [item for item in members if item["dataset"] != "security_master_intervals"]
    members.append(member)
    quality_payload = {
        "policy": audit["policy"],
        "business_semantics": (
            "point-in-time all-A mother universe; deterministic board/code exclusions precede "
            "risk-warning validation; historical names are display-only"
        ),
        "parent_data_version_id": parent_id,
        "previous_default_data_version_id": previous_default_id,
        "audit": audit,
        "security_master_member": member,
        "human_confirmation": "confirmed_in_codex_thread_2026-08-17",
    }
    quality_report_id = "fujing-v7-universe-" + _hash(quality_payload)[:20]
    preview = {
        "status": "ready_to_apply" if not args.apply else "applying",
        "database": str(path),
        "parent_data_version_id": parent_id,
        "previous_default_data_version_id": previous_default_id,
        "quality_report_id": quality_report_id,
        "member_count": len(members),
        "audit": audit,
        "security_master_member": member,
        "set_default": bool(args.set_default),
    }
    if not args.apply:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    governance.save_quality_report(
        quality_report_id=quality_report_id,
        rule_version="fujing-v7-point-in-time-universe-v2",
        status="passed",
        payload=quality_payload,
    )
    published = governance.publish_data_version(
        as_of_trade_date=END_DATE,
        quality_report_id=quality_report_id,
        members=members,
        notes=(
            "Fujing V7 strategy-scoped point-in-time universe: all-A mother universe, "
            "structural exclusions before risk-warning validation."
        ),
    )
    default_result: dict[str, Any] | None = None
    if args.set_default:
        default_result = DataCenterStore(path).set_default_version(str(published["data_version_id"]))
    print(json.dumps({
        **preview,
        "status": "published",
        "data_version_id": published["data_version_id"],
        "default_result": default_result,
    }, ensure_ascii=False, indent=2))


def _build_release_evidence(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        symbols = [
            str(row["symbol"])
            for row in connection.execute(
                """
                SELECT m.symbol FROM market_symbols m
                WHERE EXISTS (
                    SELECT 1 FROM market_daily_prices p
                    WHERE p.symbol=m.symbol AND p.adjustment='raw'
                      AND p.trade_date BETWEEN ? AND ?
                ) OR EXISTS (
                    SELECT 1 FROM security_lifecycle_events e
                    WHERE e.symbol=m.symbol AND e.event_type='listed'
                      AND e.effective_from<=?
                      AND (e.effective_to IS NULL OR e.effective_to>=?)
                )
                """,
                (START_DATE, END_DATE, END_DATE, START_DATE),
            ).fetchall()
        ]
        required = [symbol for symbol in symbols if not symbol.startswith(EXCLUDED_PREFIXES)]
        connection.execute("CREATE TEMP TABLE required_symbols(symbol TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO required_symbols(symbol) VALUES (?)",
            ((symbol,) for symbol in required),
        )
        coverage = dict(connection.execute(
            """
            WITH bounds AS (
                SELECT r.symbol,
                       MAX(?, COALESCE(
                           (SELECT MIN(e.effective_from) FROM security_lifecycle_events e
                            WHERE e.symbol=r.symbol AND e.event_type='listed'
                              AND e.effective_from IS NOT NULL),
                           (SELECT MIN(p.trade_date) FROM market_daily_prices p
                            WHERE p.symbol=r.symbol AND p.adjustment='raw')
                       )) AS lower_date,
                       MIN(?, COALESCE(
                           (SELECT MIN(e.effective_from) FROM security_lifecycle_events e
                            WHERE e.symbol=r.symbol AND e.event_type IN ('delisted','terminated')
                              AND e.effective_from IS NOT NULL),
                           CASE WHEN m.listing_status<>'current' THEN
                               (SELECT MAX(p.trade_date) FROM market_daily_prices p
                                WHERE p.symbol=r.symbol AND p.adjustment='raw')
                           END,
                           ?
                       )) AS upper_date
                FROM required_symbols r JOIN market_symbols m ON m.symbol=r.symbol
            ), expected AS (
                SELECT b.symbol, c.trade_date FROM bounds b JOIN market_trade_calendar c
                  ON c.market='CN' AND c.is_open=1
                 AND c.trade_date BETWEEN b.lower_date AND b.upper_date
            )
            SELECT COUNT(*) AS expected_symbol_trade_days,
                   COUNT(DISTINCT symbol) AS expected_symbols,
                   SUM(CASE WHEN NOT EXISTS (
                       SELECT 1 FROM security_master_intervals s
                       WHERE s.symbol=expected.symbol AND s.is_active=1
                         AND s.available_at<=expected.trade_date
                         AND s.valid_from<=expected.trade_date
                         AND COALESCE(s.valid_to,s.valid_from)>=expected.trade_date
                         AND s.risk_warning IN (0,1)
                   ) THEN 1 ELSE 0 END) AS missing_risk_symbol_trade_days
            FROM expected
            """,
            (START_DATE, END_DATE, END_DATE),
        ).fetchone())
        overlaps = int(connection.execute(
            """
            SELECT COUNT(*) FROM security_master_intervals a
            JOIN security_master_intervals b
              ON a.symbol=b.symbol AND a.interval_id<b.interval_id
             AND a.is_active=1 AND b.is_active=1
             AND a.symbol IN (SELECT symbol FROM required_symbols)
             AND a.valid_from<=COALESCE(b.valid_to,'9999-12-31')
             AND b.valid_from<=COALESCE(a.valid_to,'9999-12-31')
            """
        ).fetchone()[0])
        interval_summary = dict(connection.execute(
            """
            SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS symbol_count,
                   MIN(valid_from) AS min_date, MAX(COALESCE(valid_to,valid_from)) AS max_date
            FROM security_master_intervals
            WHERE is_active=1 AND symbol IN (SELECT symbol FROM required_symbols)
            """
        ).fetchone())
        snapshot_refs: set[str] = set()
        for row in connection.execute(
            """SELECT evidence_json FROM security_master_intervals
               WHERE is_active=1 AND symbol IN (SELECT symbol FROM required_symbols)"""
        ).fetchall():
            evidence = json.loads(str(row["evidence_json"] or "{}"))
            if isinstance(evidence, dict) and evidence.get("job_id"):
                snapshot_refs.add(str(evidence["job_id"]))

    audit = {
        "status": "passed" if (
            int(coverage.get("missing_risk_symbol_trade_days") or 0) == 0
            and overlaps == 0
            and int(coverage.get("expected_symbols") or 0) == len(required)
        ) else "failed",
        "policy": "fujing_v7_point_in_time_all_a_mother_universe_v1",
        "date_window": {"start_date": START_DATE, "end_date": END_DATE},
        "mother_universe_symbols": len(symbols),
        "structurally_excluded_symbols": len(symbols) - len(required),
        "risk_fact_required_symbols": len(required),
        "structural_exclusion_prefixes": list(EXCLUDED_PREFIXES),
        "historical_name_required": False,
        "active_overlap_pairs": overlaps,
        "coverage": coverage,
    }
    member_details = {
        "policy": audit["policy"],
        "structural_exclusion_prefixes": list(EXCLUDED_PREFIXES),
        "historical_name_required": False,
        "snapshot_refs": sorted(snapshot_refs),
        "audit": audit,
    }
    member = {
        "dataset": "security_master_intervals",
        "adjustment": "",
        "symbol_scope": "fujing_v7_structurally_eligible_a_shares",
        **interval_summary,
        "source": "stage78.3_context_backfill+strategy_scope_audit",
        "sync_run_ref": "fujing-v7-universe-scope-audit-20260817",
        "content_hash": _hash({"summary": interval_summary, "details": member_details}),
        "quality_status": "passed",
        "details": member_details,
    }
    return audit, member


def _fetch_version_readonly(path: Path, data_version_id: str) -> dict[str, Any]:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        version = connection.execute(
            "SELECT * FROM data_versions WHERE data_version_id=?",
            (data_version_id,),
        ).fetchone()
        if version is None:
            return {"status": "not_found", "data_version_id": data_version_id, "members": []}
        members = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM data_version_members WHERE data_version_id=? ORDER BY dataset, adjustment",
                (data_version_id,),
            ).fetchall()
        ]
    return {**dict(version), "members": members}


def _clone_member(raw: dict[str, Any]) -> dict[str, Any]:
    details = json.loads(str(raw.get("details_json") or "{}"))
    return {
        key: raw.get(key)
        for key in (
            "dataset", "adjustment", "symbol_scope", "row_count", "symbol_count",
            "min_date", "max_date", "source", "sync_run_ref", "content_hash", "quality_status",
        )
    } | {"details": details if isinstance(details, dict) else {}}


def _hash(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    main()
