"""Read-only coverage audit for governed point-in-time security intervals."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="var/market/a_share_market.sqlite3")
    parser.add_argument("--jobs", required=True)
    args = parser.parse_args()
    jobs = [item.strip() for item in args.jobs.split(",") if item.strip()]
    if not jobs:
        raise SystemExit("--jobs requires at least one job id")
    placeholders = ",".join("?" for _ in jobs)
    path = Path(args.database).resolve()
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        target = connection.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN i.status='completed' THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN i.status='quarantined' THEN 1 ELSE 0 END) AS quarantined
            FROM market_context_backfill_items i
            WHERE i.job_id IN ({placeholders})
              AND i.dataset='security_master_intervals'
            """,
            jobs,
        ).fetchone()
        intervals = connection.execute(
            """
            SELECT COUNT(*) AS row_count,
                   COUNT(DISTINCT symbol) AS symbol_count,
                   SUM(risk_warning) AS risk_warning_intervals,
                   SUM(CASE WHEN name='' THEN 1 ELSE 0 END) AS blank_name_rows,
                   MIN(valid_from) AS min_date,
                   MAX(valid_to) AS max_date
            FROM security_master_intervals WHERE is_active=1
            """
        ).fetchone()
        invalid = connection.execute(
            """
            SELECT
                SUM(CASE WHEN available_at>valid_from THEN 1 ELSE 0 END) AS future_available,
                SUM(CASE WHEN valid_to<valid_from THEN 1 ELSE 0 END) AS reversed_dates,
                SUM(CASE WHEN risk_warning NOT IN (0,1) THEN 1 ELSE 0 END) AS invalid_risk
            FROM security_master_intervals WHERE is_active=1
            """
        ).fetchone()
        overlaps = int(connection.execute(
            """
            SELECT COUNT(*) FROM security_master_intervals a
            JOIN security_master_intervals b
              ON a.symbol=b.symbol AND a.interval_id<b.interval_id
             AND a.is_active=1 AND b.is_active=1
             AND a.valid_from<=COALESCE(b.valid_to,'9999-12-31')
             AND b.valid_from<=COALESCE(a.valid_to,'9999-12-31')
            """
        ).fetchone()[0])
        expected = connection.execute(
            f"""
            WITH targets AS (
                SELECT i.symbol, j.start_date, j.end_date
                FROM market_context_backfill_items i
                JOIN market_context_backfill_jobs j ON j.job_id=i.job_id
                WHERE i.job_id IN ({placeholders})
                  AND i.dataset='security_master_intervals'
                  AND i.status='completed'
            ), bounds AS (
                SELECT t.symbol,
                       MAX(t.start_date, COALESCE(
                           (SELECT MIN(e.effective_from)
                            FROM security_lifecycle_events e
                            WHERE e.symbol=t.symbol AND e.event_type='listed'
                              AND e.effective_from IS NOT NULL),
                           (SELECT MIN(p.trade_date) FROM market_daily_prices p
                            WHERE p.symbol=t.symbol AND p.adjustment='raw')
                       )) AS lower_date,
                       MIN(t.end_date, COALESCE(
                           (SELECT MIN(e.effective_from)
                            FROM security_lifecycle_events e
                            WHERE e.symbol=t.symbol
                              AND e.event_type IN ('delisted','terminated')
                              AND e.effective_from IS NOT NULL),
                           CASE WHEN m.listing_status<>'current' THEN
                               (SELECT MAX(p.trade_date) FROM market_daily_prices p
                                WHERE p.symbol=t.symbol AND p.adjustment='raw')
                           END,
                           t.end_date
                       )) AS upper_date
                FROM targets t JOIN market_symbols m ON m.symbol=t.symbol
            ), expected_dates AS (
                SELECT b.symbol, c.trade_date
                FROM bounds b JOIN market_trade_calendar c
                  ON c.market='CN' AND c.is_open=1
                 AND c.trade_date BETWEEN b.lower_date AND b.upper_date
            )
            SELECT COUNT(*) AS expected_rows,
                   SUM(CASE WHEN NOT EXISTS (
                       SELECT 1 FROM security_master_intervals s
                       WHERE s.symbol=e.symbol AND s.is_active=1
                         AND s.available_at<=e.trade_date
                         AND s.valid_from<=e.trade_date
                         AND COALESCE(s.valid_to,s.valid_from)>=e.trade_date
                   ) THEN 1 ELSE 0 END) AS missing_rows,
                   COUNT(DISTINCT e.symbol) AS expected_symbols
            FROM expected_dates e
            """,
            jobs,
        ).fetchone()
        by_status = [
            dict(row)
            for row in connection.execute(
                f"""
                SELECT i.status, SUBSTR(i.item_key,1,1) AS prefix, COUNT(*) AS count
                FROM market_context_backfill_items i
                WHERE i.job_id IN ({placeholders})
                  AND i.dataset='security_master_intervals'
                GROUP BY i.status, SUBSTR(i.item_key,1,1)
                ORDER BY i.status, prefix
                """,
                jobs,
            ).fetchall()
        ]
        superseded = int(connection.execute(
            "SELECT COUNT(*) FROM security_master_intervals WHERE is_active=0"
        ).fetchone()[0])
    payload = {
        "status": "passed" if (
            int(expected["missing_rows"] or 0) == 0
            and overlaps == 0
            and not any(int(value or 0) for value in dict(invalid).values())
        ) else "failed",
        "jobs": jobs,
        "targets": dict(target),
        "active_intervals": dict(intervals),
        "superseded_evidence_rows": superseded,
        "invalid": dict(invalid),
        "active_overlap_pairs": overlaps,
        "coverage": dict(expected),
        "items_by_status_and_prefix": by_status,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
