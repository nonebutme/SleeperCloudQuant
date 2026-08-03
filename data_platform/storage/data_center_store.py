"""Stage-86 additive control-plane storage for the local data center."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from data_platform.data_center_catalog import (
    CONTROLLED_SOURCES,
    DATASET_CATALOG,
    DATA_LAYERS,
    SOURCE_CAPABILITIES,
)


DATA_CENTER_SCHEMA_VERSION = "86.3.7"

DEFAULT_ROUTES: tuple[dict[str, Any], ...] = (
    {"route_id": "a-share-catalog", "dataset": "a_share_catalog", "provider": "akshare", "endpoint": "stock_info_a_code_name", "upstream": "public-finance-sites", "priority": 10, "enabled": True, "rpm": 30, "concurrency": 1, "timeout": 30, "retries": 2, "backoff": 2.0, "stage": "P0"},
    {"route_id": "a-share-daily", "dataset": "a_share_daily", "provider": "akshare", "endpoint": "stock_zh_a_hist", "upstream": "eastmoney", "priority": 10, "enabled": True, "rpm": 60, "concurrency": 4, "timeout": 60, "retries": 3, "backoff": 2.0, "stage": "P0"},
    {"route_id": "trade-calendar", "dataset": "trade_calendar", "provider": "akshare", "endpoint": "tool_trade_date_hist_sina", "upstream": "sina", "priority": 10, "enabled": True, "rpm": 30, "concurrency": 1, "timeout": 30, "retries": 2, "backoff": 2.0, "stage": "P0"},
    {"route_id": "cn-index-daily", "dataset": "index_daily", "provider": "akshare", "endpoint": "index_zh_a_hist", "upstream": "eastmoney", "priority": 10, "enabled": True, "rpm": 30, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 2.0, "stage": "P0"},
    {"route_id": "corporate-actions", "dataset": "corporate_actions", "provider": "akshare", "endpoint": "stock_fhps_em", "upstream": "eastmoney", "priority": 20, "enabled": True, "rpm": 20, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P1"},
    {"route_id": "index-components", "dataset": "index_components", "provider": "akshare", "endpoint": "index_stock_cons_csindex", "upstream": "csindex", "priority": 20, "enabled": True, "rpm": 20, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P1"},
    {"route_id": "industry-classification", "dataset": "industry_classification", "provider": "akshare", "endpoint": "stock_board_industry_name_em", "upstream": "eastmoney", "priority": 30, "enabled": False, "rpm": 20, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P1"},
    {"route_id": "financial-statements", "dataset": "financial_statements", "provider": "akshare", "endpoint": "stock_zcfz_em", "upstream": "eastmoney", "priority": 90, "enabled": False, "rpm": 10, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 4.0, "stage": "stage87"},
    {"route_id": "industry-board-history", "dataset": "industry_board", "provider": "akshare", "endpoint": "stock_board_industry_hist_em", "upstream": "eastmoney", "priority": 40, "enabled": True, "rpm": 20, "concurrency": 2, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P2"},
    {"route_id": "concept-board-history", "dataset": "concept_board", "provider": "akshare", "endpoint": "stock_board_concept_hist_em", "upstream": "eastmoney", "priority": 40, "enabled": True, "rpm": 20, "concurrency": 2, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P2"},
    {"route_id": "industry-board-history-ths", "dataset": "industry_board", "provider": "akshare", "source_id": "akshare_ths", "endpoint": "stock_board_industry_index_ths", "upstream": "10jqka", "priority": 45, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 15, "retries": 2, "backoff": 3.0, "stage": "P1", "fallback_policy": "on_failure"},
    {"route_id": "concept-board-history-ths", "dataset": "concept_board", "provider": "akshare", "source_id": "akshare_ths", "endpoint": "stock_board_concept_index_ths", "upstream": "10jqka", "priority": 45, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 15, "retries": 2, "backoff": 3.0, "stage": "P1", "fallback_policy": "on_failure"},
    {"route_id": "concept-catalog-ths", "dataset": "concept_catalog", "provider": "akshare", "source_id": "akshare_ths", "endpoint": "stock_board_concept_name_ths", "upstream": "10jqka", "priority": 45, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 15, "retries": 2, "backoff": 3.0, "stage": "P1", "fallback_policy": "primary"},
    {"route_id": "cninfo-announcement-search", "dataset": "events", "provider": "cninfo", "source_id": "cninfo", "endpoint": "announcement_search", "upstream": "cninfo", "priority": 55, "enabled": False, "rpm": 10, "concurrency": 1, "timeout": 25, "retries": 2, "backoff": 2.0, "stage": "P1", "fallback_policy": "fill_missing"},
    {"route_id": "cninfo-industry-category", "dataset": "industry_classification", "provider": "cninfo", "source_id": "cninfo", "endpoint": "stock_industry_category_cninfo", "upstream": "cninfo", "priority": 45, "enabled": True, "rpm": 10, "concurrency": 1, "timeout": 25, "retries": 2, "backoff": 2.0, "stage": "P1", "fallback_policy": "fill_missing"},
    {"route_id": "cninfo-industry-change", "dataset": "industry_classification", "provider": "cninfo", "source_id": "cninfo", "endpoint": "stock_industry_change_cninfo", "upstream": "cninfo", "priority": 50, "enabled": True, "rpm": 10, "concurrency": 1, "timeout": 25, "retries": 2, "backoff": 2.0, "stage": "P1", "fallback_policy": "fill_missing"},
    {"route_id": "cninfo-share-change", "dataset": "corporate_actions", "provider": "cninfo", "source_id": "cninfo", "endpoint": "stock_share_change_cninfo", "upstream": "cninfo", "priority": 25, "enabled": False, "rpm": 10, "concurrency": 1, "timeout": 25, "retries": 2, "backoff": 2.0, "stage": "P1", "fallback_policy": "fill_missing"},
    {"route_id": "industry-fund-flow", "dataset": "industry_flow", "provider": "akshare", "endpoint": "stock_board_industry_fund_flow_hist", "upstream": "eastmoney", "priority": 50, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P2"},
    {"route_id": "concept-fund-flow", "dataset": "concept_flow", "provider": "akshare", "endpoint": "stock_board_concept_fund_flow_hist", "upstream": "eastmoney", "priority": 50, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P2"},
    {"route_id": "stock-events", "dataset": "events", "provider": "akshare", "endpoint": "stock_notice_report_and_news", "upstream": "eastmoney", "priority": 60, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P2"},
    {"route_id": "industry-classification-repair", "dataset": "industry_classification_repair", "provider": "akshare", "endpoint": "stock_individual_info_em", "upstream": "eastmoney", "priority": 60, "enabled": True, "rpm": 15, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P2"},
    {"route_id": "global-index-daily", "dataset": "global_index_daily", "provider": "akshare", "endpoint": "index_global_hist_em", "upstream": "eastmoney", "priority": 80, "enabled": False, "rpm": 10, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 4.0, "stage": "P2"},
)


class DataCenterStore:
    """Own additive route, quality-disposition and default-version state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS data_source_routes (
                    route_id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    upstream TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    priority INTEGER NOT NULL,
                    requests_per_minute INTEGER NOT NULL,
                    concurrency INTEGER NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    backoff_seconds REAL NOT NULL,
                    lifecycle_stage TEXT NOT NULL,
                    mapping_version TEXT NOT NULL DEFAULT 'v1',
                    last_success_at TEXT,
                    last_failure_at TEXT,
                    last_latency_ms INTEGER,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_quality_issues (
                    issue_id TEXT PRIMARY KEY,
                    dataset TEXT NOT NULL,
                    symbol TEXT,
                    observation_at TEXT,
                    rule_id TEXT NOT NULL,
                    severity TEXT NOT NULL CHECK (severity IN ('warning','error')),
                    status TEXT NOT NULL CHECK (
                        status IN ('open','quarantined','accepted','rejected','corrected','superseded')
                    ),
                    source TEXT NOT NULL,
                    data_version_id TEXT,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_quality_dispositions (
                    disposition_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    action TEXT NOT NULL CHECK (action IN ('accept','reject','quarantine','correct')),
                    reason TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (issue_id) REFERENCES data_quality_issues (issue_id)
                );

                CREATE TABLE IF NOT EXISTS data_correction_overlays (
                    overlay_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    symbol TEXT,
                    observation_at TEXT,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (issue_id) REFERENCES data_quality_issues (issue_id)
                );

                CREATE TABLE IF NOT EXISTS data_center_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_source_definitions (
                    source_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    upstream_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    verification_status TEXT NOT NULL CHECK (verification_status IN ('verified','candidate','disabled','rejected')),
                    allowed_hosts_json TEXT NOT NULL,
                    secret_env_names_json TEXT NOT NULL,
                    requests_per_minute INTEGER NOT NULL,
                    concurrency INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    notes TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_source_capabilities (
                    source_id TEXT NOT NULL,
                    endpoint_id TEXT NOT NULL,
                    dataset_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
                    verification_status TEXT NOT NULL,
                    PRIMARY KEY (source_id, endpoint_id, dataset_id),
                    FOREIGN KEY (source_id) REFERENCES data_source_definitions (source_id)
                );

                CREATE TABLE IF NOT EXISTS data_dataset_catalog (
                    dataset_id TEXT PRIMARY KEY,
                    layer_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    availability_status TEXT NOT NULL,
                    sync_enabled INTEGER NOT NULL CHECK (sync_enabled IN (0, 1)),
                    config_fields_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    producer_type TEXT NOT NULL DEFAULT 'external_source',
                    producer_id TEXT NOT NULL DEFAULT '',
                    route_required INTEGER NOT NULL DEFAULT 1 CHECK (route_required IN (0, 1)),
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_route_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    task_id TEXT,
                    dataset_id TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS data_quality_refetches (
                    refetch_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (issue_id) REFERENCES data_quality_issues (issue_id)
                );
                """
            )
            self._ensure_column(connection, "data_source_routes", "source_id", "TEXT NOT NULL DEFAULT 'akshare'")
            self._ensure_column(connection, "data_source_routes", "fallback_policy", "TEXT NOT NULL DEFAULT 'primary'")
            self._ensure_column(connection, "data_quality_issues", "source_task_id", "TEXT")
            self._ensure_column(connection, "data_quality_issues", "field_name", "TEXT")
            self._ensure_column(connection, "data_quality_dispositions", "related_task_id", "TEXT")
            self._ensure_column(connection, "data_quality_dispositions", "related_issue_id", "TEXT")
            self._ensure_column(connection, "data_quality_refetches", "completed_at", "TEXT")
            self._ensure_column(connection, "data_quality_refetches", "last_error", "TEXT")
            self._ensure_column(connection, "data_quality_refetches", "related_issue_id", "TEXT")
            cninfo_migration_applied = False
            governance_migration_applied = False
            self._ensure_column(connection, "data_dataset_catalog", "producer_type", "TEXT NOT NULL DEFAULT 'external_source'")
            self._ensure_column(connection, "data_dataset_catalog", "producer_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "data_dataset_catalog", "route_required", "INTEGER NOT NULL DEFAULT 1")
            if self._table_exists(connection, "market_schema_migrations"):
                for schema_version, description in (
                    ("86.3.5", "Enable CNInfo source with industry-only fill-missing routes"),
                    (
                        DATA_CENTER_SCHEMA_VERSION,
                        "Align dataset producers and concept/global-index route governance",
                    ),
                ):
                    migration = connection.execute(
                        """
                        INSERT OR IGNORE INTO market_schema_migrations
                            (schema_version, description, applied_at)
                        VALUES (?, ?, ?)
                        """,
                        (schema_version, description, _utc_now()),
                    )
                    if schema_version == "86.3.5":
                        cninfo_migration_applied = migration.rowcount == 1
                    elif schema_version == DATA_CENTER_SCHEMA_VERSION:
                        governance_migration_applied = migration.rowcount == 1
            for route in DEFAULT_ROUTES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_source_routes (
                        route_id, dataset, provider, endpoint, upstream, enabled,
                        priority, requests_per_minute, concurrency, timeout_seconds,
                        retry_count, backoff_seconds, lifecycle_stage, source_id,
                        fallback_policy, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route["route_id"], route["dataset"], route["provider"],
                        route["endpoint"], route["upstream"], int(route["enabled"]),
                        route["priority"], route["rpm"], route["concurrency"],
                        route["timeout"], route["retries"], route["backoff"],
                        route["stage"], route.get("source_id", route["provider"]),
                        route.get("fallback_policy", "primary"), _utc_now(),
                    ),
                )

            for source in CONTROLLED_SOURCES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_source_definitions (
                        source_id, display_name, provider_type, upstream_name, enabled,
                        verification_status, allowed_hosts_json, secret_env_names_json,
                        requests_per_minute, concurrency, retry_count, notes, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source["source_id"], source["display_name"], source["provider_type"],
                        source["upstream_name"], int(source["enabled"]), source["verification_status"],
                        _dump(source["allowed_hosts"]), _dump(source["secret_env_names"]),
                        source["requests_per_minute"], source["concurrency"], source["retry_count"],
                        source["notes"], _utc_now(),
                    ),
                )
            for dataset in DATASET_CATALOG:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_dataset_catalog (
                        dataset_id, layer_id, display_name, description, availability_status,
                        sync_enabled, config_fields_json, schema_version, producer_type,
                        producer_id, route_required, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        dataset["dataset_id"], dataset["layer_id"], dataset["display_name"],
                        dataset["description"], dataset["availability_status"],
                        int(dataset["sync_enabled"]), _dump(dataset["config_fields"]),
                        dataset["schema_version"], dataset["producer_type"],
                        dataset["producer_id"], int(dataset["route_required"]), _utc_now(),
                    ),
                )
            connection.execute(
                "UPDATE data_dataset_catalog SET sync_enabled=1, updated_at=? WHERE dataset_id='index_daily'",
                (_utc_now(),),
            )
            for route in DEFAULT_ROUTES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_source_capabilities (
                        source_id, endpoint_id, dataset_id, enabled, verification_status
                    ) VALUES (?, ?, ?, ?, 'verified')
                    """,
                    (
                        route.get("source_id", route["provider"]),
                        route["endpoint"], route["dataset"], int(route["enabled"]),
                    ),
                )
            for capability in SOURCE_CAPABILITIES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_source_capabilities (
                        source_id, endpoint_id, dataset_id, enabled, verification_status
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        capability["source_id"],
                        capability["endpoint_id"],
                        capability["dataset_id"],
                        int(capability.get("enabled", False)),
                        capability.get("verification_status", "candidate"),
                    ),
                )
            cninfo_source = next(
                source for source in CONTROLLED_SOURCES if source["source_id"] == "cninfo"
            )
            connection.execute(
                """
                UPDATE data_source_definitions
                SET display_name=?, provider_type=?, upstream_name=?,
                    verification_status=?, allowed_hosts_json=?,
                    secret_env_names_json=?, notes=?, updated_at=?
                WHERE source_id='cninfo' AND enabled=0
                  AND verification_status IN ('candidate', 'verified')
                """,
                (
                    cninfo_source["display_name"], cninfo_source["provider_type"],
                    cninfo_source["upstream_name"], cninfo_source["verification_status"],
                    _dump(cninfo_source["allowed_hosts"]),
                    _dump(cninfo_source["secret_env_names"]), cninfo_source["notes"],
                    _utc_now(),
                ),
            )
            for capability in (
                item for item in SOURCE_CAPABILITIES if item["source_id"] == "cninfo"
            ):
                connection.execute(
                    """
                    UPDATE data_source_capabilities
                    SET verification_status=?
                    WHERE source_id='cninfo' AND endpoint_id=? AND dataset_id=? AND enabled=0
                      AND EXISTS (
                          SELECT 1 FROM data_source_definitions
                          WHERE source_id='cninfo' AND enabled=0
                            AND verification_status IN ('candidate', 'verified')
                      )
                    """,
                    (
                        capability.get("verification_status", "candidate"),
                        capability["endpoint_id"], capability["dataset_id"],
                    ),
                )
            if governance_migration_applied:
                for dataset in DATASET_CATALOG:
                    connection.execute(
                        """
                        UPDATE data_dataset_catalog
                        SET producer_type=?, producer_id=?, route_required=?, updated_at=?
                        WHERE dataset_id=?
                        """,
                        (
                            dataset["producer_type"], dataset["producer_id"],
                            int(dataset["route_required"]), _utc_now(), dataset["dataset_id"],
                        ),
                    )
            if cninfo_migration_applied:
                connection.execute(
                    """
                    UPDATE data_source_definitions
                    SET enabled=1, notes=?, updated_at=?
                    WHERE source_id='cninfo' AND verification_status='verified'
                    """,
                    (cninfo_source["notes"], _utc_now()),
                )
                connection.execute(
                    """
                    UPDATE data_source_capabilities
                    SET enabled=CASE
                        WHEN endpoint_id IN (
                            'stock_industry_category_cninfo',
                            'stock_industry_change_cninfo'
                        ) AND dataset_id='industry_classification' THEN 1
                        ELSE 0
                    END
                    WHERE source_id='cninfo'
                    """
                )
                connection.execute(
                    """
                    UPDATE data_source_routes
                    SET enabled=CASE
                        WHEN route_id IN (
                            'cninfo-industry-category',
                            'cninfo-industry-change'
                        ) THEN 1
                        ELSE 0
                    END,
                    updated_at=?
                    WHERE source_id='cninfo'
                    """,
                    (_utc_now(),),
                )


    def list_sources(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                "SELECT * FROM data_source_definitions ORDER BY CASE verification_status WHEN 'verified' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END, source_id"
            ).fetchall()
            capabilities = connection.execute(
                "SELECT * FROM data_source_capabilities ORDER BY dataset_id, endpoint_id"
            ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in capabilities:
            payload = dict(row)
            payload["enabled"] = bool(payload["enabled"])
            grouped.setdefault(str(payload["source_id"]), []).append(payload)
        return [self._source_payload(row, grouped.get(str(row["source_id"]), [])) for row in rows]

    def get_source(self, source_id: str) -> dict[str, Any]:
        source = next((item for item in self.list_sources() if item["source_id"] == source_id), None)
        if source is None:
            raise KeyError(f"controlled source not found: {source_id}")
        return source

    def update_source(self, source_id: str, update: Mapping[str, Any]) -> dict[str, Any]:
        current = self.get_source(source_id)
        enabled = current["enabled"] if update.get("enabled") is None else bool(update["enabled"])
        if enabled and current["verification_status"] != "verified":
            raise ValueError("only a verified controlled source can be enabled")
        values = {
            "enabled": enabled,
            "requests_per_minute": current["requests_per_minute"] if update.get("requests_per_minute") is None else int(update["requests_per_minute"]),
            "concurrency": current["concurrency"] if update.get("concurrency") is None else int(update["concurrency"]),
            "retry_count": current["retry_count"] if update.get("retry_count") is None else int(update["retry_count"]),
        }
        if values["requests_per_minute"] < 1 or values["concurrency"] < 1 or values["retry_count"] < 0:
            raise ValueError("source rate and concurrency must be positive; retry count cannot be negative")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE data_source_definitions SET enabled=?, requests_per_minute=?,
                    concurrency=?, retry_count=?, updated_at=? WHERE source_id=?
                """,
                (int(values["enabled"]), values["requests_per_minute"], values["concurrency"],
                 values["retry_count"], _utc_now(), source_id),
            )
        return self.get_source(source_id)

    def list_datasets(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        layers = {item["layer_id"]: item for item in DATA_LAYERS}
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                "SELECT * FROM data_dataset_catalog ORDER BY layer_id, display_name, dataset_id"
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["sync_enabled"] = bool(payload["sync_enabled"])
            payload["route_required"] = bool(payload["route_required"])
            payload["config_fields"] = json.loads(str(payload.pop("config_fields_json") or "[]"))
            layer = layers.get(str(payload["layer_id"]), {})
            payload["layer_name"] = layer.get("display_name", payload["layer_id"])
            payload["layer_description"] = layer.get("description", "")
            items.append(payload)
        return items

    def freeze_route_snapshot(self, dataset_id: str, *, task_id: str) -> dict[str, Any]:
        routes = [route for route in self.list_routes() if route["dataset"] == dataset_id and route["enabled"]]
        sources = {source["source_id"]: source for source in self.list_sources()}
        usable = [
            route for route in routes
            if sources.get(str(route.get("source_id")), {}).get("enabled")
            and sources.get(str(route.get("source_id")), {}).get("verification_status") == "verified"
        ]
        if not usable:
            raise ValueError(f"dataset has no enabled verified route: {dataset_id}")
        snapshot_id = f"drs-{uuid.uuid4().hex}"
        payload = {"dataset_id": dataset_id, "task_id": task_id, "routes": usable}
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_route_snapshots
                    (snapshot_id, task_id, dataset_id, snapshot_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, task_id, dataset_id, _dump(payload), _utc_now()),
            )
        return {"snapshot_id": snapshot_id, **payload}

    def list_routes(self) -> list[dict[str, Any]]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                "SELECT * FROM data_source_routes ORDER BY priority, dataset, route_id"
            ).fetchall()
        return [self._route_payload(row) for row in rows]

    def get_route(self, route_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM data_source_routes WHERE route_id=?", (route_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"route not found: {route_id}")
        return self._route_payload(row)

    def update_routes(self, routes: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        self.ensure_schema()
        current_routes = {route["route_id"]: route for route in self.list_routes()}
        allowed = set(current_routes)
        sources = {source["source_id"]: source for source in self.list_sources()}
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            for update in routes:
                route_id = str(update.get("route_id") or "")
                if route_id not in allowed:
                    raise KeyError(f"route not found: {route_id}")
                current = current_routes[route_id]
                values = {
                    "enabled": bool(update.get("enabled", current["enabled"])),
                    "priority": int(update.get("priority", current["priority"])),
                    "requests_per_minute": int(update.get("requests_per_minute", current["requests_per_minute"])),
                    "concurrency": int(update.get("concurrency", current["concurrency"])),
                    "timeout_seconds": int(update.get("timeout_seconds", current["timeout_seconds"])),
                    "retry_count": int(update.get("retry_count", current["retry_count"])),
                    "backoff_seconds": float(update.get("backoff_seconds", current["backoff_seconds"])),
                    "source_id": str(update.get("source_id") or current.get("source_id") or "akshare"),
                    "fallback_policy": str(update.get("fallback_policy") or current.get("fallback_policy") or "primary"),
                }
                if min(values["requests_per_minute"], values["concurrency"], values["timeout_seconds"]) < 1:
                    raise ValueError("rate, concurrency and timeout must be positive")
                if values["retry_count"] < 0 or values["fallback_policy"] not in {"primary", "fill_missing", "on_failure"}:
                    raise ValueError("invalid retry count or fallback policy")
                source = sources.get(values["source_id"])
                if source is None:
                    raise ValueError("route source must come from the controlled registry")
                capability = connection.execute(
                    """
                    SELECT verification_status FROM data_source_capabilities
                    WHERE source_id=? AND endpoint_id=? AND dataset_id=?
                    """,
                    (values["source_id"], current["endpoint"], current["dataset"]),
                ).fetchone()
                if values["enabled"] and (
                    not source["enabled"] or source["verification_status"] != "verified"
                    or capability is None or capability["verification_status"] != "verified"
                ):
                    raise ValueError("enabled routes require an enabled verified source capability")
                connection.execute(
                    """
                    UPDATE data_source_routes SET enabled=?, priority=?,
                        requests_per_minute=?, concurrency=?, timeout_seconds=?,
                        retry_count=?, backoff_seconds=?, source_id=?, fallback_policy=?, updated_at=?
                    WHERE route_id=?
                    """,
                    (
                        int(values["enabled"]), values["priority"], values["requests_per_minute"],
                        values["concurrency"], values["timeout_seconds"], values["retry_count"],
                        values["backoff_seconds"], values["source_id"], values["fallback_policy"],
                        now, route_id,
                    ),
                )
            duplicate_primary = connection.execute(
                """
                SELECT dataset FROM data_source_routes
                WHERE enabled=1 AND fallback_policy='primary'
                GROUP BY dataset HAVING COUNT(*) > 1
                LIMIT 1
                """
            ).fetchone()
            if duplicate_primary is not None:
                raise ValueError(f"dataset has multiple enabled primary routes: {duplicate_primary['dataset']}")
        return self.list_routes()

    def record_route_probe(
        self, route_id: str, *, succeeded: bool, latency_ms: int, error: str | None = None
    ) -> None:
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE data_source_routes SET
                    last_success_at=CASE WHEN ? THEN ? ELSE last_success_at END,
                    last_failure_at=CASE WHEN ? THEN last_failure_at ELSE ? END,
                    last_latency_ms=?, last_error=?, updated_at=?
                WHERE route_id=?
                """,
                (int(succeeded), now, int(succeeded), now, latency_ms, error, now, route_id),
            )

    def create_issue(self, issue: Mapping[str, Any]) -> dict[str, Any]:
        self.ensure_schema()
        now = _utc_now()
        issue_id = str(issue.get("issue_id") or f"dqi-{uuid.uuid4().hex}")
        severity = str(issue.get("severity") or "warning")
        status = str(issue.get("status") or "open")
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO data_quality_issues (
                    issue_id, dataset, symbol, observation_at, rule_id, severity,
                    status, source, data_version_id, evidence_json, source_task_id,
                    field_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    issue_id, str(issue.get("dataset") or "unknown"),
                    _optional_text(issue.get("symbol")),
                    _optional_text(issue.get("observation_at")),
                    str(issue.get("rule_id") or "unknown"), severity, status,
                    str(issue.get("source") or "unknown"),
                    _optional_text(issue.get("data_version_id")),
                    _dump(dict(issue.get("evidence") or {})),
                    _optional_text(issue.get("source_task_id")),
                    _optional_text(issue.get("field_name")), now, now,
                ),
            )
        return self.get_issue(issue_id)

    @staticmethod
    def _quality_filter_clause(
        *, status: str = "", severity: str = "", dataset: str = "",
        source_task_id: str = "", source: str = "", symbol: str = "", rule_id: str = "",
        date_from: str = "", date_to: str = "",
    ) -> tuple[str, list[Any]]:
        filters: list[str] = []
        values: list[Any] = []
        for column, raw, allowed in (
            ("status", status, {"open", "quarantined", "accepted", "rejected", "corrected", "superseded"}),
            ("severity", severity, {"warning", "error"}),
        ):
            selected = _split_csv(raw)
            invalid = [value for value in selected if value not in allowed]
            if invalid:
                raise ValueError(f"invalid {column} filter: {','.join(invalid)}")
            if selected:
                filters.append(f"{column} IN ({','.join('?' for _ in selected)})")
                values.extend(selected)
        for column, value in (
            ("dataset", dataset), ("source_task_id", source_task_id), ("source", source),
            ("symbol", symbol), ("rule_id", rule_id),
        ):
            if value:
                filters.append(f"{column}=?")
                values.append(value)
        if date_from:
            _validate_iso_date(date_from, "date_from")
            filters.append("substr(observation_at, 1, 10)>=?")
            values.append(date_from)
        if date_to:
            _validate_iso_date(date_to, "date_to")
            filters.append("substr(observation_at, 1, 10)<=?")
            values.append(date_to)
        if date_from and date_to and date_from > date_to:
            raise ValueError("date_from must not be later than date_to")
        return (f"WHERE {' AND '.join(filters)}" if filters else "", values)

    def list_issues(
        self, *, status: str = "", severity: str = "", dataset: str = "",
        source_task_id: str = "", source: str = "", symbol: str = "", rule_id: str = "",
        date_from: str = "", date_to: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        where, values = self._quality_filter_clause(
            status=status, severity=severity, dataset=dataset,
            source_task_id=source_task_id, source=source, symbol=symbol, rule_id=rule_id,
            date_from=date_from, date_to=date_to,
        )
        values.append(max(1, min(int(limit), 500)))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"SELECT * FROM data_quality_issues {where} ORDER BY created_at DESC LIMIT ?",
                values,
            ).fetchall()
        return [self._issue_payload(row) for row in rows]

    def summarize_issues(
        self, *, severity: str = "", dataset: str = "", source_task_id: str = "", source: str = "",
        symbol: str = "", rule_id: str = "", date_from: str = "", date_to: str = "",
    ) -> dict[str, Any]:
        self.ensure_schema()
        where, values = self._quality_filter_clause(
            severity=severity, dataset=dataset, source_task_id=source_task_id, source=source,
            symbol=symbol, rule_id=rule_id, date_from=date_from, date_to=date_to,
        )
        with closing(self._connect(read_only=True)) as connection:
            status_counts = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    f"SELECT status, COUNT(*) AS count FROM data_quality_issues {where} GROUP BY status",
                    values,
                ).fetchall()
            }
            severity_counts = {
                str(row["severity"]): int(row["count"])
                for row in connection.execute(
                    f"SELECT severity, COUNT(*) AS count FROM data_quality_issues {where} GROUP BY severity",
                    values,
                ).fetchall()
            }
        return {
            "total": sum(status_counts.values()),
            "status_counts": status_counts,
            "severity_counts": severity_counts,
        }


    def quality_facets(self) -> dict[str, list[dict[str, Any]]]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            result: dict[str, list[dict[str, Any]]] = {}
            for column, key in (
                ("dataset", "datasets"), ("source", "sources"),
                ("rule_id", "rules"), ("source_task_id", "tasks"),
            ):
                rows = connection.execute(
                    f"""
                    SELECT {column} AS value, COUNT(*) AS count
                    FROM data_quality_issues
                    WHERE {column} IS NOT NULL AND TRIM({column})<>''
                    GROUP BY {column} ORDER BY count DESC, value
                    """
                ).fetchall()
                result[key] = [
                    {"value": str(row["value"]), "count": int(row["count"])}
                    for row in rows
                ]
        return result
    def get_issue(self, issue_id: str) -> dict[str, Any]:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM data_quality_issues WHERE issue_id=?", (issue_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"quality issue not found: {issue_id}")
        return self._issue_payload(row)

    def get_issue_history(self, issue_id: str) -> dict[str, Any]:
        issue = self.get_issue(issue_id)
        with closing(self._connect(read_only=True)) as connection:
            dispositions = [dict(row) for row in connection.execute(
                "SELECT * FROM data_quality_dispositions WHERE issue_id=? ORDER BY created_at",
                (issue_id,),
            ).fetchall()]
            overlays = [dict(row) for row in connection.execute(
                "SELECT * FROM data_correction_overlays WHERE issue_id=? ORDER BY created_at",
                (issue_id,),
            ).fetchall()]
            refetches = [dict(row) for row in connection.execute(
                "SELECT * FROM data_quality_refetches WHERE issue_id=? ORDER BY created_at",
                (issue_id,),
            ).fetchall()]
        for overlay in overlays:
            overlay["before"] = json.loads(str(overlay.pop("before_json") or "{}"))
            overlay["after"] = json.loads(str(overlay.pop("after_json") or "{}"))
        return {"issue": issue, "dispositions": dispositions, "overlays": overlays, "refetches": refetches}

    def record_refetch(self, issue_id: str, task_id: str) -> dict[str, Any]:
        self.get_issue(issue_id)
        payload = {
            "refetch_id": f"dqf-{uuid.uuid4().hex}", "issue_id": issue_id,
            "task_id": task_id, "status": "queued", "created_at": _utc_now(),
        }
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_quality_refetches
                    (refetch_id, issue_id, task_id, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
        return payload

    def update_refetch(
        self, refetch_id: str, *, status: str, last_error: str = "",
        related_issue_id: str = "",
    ) -> dict[str, Any]:
        terminal = status in {"completed", "completed_noop", "published", "partial_failure", "failed", "interrupted", "stopped"}
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE data_quality_refetches SET
                    status=?,
                    completed_at=COALESCE(completed_at, ?),
                    last_error=COALESCE(?, last_error),
                    related_issue_id=COALESCE(?, related_issue_id)
                WHERE refetch_id=?
                """,
                (
                    status, _utc_now() if terminal else None,
                    last_error or None, related_issue_id or None, refetch_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM data_quality_refetches WHERE refetch_id=?", (refetch_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"quality refetch not found: {refetch_id}")
        return dict(row)

    def disposition_issue(
        self,
        issue_id: str,
        *,
        action: str,
        reason: str,
        operator: str,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("disposition reason is required")
        statuses = {"accept": "accepted", "reject": "rejected", "quarantine": "quarantined", "correct": "corrected"}
        if action not in statuses:
            raise ValueError(f"unsupported disposition action: {action}")
        issue = self.get_issue(issue_id)
        if issue["status"] not in {"open", "quarantined"}:
            raise ValueError(f"quality issue is already resolved: {issue_id}")
        if action == "correct" and (before is None or after is None):
            raise ValueError("correction requires before and after values")
        now = _utc_now()
        disposition_id = f"dqd-{uuid.uuid4().hex}"
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_quality_dispositions
                    (disposition_id, issue_id, action, reason, operator, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (disposition_id, issue_id, action, reason.strip(), operator or "local-user", now),
            )
            if action == "correct":
                connection.execute(
                    """
                    INSERT INTO data_correction_overlays (
                        overlay_id, issue_id, dataset, symbol, observation_at,
                        before_json, after_json, reason, operator, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"dco-{uuid.uuid4().hex}", issue_id, issue["dataset"],
                        issue.get("symbol"), issue.get("observation_at"),
                        _dump(dict(before or {})), _dump(dict(after or {})),
                        reason.strip(), operator or "local-user", now,
                    ),
                )
            connection.execute(
                "UPDATE data_quality_issues SET status=?, updated_at=? WHERE issue_id=?",
                (statuses[action], now, issue_id),
            )
        return self.get_issue(issue_id)

    def bulk_disposition_issues(
        self, issue_ids: Sequence[str], *, action: str, reason: str, operator: str,
    ) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(str(issue_id).strip() for issue_id in issue_ids if str(issue_id).strip()))
        if not ids:
            raise ValueError("at least one quality issue is required")
        if len(ids) > 200:
            raise ValueError("at most 200 quality issues can be processed at once")
        if action not in {"accept", "reject", "quarantine"}:
            raise ValueError("bulk action must be accept, reject or quarantine")
        if not reason.strip():
            raise ValueError("bulk disposition reason is required")
        placeholders = ",".join("?" for _ in ids)
        statuses = {"accept": "accepted", "reject": "rejected", "quarantine": "quarantined"}
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                f"SELECT * FROM data_quality_issues WHERE issue_id IN ({placeholders})", ids
            ).fetchall()
            if len(rows) != len(ids):
                found = {str(row["issue_id"]) for row in rows}
                missing = [issue_id for issue_id in ids if issue_id not in found]
                raise KeyError(f"quality issue not found: {','.join(missing)}")
            cohorts = {(str(row["dataset"]), str(row["rule_id"])) for row in rows}
            if len(cohorts) != 1:
                raise ValueError("bulk disposition cannot mix datasets or quality rules")
            resolved = [str(row["issue_id"]) for row in rows if str(row["status"]) not in {"open", "quarantined"}]
            if resolved:
                raise ValueError(f"bulk disposition includes resolved issues: {','.join(resolved)}")
            for issue_id in ids:
                connection.execute(
                    """
                    INSERT INTO data_quality_dispositions
                        (disposition_id, issue_id, action, reason, operator, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"dqd-{uuid.uuid4().hex}", issue_id, action, reason.strip(),
                        operator or "local-user", now,
                    ),
                )
                connection.execute(
                    "UPDATE data_quality_issues SET status=?, updated_at=? WHERE issue_id=?",
                    (statuses[action], now, issue_id),
                )
        return [self.get_issue(issue_id) for issue_id in ids]

    def list_versions(self) -> dict[str, Any]:
        self.ensure_schema()
        if not self._has_table("data_versions"):
            return {
                "default_version_id": None, "default_version": None,
                "latest_published_version_id": None, "latest_published_version": None,
                "items": [],
            }
        with closing(self._connect(read_only=True)) as connection:
            default_row = connection.execute(
                "SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'"
            ).fetchone()
            rows = connection.execute(
                """
                SELECT v.*, COUNT(m.dataset) AS member_count,
                       COALESCE(SUM(m.row_count), 0) AS row_count
                FROM data_versions v
                LEFT JOIN data_version_members m ON m.data_version_id=v.data_version_id
                GROUP BY v.data_version_id
                ORDER BY v.as_of_trade_date DESC, v.created_at DESC
                """
            ).fetchall()
        default_id = str(default_row["setting_value"]) if default_row else None
        items = [{**dict(row), "is_default": str(row["data_version_id"]) == default_id} for row in rows]
        default = next((item for item in items if item["is_default"]), None)
        published = [item for item in items if item.get("status") in {"published", "superseded"}]
        latest = max(
            published,
            key=lambda item: (str(item.get("published_at") or ""), str(item.get("created_at") or "")),
            default=None,
        )
        return {
            "default_version_id": default_id if default else None,
            "default_version": default,
            "latest_published_version_id": latest.get("data_version_id") if latest else None,
            "latest_published_version": latest,
            "items": items,
        }

    def set_default_version(self, version_id: str) -> dict[str, Any]:
        versions = self.list_versions()["items"]
        selected = next((item for item in versions if item["data_version_id"] == version_id), None)
        if selected is None:
            raise KeyError(f"data version not found: {version_id}")
        if selected["status"] not in {"published", "superseded"}:
            raise ValueError("only published or superseded versions can become default")
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_center_settings (setting_key, setting_value, updated_at)
                VALUES ('default_data_version_id', ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value=excluded.setting_value, updated_at=excluded.updated_at
                """,
                (version_id, now),
            )
        return {"status": "default_updated", "default_version_id": version_id, "updated_at": now}

    def list_assets(self, *, version_id: str = "") -> dict[str, Any]:
        versions = self.list_versions()
        selected = version_id or versions["default_version_id"]
        members: list[dict[str, Any]] = []
        if selected and self._has_table("data_version_members"):
            with closing(self._connect(read_only=True)) as connection:
                rows = connection.execute(
                    "SELECT * FROM data_version_members WHERE data_version_id=? ORDER BY dataset, adjustment",
                    (selected,),
                ).fetchall()
            members = [dict(row) for row in rows]
        return {"version_id": selected, "items": members}

    def get_overview(self) -> dict[str, Any]:
        self.ensure_schema()
        versions = self.list_versions()
        default = versions["default_version"]
        latest_published = versions["latest_published_version"]
        with closing(self._connect(read_only=True)) as connection:
            issue_counts = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    "SELECT status, COUNT(*) AS count FROM data_quality_issues GROUP BY status"
                ).fetchall()
            }
            latest_observation = None
            if self._table_exists(connection, "market_daily_prices"):
                latest_observation = connection.execute(
                    "SELECT MAX(trade_date) FROM market_daily_prices"
                ).fetchone()[0]
        return {
            "schema_version": DATA_CENTER_SCHEMA_VERSION,
            "database_path": str(self.database_path.resolve()),
            "database_size_bytes": self.database_path.stat().st_size if self.database_path.exists() else 0,
            "route_count": len(self.list_routes()),
            "issue_counts": issue_counts,
            "default_version": default,
            "latest_published_version": latest_published,
            "default_differs_from_latest": bool(
                default and latest_published
                and default.get("data_version_id") != latest_published.get("data_version_id")
            ),
            "published_cutoff": default.get("as_of_trade_date") if default else None,
            "latest_published_cutoff": latest_published.get("as_of_trade_date") if latest_published else None,
            "latest_observation_date": latest_observation,
            "has_unpublished_observations": bool(
                latest_observation and default and latest_observation > str(default.get("as_of_trade_date") or "")
            ),
        }

    def _has_table(self, table: str) -> bool:
        with closing(self._connect(read_only=True)) as connection:
            return self._table_exists(connection, table)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone() is not None

    @staticmethod
    def _source_payload(row: sqlite3.Row, capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        payload["allowed_hosts"] = json.loads(str(payload.pop("allowed_hosts_json") or "[]"))
        payload["secret_env_names"] = json.loads(str(payload.pop("secret_env_names_json") or "[]"))
        payload["capabilities"] = capabilities
        return payload

    @staticmethod
    def _route_payload(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["enabled"] = bool(payload["enabled"])
        return payload

    @staticmethod
    def _issue_payload(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        payload["evidence"] = json.loads(str(payload.pop("evidence_json") or "{}"))
        return payload

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            connection = sqlite3.connect(
                f"file:{self.database_path.resolve().as_posix()}?mode=ro", uri=True
            )
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _split_csv(value: str) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in str(value or "").split(",") if item.strip()))


def _validate_iso_date(value: str, field: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
