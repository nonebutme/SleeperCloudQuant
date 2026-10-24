"""Shared immutable data-version resolution for research and backtests."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable


class ResearchDataVersionResolver:
    """Resolve an explicit version or the governed global default.

    The latest published release is only a compatibility fallback when the
    control-plane default has not been configured.  Consumers therefore share
    one deterministic policy instead of independently selecting "latest".
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def resolve(
        self,
        *,
        data_version_id: str | None = None,
        required_members: Iterable[tuple[str, str]] = (),
    ) -> dict[str, Any]:
        if not self.database_path.is_file():
            return {"status": "unavailable", "reason": "market_database_not_found"}
        try:
            with closing(self._connect()) as connection:
                version, policy = self._select_version(connection, data_version_id)
                if version is None:
                    return {
                        "status": "unavailable",
                        "reason": (
                            "data_version_not_reproducible"
                            if data_version_id
                            else "no_governed_data_version"
                        ),
                    }
                managed = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='maintenance_commits'"
                ).fetchone()
                if managed:
                    current = connection.execute("SELECT setting_value FROM data_center_settings "
                                                 "WHERE setting_key='default_data_version_id'").fetchone()
                    if current and str(version["data_version_id"]) != str(current[0]):
                        return {"status": "unavailable", "reason": "historical_input_not_retained",
                                "data_version_id": str(version["data_version_id"]),
                                "message": "原数据已更新；请使用保存的研究输入或新建研究任务。"}
                members = [
                    dict(row)
                    for row in connection.execute(
                        """SELECT dataset, adjustment, symbol_scope, row_count,
                                  symbol_count, min_date, max_date, source,
                                  sync_run_ref, content_hash, quality_status,
                                  details_json
                           FROM data_version_members
                           WHERE data_version_id=? ORDER BY dataset, adjustment""",
                        (version["data_version_id"],),
                    ).fetchall()
                ]
                report = connection.execute(
                    "SELECT status FROM data_quality_reports WHERE quality_report_id=?",
                    (version["quality_report_id"],),
                ).fetchone()
        except sqlite3.Error as error:
            return {
                "status": "unavailable",
                "reason": f"data_version_read_failed:{type(error).__name__}",
            }

        if report is None or str(report["status"] or "") != "passed":
            return {
                "status": "unavailable",
                "reason": "quality_report_not_passed",
                "data_version_id": str(version["data_version_id"]),
            }

        required: list[dict[str, Any]] = []
        for dataset, adjustment in required_members:
            member = next(
                (
                    item
                    for item in members
                    if item["dataset"] == dataset
                    and str(item.get("adjustment") or "") == str(adjustment or "")
                ),
                None,
            )
            if member is None:
                suffix = f":{adjustment}" if adjustment else ""
                return {
                    "status": "unavailable",
                    "reason": f"required_member_missing:{dataset}{suffix}",
                    "data_version_id": str(version["data_version_id"]),
                }
            required.append(member)
        failed = [item for item in required if item.get("quality_status") != "passed"]
        if failed:
            return {
                "status": "unavailable",
                "reason": "required_member_quality_not_passed",
                "data_version_id": str(version["data_version_id"]),
                "failed_members": failed,
            }
        return {
            "status": "ready",
            "data_version_id": str(version["data_version_id"]),
            "version_status": str(version["status"]),
            "as_of_trade_date": str(version["as_of_trade_date"]),
            "quality_report_id": str(version["quality_report_id"]),
            "manifest_hash": str(version["manifest_hash"]),
            "published_at": version["published_at"],
            "required_members": required,
            "all_members": members,
            "selection_policy": policy,
        }

    @staticmethod
    def _select_version(
        connection: sqlite3.Connection, explicit_id: str | None,
    ) -> tuple[sqlite3.Row | None, str]:
        if explicit_id:
            return (
                connection.execute(
                    """SELECT * FROM data_versions
                       WHERE data_version_id=? AND status IN ('published','superseded')""",
                    (str(explicit_id),),
                ).fetchone(),
                "explicit_reproducible_version",
            )
        settings_exists = connection.execute(
            """SELECT 1 FROM sqlite_master
               WHERE type='table' AND name='data_center_settings'"""
        ).fetchone()
        if settings_exists is not None:
            default = connection.execute(
                """SELECT v.* FROM data_center_settings s
                   JOIN data_versions v ON v.data_version_id=s.setting_value
                   WHERE s.setting_key='default_data_version_id'
                     AND v.status IN ('published','superseded')"""
            ).fetchone()
            if default is not None:
                return default, "global_default_version"
        return (
            connection.execute(
                """SELECT * FROM data_versions WHERE status='published'
                   ORDER BY as_of_trade_date DESC, published_at DESC LIMIT 1"""
            ).fetchone(),
            "latest_published_fallback",
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"file:{self.database_path.resolve().as_posix()}?mode=ro", uri=True
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection
