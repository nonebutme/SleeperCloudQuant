"""SQLite persistence for the stage-89 asset and lineage catalog."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_platform.asset_governance import ASSETS, DATABASES, LINEAGE


class AssetGovernanceStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def ensure_schema(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_asset_registry (
                    asset_id TEXT PRIMARY KEY, database_id TEXT NOT NULL,
                    database_path TEXT NOT NULL, table_name TEXT NOT NULL,
                    database_role TEXT NOT NULL, lifecycle_layer TEXT NOT NULL,
                    owner TEXT NOT NULL, authority TEXT NOT NULL,
                    mutability TEXT NOT NULL, retention_class TEXT NOT NULL,
                    secondary_layers_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_data_asset_registry_layer
                    ON data_asset_registry (lifecycle_layer, database_role, asset_id);
                CREATE TABLE IF NOT EXISTS data_lineage_edges (
                    edge_id TEXT PRIMARY KEY, upstream_asset_id TEXT NOT NULL,
                    downstream_asset_id TEXT NOT NULL, relation_type TEXT NOT NULL,
                    transform_version TEXT NOT NULL, point_in_time_policy TEXT NOT NULL,
                    metadata_json TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_data_lineage_upstream
                    ON data_lineage_edges (upstream_asset_id, downstream_asset_id);
                CREATE INDEX IF NOT EXISTS idx_data_lineage_downstream
                    ON data_lineage_edges (downstream_asset_id, upstream_asset_id);
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(data_asset_registry)")
            }
            if "secondary_layers_json" not in columns:
                connection.execute(
                    "ALTER TABLE data_asset_registry "
                    "ADD COLUMN secondary_layers_json TEXT NOT NULL DEFAULT '[]'"
                )
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for asset in ASSETS:
                database_id, table_name = asset.asset_id.split(".", 1)
                connection.execute(
                    """INSERT INTO data_asset_registry (
                        asset_id, database_id, database_path, table_name,
                        database_role, lifecycle_layer, owner, authority,
                        mutability, retention_class, secondary_layers_json,
                        status, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_id) DO UPDATE SET
                    database_path=excluded.database_path, database_role=excluded.database_role,
                    lifecycle_layer=excluded.lifecycle_layer, owner=excluded.owner,
                    authority=excluded.authority, mutability=excluded.mutability,
                    retention_class=excluded.retention_class,
                    secondary_layers_json=excluded.secondary_layers_json,
                    status=excluded.status, updated_at=excluded.updated_at""",
                    (asset.asset_id, database_id, str(DATABASES[database_id]), table_name,
                     asset.database_role, asset.lifecycle_layer, asset.owner, asset.authority,
                     asset.mutability, asset.retention_class,
                     json.dumps(asset.secondary_layers, ensure_ascii=False),
                     "registered", now),
                )
            for item in LINEAGE:
                edge_id = f"{item['upstream']}->{item['downstream']}:{item['relation']}"
                connection.execute(
                    """INSERT INTO data_lineage_edges VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(edge_id) DO UPDATE SET updated_at=excluded.updated_at""",
                    (edge_id, item["upstream"], item["downstream"], item["relation"],
                     "stage89-v1", "explicit_version_or_as_of", "{}", now),
                )

    def list_assets(self) -> list[dict[str, Any]]:
        with closing(self._connect_ro()) as connection:
            result = []
            for row in connection.execute(
                "SELECT * FROM data_asset_registry ORDER BY lifecycle_layer, asset_id"
            ):
                item = dict(row)
                item["secondary_layers"] = json.loads(
                    str(item.pop("secondary_layers_json") or "[]")
                )
                result.append(item)
            return result

    def list_lineage(self, asset_id: str = "") -> list[dict[str, Any]]:
        where, values = "", []
        if asset_id:
            where, values = " WHERE upstream_asset_id=? OR downstream_asset_id=?", [asset_id, asset_id]
        with closing(self._connect_ro()) as connection:
            rows = connection.execute(
                "SELECT * FROM data_lineage_edges" + where + " ORDER BY edge_id", values
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(str(item.pop("metadata_json") or "{}"))
            result.append(item)
        return result

    def _connect_ro(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection
