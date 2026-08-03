"""Populate the approved stage-78.1 governance sample and publish one release."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from data_platform.providers.akshare_governance_provider import (
        AkshareGovernanceProvider,
    )
    from data_platform.storage.a_share_governance_store import (
        AShareGovernanceStore,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        default=os.environ.get("SCQ_A_SHARE_CANONICAL_DB_PATH")
        or "var/market/a_share_market.sqlite3",
    )
    parser.add_argument("--symbols", default="000001,600000,300750")
    parser.add_argument("--start-date", default="2015-01-05")
    parser.add_argument("--end-date")
    parser.add_argument("--index-symbol", default="000300")
    parser.add_argument("--proxy", default=os.environ.get("SCQ_AKSHARE_PROXY"))
    parser.add_argument("--retry-count", type=int, default=4)
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    database_path = Path(args.target)
    if not database_path.is_file():
        raise SystemExit(f"canonical database not found: {database_path}")
    end_date = str(args.end_date or _latest_common_date(database_path))
    symbols = _items(args.symbols)
    if not symbols:
        raise SystemExit("at least one sample symbol is required")

    if not args.skip_backup:
        backup = _backup_before_first_migration(database_path)
        if backup:
            print(f"[stage78.1] migration_backup={backup}", flush=True)

    store = AShareGovernanceStore(database_path)
    store.ensure_schema()
    source_errors: list[dict[str, str]] = []
    provider = AkshareGovernanceProvider(
        proxy_url=args.proxy,
        retry_count=args.retry_count,
    )

    calendar_rows = provider.fetch_trade_calendar(
        start_date=args.start_date,
        end_date=end_date,
    )
    calendar_count = store.upsert_trade_calendar(calendar_rows)
    print(f"[stage78.1] trade_calendar={calendar_count}", flush=True)

    try:
        index_rows = provider.fetch_index_daily_prices(
            index_symbol=args.index_symbol,
            start_date=args.start_date,
            end_date=end_date,
        )
    except Exception as error:
        index_rows = _load_existing_index_rows(
            database_path=database_path,
            index_symbol=args.index_symbol,
            start_date=args.start_date,
            end_date=end_date,
        )
        if not index_rows:
            raise
        source_errors.append(
            {
                "dataset": "market_index_daily_prices",
                "symbol": args.index_symbol,
                "error": f"live_refresh_failed_used_local_fact:{type(error).__name__}: {error}",
            }
        )
        print(
            f"[stage78.1] index_live_refresh_failed_using_local_rows={len(index_rows)}",
            flush=True,
        )
    index_count = store.upsert_index_prices(index_rows)
    print(f"[stage78.1] index_rows={index_count}", flush=True)

    lifecycle_rows: list[dict[str, Any]] = []
    corporate_action_rows: list[dict[str, Any]] = []
    for symbol in symbols:
        lifecycle_error: Exception | None = None
        try:
            symbol_lifecycle = provider.fetch_security_lifecycle_events(symbol=symbol)
        except Exception as error:
            symbol_lifecycle = []
            lifecycle_error = error
        if not symbol_lifecycle:
            symbol_lifecycle = _load_existing_lifecycle_rows(
                database_path=database_path,
                symbol=symbol,
            )
        if symbol_lifecycle:
            lifecycle_rows.extend(symbol_lifecycle)
            if lifecycle_error is not None:
                source_errors.append(
                    {
                        "dataset": "security_lifecycle_refresh_warning",
                        "symbol": symbol,
                        "error": f"live_refresh_failed_used_local_fact:{type(lifecycle_error).__name__}: {lifecycle_error}",
                    }
                )
        else:
            source_errors.append(
                {
                    "dataset": "security_lifecycle_events",
                    "symbol": symbol,
                    "error": (
                        f"{type(lifecycle_error).__name__}: {lifecycle_error}"
                        if lifecycle_error is not None
                        else "no lifecycle evidence returned"
                    ),
                }
            )
        try:
            corporate_action_rows.extend(
                provider.fetch_corporate_actions(symbol=symbol)
            )
        except Exception as error:
            source_errors.append(
                {
                    "dataset": "corporate_action_events",
                    "symbol": symbol,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
        print(
            f"[stage78.1] context_symbol={symbol} "
            f"lifecycle={sum(row['symbol'] == symbol for row in lifecycle_rows)} "
            f"actions={sum(row['symbol'] == symbol for row in corporate_action_rows)}",
            flush=True,
        )

    lifecycle_count = store.upsert_lifecycle_events(lifecycle_rows)
    corporate_action_count = store.upsert_corporate_actions(corporate_action_rows)
    duplicate_cleanup = _deduplicate_unpublished_context_facts(database_path)
    print(f"[stage78.1] context_duplicates_removed={duplicate_cleanup}", flush=True)

    try:
        suspension_rows = provider.fetch_suspensions(trade_date=end_date)
    except Exception as error:
        suspension_rows = []
        source_errors.append(
            {
                "dataset": "security_trading_status_daily",
                "symbol": "*",
                "error": f"{type(error).__name__}: {error}",
            }
        )
    status_rows = _build_sample_trading_status_rows(
        database_path=database_path,
        symbols=symbols,
        calendar_rows=calendar_rows,
        suspension_rows=suspension_rows,
        end_date=end_date,
    )
    trading_status_count = store.upsert_trading_statuses(status_rows)

    factor_rows = _build_observed_adjustment_factors(
        database_path=database_path,
        symbols=symbols,
        end_date=end_date,
    )
    factor_count = store.upsert_adjustment_factors(factor_rows)

    checks = _quality_checks(
        database_path=database_path,
        symbols=symbols,
        end_date=end_date,
        index_symbol=args.index_symbol,
        lifecycle_rows=lifecycle_rows,
        corporate_action_rows=corporate_action_rows,
        status_rows=status_rows,
        factor_rows=factor_rows,
        calendar_rows=calendar_rows,
        index_rows=index_rows,
        source_errors=source_errors,
    )
    quality_status = (
        "passed"
        if all(item["status"] == "passed" for item in checks)
        else "failed"
    )
    quality_payload = {
        "stage": "78.1",
        "scope": "canonical_prices_full_release_with_context_sample",
        "symbols": symbols,
        "index_symbol": args.index_symbol,
        "start_date": args.start_date,
        "end_date": end_date,
        "checks": checks,
        "source_errors": source_errors,
        "generated_at": _utc_now(),
    }
    quality_hash = _hash(quality_payload)
    quality_report_id = f"stage781-{end_date.replace('-', '')}-{quality_hash[:12]}"
    report = store.save_quality_report(
        quality_report_id=quality_report_id,
        rule_version="stage78.1-quality-v1",
        status=quality_status,
        payload=quality_payload,
    )
    if quality_status != "passed":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit("stage 78.1 quality report failed; version not published")

    members = _build_version_members(
        database_path=database_path,
        sample_symbols=symbols,
        index_symbol=args.index_symbol,
    )
    version = store.publish_data_version(
        as_of_trade_date=end_date,
        quality_report_id=quality_report_id,
        members=members,
        notes=(
            "Stage 78.1 full canonical daily-price release plus audited "
            "calendar/index/context sample; not a full-market context backfill."
        ),
    )
    result = {
        "status": "completed",
        "stage": "78.1",
        "database_path": str(database_path.resolve()),
        "sample_symbols": symbols,
        "end_date": end_date,
        "rows_written": {
            "market_trade_calendar": calendar_count,
            "market_index_daily_prices": index_count,
            "security_lifecycle_events": lifecycle_count,
            "corporate_action_events": corporate_action_count,
            "security_trading_status_daily": trading_status_count,
            "price_adjustment_factors": factor_count,
        },
        "quality_report": report,
        "data_version": version,
        "governance_overview": store.get_overview(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _backup_before_first_migration(database_path: Path) -> Path | None:
    with closing(sqlite3.connect(database_path)) as connection:
        exists = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='market_schema_migrations'
            """
        ).fetchone()
    if exists:
        return None
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{database_path.stem}.pre-stage78-1-{stamp}.sqlite3"
    with closing(sqlite3.connect(database_path)) as source:
        source.execute("PRAGMA wal_checkpoint(PASSIVE)")
        with closing(sqlite3.connect(backup_path)) as destination:
            source.backup(destination, pages=2048)
            check = destination.execute("PRAGMA integrity_check").fetchone()
            if not check or str(check[0]).lower() != "ok":
                raise RuntimeError("stage 78.1 backup integrity check failed")
    return backup_path


def _latest_common_date(database_path: Path) -> str:
    with closing(_connect_read_only(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT adjustment, MAX(trade_date) AS max_date
            FROM market_daily_prices
            GROUP BY adjustment
            """
        ).fetchall()
    dates = {str(row["adjustment"]): str(row["max_date"] or "") for row in rows}
    if any(not dates.get(mode) for mode in ("raw", "qfq", "hfq")):
        raise RuntimeError("raw/qfq/hfq latest dates are required")
    if len({dates[mode] for mode in ("raw", "qfq", "hfq")}) != 1:
        raise RuntimeError(f"raw/qfq/hfq latest dates differ: {dates}")
    return dates["raw"]


def _deduplicate_unpublished_context_facts(database_path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(database_path)) as connection:
        lifecycle_before = int(
            connection.execute("SELECT COUNT(*) FROM security_lifecycle_events").fetchone()[0]
        )
        action_before = int(
            connection.execute("SELECT COUNT(*) FROM corporate_action_events").fetchone()[0]
        )
        connection.execute(
            """
            DELETE FROM security_lifecycle_events
            WHERE rowid NOT IN (
                SELECT MAX(rowid) FROM security_lifecycle_events
                GROUP BY symbol, event_type, COALESCE(effective_from, ''),
                         COALESCE(announced_at, '')
            )
            """
        )
        connection.execute(
            """
            DELETE FROM corporate_action_events
            WHERE rowid NOT IN (
                SELECT MAX(rowid) FROM corporate_action_events
                GROUP BY symbol, action_type, COALESCE(report_period, ''),
                         COALESCE(announcement_date, ''), COALESCE(ex_date, '')
            )
            """
        )
        connection.commit()
        lifecycle_after = int(
            connection.execute("SELECT COUNT(*) FROM security_lifecycle_events").fetchone()[0]
        )
        action_after = int(
            connection.execute("SELECT COUNT(*) FROM corporate_action_events").fetchone()[0]
        )
    return {
        "security_lifecycle_events": lifecycle_before - lifecycle_after,
        "corporate_action_events": action_before - action_after,
    }

def _load_existing_lifecycle_rows(
    *,
    database_path: Path,
    symbol: str,
) -> list[dict[str, Any]]:
    with closing(_connect_read_only(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT event_id, symbol, event_type, effective_from, effective_to,
                   announced_at, source, source_observed_at, source_payload_hash,
                   evidence_json
            FROM security_lifecycle_events
            WHERE symbol=? ORDER BY effective_from
            """,
            (symbol,),
        ).fetchall()
    payload = []
    for row in rows:
        item = dict(row)
        item["evidence"] = json.loads(str(item.pop("evidence_json") or "{}"))
        payload.append(item)
    return payload

def _load_existing_index_rows(
    *,
    database_path: Path,
    index_symbol: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    with closing(_connect_read_only(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT index_symbol, trade_date, open, high, low, close, volume,
                   amount, source, source_observed_at, source_payload_hash
            FROM market_index_daily_prices
            WHERE index_symbol=? AND trade_date>=? AND trade_date<=?
            ORDER BY trade_date
            """,
            (index_symbol, start_date, end_date),
        ).fetchall()
    return [dict(row) for row in rows]

def _build_sample_trading_status_rows(
    *,
    database_path: Path,
    symbols: list[str],
    calendar_rows: list[dict[str, Any]],
    suspension_rows: list[dict[str, Any]],
    end_date: str,
) -> list[dict[str, Any]]:
    open_dates = [
        str(row["trade_date"])
        for row in calendar_rows
        if row.get("is_open") and str(row["trade_date"]) <= end_date
    ][-20:]
    suspension_map = {
        (str(row["symbol"]), str(row["trade_date"])): row
        for row in suspension_rows
    }
    placeholders = ",".join("?" for _ in symbols)
    with closing(_connect_read_only(database_path)) as connection:
        prices = {
            (str(row["symbol"]), str(row["trade_date"])): dict(row)
            for row in connection.execute(
                f"""
                SELECT symbol, trade_date, close, volume, source
                FROM market_daily_prices
                WHERE adjustment='raw'
                  AND symbol IN ({placeholders})
                  AND trade_date>=? AND trade_date<=?
                """,
                (*symbols, open_dates[0], open_dates[-1]),
            ).fetchall()
        }
    observed_at = _utc_now()
    rows = []
    for symbol in symbols:
        for trade_date in open_dates:
            suspension = suspension_map.get((symbol, trade_date))
            price = prices.get((symbol, trade_date))
            if suspension:
                rows.append(suspension)
            elif price:
                evidence = {
                    "positive_bar_evidence": True,
                    "close": price["close"],
                    "volume": price["volume"],
                    "price_source": price["source"],
                }
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "status": "normal",
                        "is_tradable": True,
                        "source": "canonical_market_daily_prices:positive_bar",
                        "source_observed_at": observed_at,
                        "source_payload_hash": _hash(evidence),
                        "evidence": evidence,
                    }
                )
            else:
                evidence = {
                    "positive_bar_evidence": False,
                    "suspension_source_match": False,
                    "reason": "no_authoritative_status_evidence",
                }
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date,
                        "status": "unknown",
                        "is_tradable": None,
                        "source": "stage78.1:evidence_gap",
                        "source_observed_at": observed_at,
                        "source_payload_hash": _hash(evidence),
                        "evidence": evidence,
                    }
                )
    return rows


def _build_observed_adjustment_factors(
    *,
    database_path: Path,
    symbols: list[str],
    end_date: str,
) -> list[dict[str, Any]]:
    placeholders = ",".join("?" for _ in symbols)
    with closing(_connect_read_only(database_path)) as connection:
        rows = connection.execute(
            f"""
            SELECT raw.symbol, raw.trade_date, raw.close AS raw_close,
                   qfq.close AS qfq_close, hfq.close AS hfq_close
            FROM market_daily_prices raw
            JOIN market_daily_prices qfq
              ON qfq.symbol=raw.symbol AND qfq.trade_date=raw.trade_date
             AND qfq.adjustment='qfq'
            JOIN market_daily_prices hfq
              ON hfq.symbol=raw.symbol AND hfq.trade_date=raw.trade_date
             AND hfq.adjustment='hfq'
            WHERE raw.adjustment='raw'
              AND raw.symbol IN ({placeholders})
              AND raw.trade_date<=?
              AND raw.close>0 AND qfq.close>0 AND hfq.close>0
            ORDER BY raw.trade_date DESC
            LIMIT 180
            """,
            (*symbols, end_date),
        ).fetchall()
    observed_at = _utc_now()
    factors = []
    for row in rows:
        for method, adjusted_close in (
            ("observed_qfq_close_ratio", row["qfq_close"]),
            ("observed_hfq_close_ratio", row["hfq_close"]),
        ):
            factor = float(adjusted_close) / float(row["raw_close"])
            factors.append(
                {
                    "symbol": row["symbol"],
                    "trade_date": row["trade_date"],
                    "factor_method": method,
                    "factor": factor,
                    "base_date": end_date,
                    "source": "derived:canonical_raw_adjusted_close_ratio",
                    "source_observed_at": observed_at,
                    "quality_status": "passed",
                    "evidence": {
                        "raw_close": row["raw_close"],
                        "adjusted_close": adjusted_close,
                        "derivation": "adjusted_close/raw_close",
                        "scope": "stage78.1_observed_factor_sample",
                    },
                }
            )
    return factors


def _quality_checks(
    *,
    database_path: Path,
    symbols: list[str],
    end_date: str,
    index_symbol: str,
    lifecycle_rows: list[dict[str, Any]],
    corporate_action_rows: list[dict[str, Any]],
    status_rows: list[dict[str, Any]],
    factor_rows: list[dict[str, Any]],
    calendar_rows: list[dict[str, Any]],
    index_rows: list[dict[str, Any]],
    source_errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    with closing(_connect_read_only(database_path)) as connection:
        duplicates = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT symbol, trade_date, adjustment
                    FROM market_daily_prices
                    GROUP BY symbol, trade_date, adjustment
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )
        latest = {
            str(row["adjustment"]): str(row["max_date"])
            for row in connection.execute(
                """
                SELECT adjustment, MAX(trade_date) AS max_date
                FROM market_daily_prices GROUP BY adjustment
                """
            ).fetchall()
        }
        context_duplicates = {
            "security_lifecycle_events": int(connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT 1 FROM security_lifecycle_events
                       GROUP BY symbol, event_type, COALESCE(effective_from, ''),
                                COALESCE(announced_at, '')
                       HAVING COUNT(*) > 1)"""
            ).fetchone()[0]),
            "corporate_action_events": int(connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT 1 FROM corporate_action_events
                       GROUP BY symbol, action_type, COALESCE(report_period, ''),
                                COALESCE(announcement_date, ''), COALESCE(ex_date, '')
                       HAVING COUNT(*) > 1)"""
            ).fetchone()[0]),
        }

    open_days = sum(bool(row.get("is_open")) for row in calendar_rows)
    factor_positive = all(float(row.get("factor") or 0) > 0 for row in factor_rows)
    expected_status_rows = len(symbols) * 20
    checks = [
        _check("canonical_price_duplicate_keys", duplicates == 0, duplicates),
        _check(
            "context_natural_key_duplicates",
            all(value == 0 for value in context_duplicates.values()),
            context_duplicates,
        ),
        _check(
            "canonical_adjustment_latest_date",
            all(latest.get(mode) == end_date for mode in ("raw", "qfq", "hfq")),
            latest,
        ),
        _check("trade_calendar_open_days", open_days > 0, open_days),
        _check(
            "official_index_coverage",
            bool(index_rows)
            and str(index_rows[-1]["trade_date"]) == end_date
            and str(index_rows[0]["index_symbol"]) == index_symbol,
            {
                "row_count": len(index_rows),
                "min_date": index_rows[0]["trade_date"] if index_rows else None,
                "max_date": index_rows[-1]["trade_date"] if index_rows else None,
            },
        ),
        _check(
            "sample_listing_lifecycle",
            len({row["symbol"] for row in lifecycle_rows}) == len(symbols),
            {"row_count": len(lifecycle_rows), "symbols": sorted({row["symbol"] for row in lifecycle_rows})},
        ),
        _check(
            "sample_corporate_actions",
            bool(corporate_action_rows),
            {"row_count": len(corporate_action_rows)},
        ),
        _check(
            "sample_daily_trading_status",
            len(status_rows) == expected_status_rows,
            {
                "row_count": len(status_rows),
                "expected": expected_status_rows,
                "unknown_count": sum(row["status"] == "unknown" for row in status_rows),
            },
        ),
        _check(
            "sample_adjustment_factors",
            bool(factor_rows) and factor_positive,
            {"row_count": len(factor_rows), "all_positive": factor_positive},
        ),
        _check(
            "critical_source_errors",
            not any(
                row["dataset"] in {
                    "security_lifecycle_events",
                    "corporate_action_events",
                }
                for row in source_errors
            ),
            source_errors,
        ),
    ]
    return checks


def _build_version_members(
    *,
    database_path: Path,
    sample_symbols: list[str],
    index_symbol: str,
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    with closing(_connect_read_only(database_path)) as connection:
        for adjustment in ("raw", "qfq", "hfq"):
            row = connection.execute(
                """
                SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS symbol_count,
                       MIN(trade_date) AS min_date, MAX(trade_date) AS max_date,
                       MAX(imported_at) AS latest_imported_at
                FROM market_daily_prices WHERE adjustment=?
                """,
                (adjustment,),
            ).fetchone()
            details = {
                "latest_imported_at": row["latest_imported_at"],
                "primary_key": "symbol+trade_date+adjustment",
            }
            members.append(
                _member(
                    dataset="market_daily_prices",
                    adjustment=adjustment,
                    symbol_scope="all_catalogued_a_shares",
                    row=row,
                    source="canonical_a_share_sqlite",
                    details=details,
                )
            )
        specs = (
            ("market_trade_calendar", "", "CN"),
            ("market_index_daily_prices", "", index_symbol),
            ("security_lifecycle_events", "", ",".join(sample_symbols)),
            ("security_trading_status_daily", "", ",".join(sample_symbols)),
            ("corporate_action_events", "", ",".join(sample_symbols)),
            ("price_adjustment_factors", "", ",".join(sample_symbols)),
        )
        for table, adjustment, scope in specs:
            date_column = {
                "market_trade_calendar": "trade_date",
                "market_index_daily_prices": "trade_date",
                "security_lifecycle_events": "effective_from",
                "security_trading_status_daily": "trade_date",
                "corporate_action_events": "COALESCE(ex_date, announcement_date)",
                "price_adjustment_factors": "trade_date",
            }[table]
            symbol_column = {
                "market_trade_calendar": "market",
                "market_index_daily_prices": "index_symbol",
            }.get(table, "symbol")
            where = ""
            values: tuple[Any, ...] = ()
            if table == "market_index_daily_prices":
                where = "WHERE index_symbol=?"
                values = (index_symbol,)
            elif table not in {"market_trade_calendar", "market_index_daily_prices"}:
                placeholders = ",".join("?" for _ in sample_symbols)
                where = f"WHERE symbol IN ({placeholders})"
                values = tuple(sample_symbols)
            row = connection.execute(
                f"""
                SELECT COUNT(*) AS row_count,
                       COUNT(DISTINCT {symbol_column}) AS symbol_count,
                       MIN({date_column}) AS min_date,
                       MAX({date_column}) AS max_date
                FROM {table} {where}
                """,
                values,
            ).fetchone()
            members.append(
                _member(
                    dataset=table,
                    adjustment=adjustment,
                    symbol_scope=scope,
                    row=row,
                    source="stage78.1_governance_sample",
                    details={
                        "sample_only": table
                        not in {"market_trade_calendar", "market_index_daily_prices"},
                    },
                )
            )
    return members


def _member(
    *,
    dataset: str,
    adjustment: str,
    symbol_scope: str,
    row: sqlite3.Row,
    source: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    summary = {
        "dataset": dataset,
        "adjustment": adjustment,
        "symbol_scope": symbol_scope,
        "row_count": int(row["row_count"] or 0),
        "symbol_count": int(row["symbol_count"] or 0),
        "min_date": row["min_date"],
        "max_date": row["max_date"],
        "source": source,
        "details": details,
    }
    return {
        **summary,
        "content_hash": _hash(summary),
        "quality_status": "passed",
        "sync_run_ref": None,
    }


def _check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "evidence": evidence,
    }


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _items(value: str) -> list[str]:
    return [item.strip().split(".", 1)[0].zfill(6) for item in value.split(",") if item.strip()]


def _hash(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
