"""Read-only strategy-scoped readiness audit for the Fujing V7 mother universe."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


DEFAULT_EXCLUDED_PREFIXES = ("688", "689", "8", "43", "83", "87", "92", "900", "200")


def main() -> None:
    ensure_project_root_on_sys_path()
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="var/market/a_share_market.sqlite3")
    parser.add_argument("--start-date", default="2015-01-05")
    parser.add_argument("--end-date", default="2026-08-10")
    parser.add_argument("--excluded-prefixes", default=",".join(DEFAULT_EXCLUDED_PREFIXES))
    args = parser.parse_args()
    prefixes = tuple(item.strip() for item in args.excluded_prefixes.split(",") if item.strip())
    path = Path(args.database).resolve()

    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        symbols = [
            dict(row)
            for row in connection.execute(
                """
                SELECT m.symbol, m.market, m.listing_status,
                       COALESCE(
                           (SELECT MIN(e.effective_from)
                            FROM security_lifecycle_events e
                            WHERE e.symbol=m.symbol AND e.event_type='listed'
                              AND e.effective_from IS NOT NULL),
                           (SELECT MIN(p.trade_date) FROM market_daily_prices p
                            WHERE p.symbol=m.symbol AND p.adjustment='raw')
                       ) AS listed_from,
                       COALESCE(
                           (SELECT MIN(e.effective_from)
                            FROM security_lifecycle_events e
                            WHERE e.symbol=m.symbol
                              AND e.event_type IN ('delisted','terminated')
                              AND e.effective_from IS NOT NULL),
                           CASE WHEN m.listing_status<>'current' THEN
                               (SELECT MAX(p.trade_date) FROM market_daily_prices p
                                WHERE p.symbol=m.symbol AND p.adjustment='raw')
                           END
                       ) AS delisted_from
                FROM market_symbols m
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
                ORDER BY m.symbol
                """,
                (args.start_date, args.end_date, args.end_date, args.start_date),
            ).fetchall()
        ]
        required = [row for row in symbols if not str(row["symbol"]).startswith(prefixes)]
        excluded = [row for row in symbols if str(row["symbol"]).startswith(prefixes)]
        required_symbols = [str(row["symbol"]) for row in required]
        connection.execute("CREATE TEMP TABLE required_symbols(symbol TEXT PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO required_symbols(symbol) VALUES (?)",
            ((symbol,) for symbol in required_symbols),
        )
        coverage = connection.execute(
            """
            WITH bounds AS (
                SELECT r.symbol,
                       MAX(?, COALESCE(
                           (SELECT MIN(e.effective_from)
                            FROM security_lifecycle_events e
                            WHERE e.symbol=r.symbol AND e.event_type='listed'
                              AND e.effective_from IS NOT NULL),
                           (SELECT MIN(p.trade_date) FROM market_daily_prices p
                            WHERE p.symbol=r.symbol AND p.adjustment='raw')
                       )) AS lower_date,
                       MIN(?, COALESCE(
                           (SELECT MIN(e.effective_from)
                            FROM security_lifecycle_events e
                            WHERE e.symbol=r.symbol
                              AND e.event_type IN ('delisted','terminated')
                              AND e.effective_from IS NOT NULL),
                           CASE WHEN m.listing_status<>'current' THEN
                               (SELECT MAX(p.trade_date) FROM market_daily_prices p
                                WHERE p.symbol=r.symbol AND p.adjustment='raw')
                           END,
                           ?
                       )) AS upper_date
                FROM required_symbols r JOIN market_symbols m ON m.symbol=r.symbol
            ), expected AS (
                SELECT b.symbol, c.trade_date
                FROM bounds b JOIN market_trade_calendar c
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
            (args.start_date, args.end_date, args.end_date),
        ).fetchone()
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
        missing_lifecycle = sum(1 for row in symbols if not row.get("listed_from"))

    payload = {
        "status": "passed" if (
            int(coverage["missing_risk_symbol_trade_days"] or 0) == 0
            and overlaps == 0
            and missing_lifecycle == 0
        ) else "failed",
        "policy": "fujing_v7_point_in_time_all_a_mother_universe_v1",
        "date_window": {"start_date": args.start_date, "end_date": args.end_date},
        "mother_universe_symbols": len(symbols),
        "structurally_excluded_symbols": len(excluded),
        "risk_fact_required_symbols": len(required),
        "structural_exclusion_prefixes": list(prefixes),
        "historical_name_required": False,
        "missing_listing_boundary_symbols": missing_lifecycle,
        "active_overlap_pairs": overlaps,
        "coverage": dict(coverage),
        "release_scope": "strategy_scoped_candidate_only",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
