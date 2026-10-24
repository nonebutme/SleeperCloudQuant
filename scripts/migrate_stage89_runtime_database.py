"""Non-destructively promote the historical tmp runtime database."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


CORE_RELATIONSHIPS = (
    "backtest_accounts", "backtest_positions", "backtest_trades",
    "backtest_metrics", "backtest_logs", "backtest_yearly_returns",
    "backtest_input_snapshots",
)


def _connect_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]


def _inventory(path: Path) -> dict[str, int]:
    with _connect_ro(path) as connection:
        return {table: int(connection.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]) for table in _tables(connection)}


def _validate(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    with _connect_ro(path) as connection:
        check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        if check != "ok":
            raise RuntimeError(f"quick_check failed for {path}: {check}")
        tables = set(_tables(connection))
        if "backtest_runs" not in tables:
            raise RuntimeError("backtest_runs is missing")
        orphans = {
            table: int(connection.execute(
                f'SELECT COUNT(*) FROM "{table}" child '
                "LEFT JOIN backtest_runs parent ON parent.run_id=child.run_id "
                "WHERE parent.run_id IS NULL"
            ).fetchone()[0])
            for table in CORE_RELATIONSHIPS if table in tables
        }
    inventory = _inventory(path)
    return inventory, orphans


def _backup(source: Path, target: Path, pages: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.execute("PRAGMA wal_checkpoint(PASSIVE)")
        src.backup(dst, pages=max(1, pages))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="tmp/formal_http_demo.sqlite3")
    parser.add_argument("--target", default="var/runtime/backtest_results.sqlite3")
    parser.add_argument("--backup", required=True)
    parser.add_argument("--pages", type=int, default=8192)
    args = parser.parse_args()
    source, target, backup = (Path(value).resolve() for value in (
        args.source, args.target, args.backup
    ))
    if not source.is_file():
        raise SystemExit(f"source database does not exist: {source}")
    for candidate in (target, backup):
        if candidate.exists():
            raise SystemExit(f"refusing to overwrite existing file: {candidate}")

    source_inventory, source_orphans = _validate(source)
    if any(source_orphans.values()):
        raise RuntimeError(f"source contains orphan rows: {source_orphans}")
    _backup(source, backup, args.pages)
    backup_inventory, backup_orphans = _validate(backup)
    _backup(source, target, args.pages)
    target_inventory, target_orphans = _validate(target)
    if not (source_inventory == backup_inventory == target_inventory):
        raise RuntimeError("source, backup and target inventories differ")
    if not (source_orphans == backup_orphans == target_orphans):
        raise RuntimeError("source, backup and target relationships differ")
    print(
        "[stage89] migration verified "
        f"tables={len(target_inventory)} rows={sum(target_inventory.values())} "
        f"source={source} backup={backup} target={target}"
    )


if __name__ == "__main__":
    main()
