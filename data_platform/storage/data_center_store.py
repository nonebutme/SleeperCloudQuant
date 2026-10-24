"""Stage-86 additive control-plane storage for the local data center."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from data_platform.data_center_catalog import (
    CONTROLLED_SOURCES,
    DATASET_CATALOG,
    DATA_LAYERS,
    SOURCE_CAPABILITIES,
)


DATA_CENTER_SCHEMA_VERSION = "91.0.0"
GLOBAL_INDEX_SINA_MIGRATION = "global-index-sina.v1"
GLOBAL_INDEX_GOVERNANCE_MIGRATION = "global-index-governance.v2"

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
    {"route_id": "industry-classification-repair", "dataset": "industry_classification_repair", "provider": "cninfo", "source_id": "cninfo", "endpoint": "stock_industry_change_cninfo", "upstream": "cninfo", "priority": 60, "enabled": True, "rpm": 10, "concurrency": 1, "timeout": 25, "retries": 2, "backoff": 2.0, "stage": "P1"},
    {"route_id": "global-index-us-sina", "dataset": "global_index_daily", "provider": "akshare", "endpoint": "index_us_stock_sina", "upstream": "sina", "priority": 10, "enabled": True, "rpm": 20, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P1", "fallback_policy": "primary", "partition_key": "US"},
    {"route_id": "global-index-international-sina", "dataset": "global_index_daily", "provider": "akshare", "endpoint": "index_global_hist_sina", "upstream": "sina", "priority": 20, "enabled": True, "rpm": 20, "concurrency": 1, "timeout": 60, "retries": 2, "backoff": 3.0, "stage": "P1", "fallback_policy": "primary", "partition_key": "INTERNATIONAL"},
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
                CREATE TABLE IF NOT EXISTS data_source_probes (
                    probe_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    route_id TEXT,
                    dataset_id TEXT NOT NULL,
                    endpoint_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_code TEXT,
                    error_class TEXT,
                    latency_ms INTEGER NOT NULL,
                    sample_rows INTEGER NOT NULL DEFAULT 0,
                    retryable INTEGER NOT NULL DEFAULT 0 CHECK (retryable IN (0, 1)),
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_source_probes_target_created
                    ON data_source_probes (source_id, dataset_id, endpoint_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS data_quality_remediations (
                    remediation_id TEXT PRIMARY KEY,
                    issue_id TEXT NOT NULL,
                    method TEXT NOT NULL,
                    executor_type TEXT NOT NULL,
                    executor_id TEXT,
                    status TEXT NOT NULL,
                    data_version_id TEXT,
                    verification_scan_id TEXT,
                    reason TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (issue_id) REFERENCES data_quality_issues (issue_id)
                );
                CREATE INDEX IF NOT EXISTS idx_quality_remediations_issue
                    ON data_quality_remediations (issue_id, created_at);
                CREATE TABLE IF NOT EXISTS index_component_intervals (
                    index_code TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    source TEXT NOT NULL,
                    source_version TEXT NOT NULL DEFAULT '',
                    observed_at TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (index_code, symbol, valid_from, source)
                );
                CREATE INDEX IF NOT EXISTS idx_index_components_asof
                    ON index_component_intervals
                    (index_code, valid_from, valid_to, symbol);
                """
            )
            self._ensure_column(connection, "data_source_routes", "source_id", "TEXT NOT NULL DEFAULT 'akshare'")
            self._ensure_column(connection, "data_source_routes", "fallback_policy", "TEXT NOT NULL DEFAULT 'primary'")
            self._ensure_column(connection, "data_source_routes", "partition_key", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "data_quality_issues", "source_task_id", "TEXT")
            self._ensure_column(connection, "data_quality_issues", "field_name", "TEXT")
            self._ensure_column(connection, "data_quality_issues", "issue_category", "TEXT NOT NULL DEFAULT 'consistency'")
            self._ensure_column(connection, "data_quality_issues", "workflow_status", "TEXT NOT NULL DEFAULT 'open'")
            self._ensure_column(connection, "data_quality_issues", "block_release", "INTEGER NOT NULL DEFAULT 1")
            connection.execute(
                """
                UPDATE data_quality_issues
                SET workflow_status=status
                WHERE workflow_status='open' AND status<>'open'
                """
            )
            self._ensure_column(connection, "data_quality_dispositions", "related_task_id", "TEXT")
            self._ensure_column(connection, "data_quality_dispositions", "related_issue_id", "TEXT")
            self._ensure_column(connection, "data_quality_refetches", "completed_at", "TEXT")
            self._ensure_column(connection, "data_quality_refetches", "last_error", "TEXT")
            self._ensure_column(connection, "data_quality_refetches", "related_issue_id", "TEXT")
            self._ensure_column(connection, "data_correction_overlays", "status", "TEXT NOT NULL DEFAULT 'pending_publish'")
            self._ensure_column(connection, "data_correction_overlays", "data_version_id", "TEXT")
            cninfo_migration_applied = False
            governance_migration_applied = False
            global_index_migration_applied = False
            global_index_governance_applied = False
            self._ensure_column(connection, "data_dataset_catalog", "producer_type", "TEXT NOT NULL DEFAULT 'external_source'")
            self._ensure_column(connection, "data_dataset_catalog", "producer_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "data_dataset_catalog", "route_required", "INTEGER NOT NULL DEFAULT 1")
            if self._table_exists(connection, "market_schema_migrations"):
                for schema_version, description in (
                    ("86.3.5", "Enable CNInfo source with industry-only fill-missing routes"),
                    (
                        GLOBAL_INDEX_SINA_MIGRATION,
                        "Enable bounded Sina global-index routes and manual synchronization",
                    ),
                    (
                        GLOBAL_INDEX_GOVERNANCE_MIGRATION,
                        "Model global-index routes as required market partitions",
                    ),
                    (
                        DATA_CENTER_SCHEMA_VERSION,
                        "Add stage-91 source probes, effective task config and remediation lifecycle",
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
                    elif schema_version == GLOBAL_INDEX_SINA_MIGRATION:
                        global_index_migration_applied = migration.rowcount == 1
                    elif schema_version == GLOBAL_INDEX_GOVERNANCE_MIGRATION:
                        global_index_governance_applied = migration.rowcount == 1
                    elif schema_version == DATA_CENTER_SCHEMA_VERSION:
                        governance_migration_applied = migration.rowcount == 1
            for route in DEFAULT_ROUTES:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO data_source_routes (
                        route_id, dataset, provider, endpoint, upstream, enabled,
                        priority, requests_per_minute, concurrency, timeout_seconds,
                        retry_count, backoff_seconds, lifecycle_stage, source_id,
                        fallback_policy, partition_key, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        route["route_id"], route["dataset"], route["provider"],
                        route["endpoint"], route["upstream"], int(route["enabled"]),
                        route["priority"], route["rpm"], route["concurrency"],
                        route["timeout"], route["retries"], route["backoff"],
                        route["stage"], route.get("source_id", route["provider"]),
                        route.get("fallback_policy", "primary"),
                        route.get("partition_key", ""), _utc_now(),
                    ),
                )
            if global_index_governance_applied:
                connection.execute(
                    """
                    UPDATE data_source_routes
                    SET fallback_policy='primary', partition_key=CASE route_id
                        WHEN 'global-index-us-sina' THEN 'US'
                        WHEN 'global-index-international-sina' THEN 'INTERNATIONAL'
                        ELSE partition_key
                    END, updated_at=?
                    WHERE route_id IN (
                        'global-index-us-sina',
                        'global-index-international-sina'
                    )
                    """,
                    (_utc_now(),),
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
            if global_index_migration_applied:
                global_definition = next(
                    item for item in DATASET_CATALOG
                    if item["dataset_id"] == "global_index_daily"
                )
                connection.execute(
                    """
                    UPDATE data_dataset_catalog
                    SET description=?, availability_status=?, sync_enabled=?,
                        config_fields_json=?, updated_at=?
                    WHERE dataset_id='global_index_daily'
                    """,
                    (
                        global_definition["description"],
                        global_definition["availability_status"],
                        int(global_definition["sync_enabled"]),
                        _dump(global_definition["config_fields"]), _utc_now(),
                    ),
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
            if global_index_migration_applied:
                for endpoint_id in ("index_us_stock_sina", "index_global_hist_sina"):
                    connection.execute(
                        """
                        UPDATE data_source_capabilities
                        SET enabled=1, verification_status='verified'
                        WHERE source_id='akshare' AND endpoint_id=?
                          AND dataset_id='global_index_daily'
                        """,
                        (endpoint_id,),
                    )
            akshare_source = next(
                source for source in CONTROLLED_SOURCES if source["source_id"] == "akshare"
            )
            connection.execute(
                """
                UPDATE data_source_definitions
                SET allowed_hosts_json=?, updated_at=?
                WHERE source_id='akshare' AND verification_status='verified'
                """,
                (_dump(akshare_source["allowed_hosts"]), _utc_now()),
            )
            # This THS endpoint returns a board-name catalog. It cannot satisfy the
            # stock-to-industry point-in-time classification contract it was once
            # registered against, so it must never be treated as testable.
            connection.execute(
                """
                UPDATE data_source_capabilities
                SET enabled=0, verification_status='rejected'
                WHERE source_id='akshare_ths'
                  AND endpoint_id='stock_board_industry_name_ths'
                  AND dataset_id='industry_classification'
                """
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
                        WHEN endpoint_id='stock_industry_category_cninfo'
                             AND dataset_id='industry_classification' THEN 1
                        WHEN endpoint_id='stock_industry_change_cninfo'
                             AND dataset_id IN (
                                 'industry_classification',
                                 'industry_classification_repair'
                             ) THEN 1
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
                            'cninfo-industry-change',
                            'industry-classification-repair'
                        ) THEN 1
                        ELSE 0
                    END,
                    updated_at=?
                    WHERE source_id='cninfo'
                    """,
                    (_utc_now(),),
                )
            # Repair historical control-plane drift without overriding valid
            # operator choices. The repair executor has always called the
            # controlled CNInfo industry-history endpoint; its old AKShare
            # lifecycle route therefore described a different dataset.
            connection.execute(
                """
                UPDATE data_source_routes
                SET provider='cninfo', source_id='cninfo',
                    endpoint='stock_industry_change_cninfo', upstream='cninfo',
                    requests_per_minute=10, concurrency=1, timeout_seconds=25,
                    retry_count=2, backoff_seconds=2.0, lifecycle_stage='P1',
                    last_success_at=NULL, last_failure_at=NULL,
                    last_latency_ms=NULL, last_error=NULL, updated_at=?
                WHERE route_id='industry-classification-repair'
                  AND source_id='akshare'
                  AND endpoint='stock_individual_info_em'
                """,
                (_utc_now(),),
            )
            connection.execute(
                """
                UPDATE data_source_capabilities
                SET enabled=0, verification_status='rejected'
                WHERE source_id='akshare'
                  AND endpoint_id='stock_individual_info_em'
                  AND dataset_id='industry_classification_repair'
                """
            )
            # An enabled route must never outlive the enabled, verified source
            # capability that authorizes its endpoint. This also repairs the
            # previously drifted global-index route while preserving all valid
            # route settings.
            connection.execute(
                """
                UPDATE data_source_routes AS route
                SET enabled=0, updated_at=?
                WHERE route.enabled=1 AND NOT EXISTS (
                    SELECT 1
                    FROM data_source_definitions AS source
                    JOIN data_source_capabilities AS capability
                      ON capability.source_id=source.source_id
                    WHERE source.source_id=route.source_id
                      AND source.enabled=1
                      AND source.verification_status='verified'
                      AND capability.endpoint_id=route.endpoint
                      AND capability.dataset_id=route.dataset
                      AND capability.enabled=1
                      AND capability.verification_status='verified'
                )
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
        definitions = {item["dataset_id"]: item for item in DATASET_CATALOG}
        for row in rows:
            payload = dict(row)
            payload["sync_enabled"] = bool(payload["sync_enabled"])
            payload["route_required"] = bool(payload["route_required"])
            payload["config_fields"] = json.loads(str(payload.pop("config_fields_json") or "[]"))
            layer = layers.get(str(payload["layer_id"]), {})
            payload["layer_name"] = layer.get("display_name", payload["layer_id"])
            payload["layer_description"] = layer.get("description", "")
            definition = definitions.get(str(payload["dataset_id"]), {})
            payload["acquisition_mode"] = definition.get("acquisition_mode", "manual_sync")
            payload["acquisition_note"] = definition.get(
                "acquisition_note", "通过数据中心同步任务下载"
            )
            payload["required_route_partitions"] = list(
                definition.get("required_route_partitions") or []
            )
            items.append(payload)
        return items

    @staticmethod
    def required_route_partitions(dataset_id: str) -> tuple[str, ...]:
        definition = next((
            item for item in DATASET_CATALOG
            if item["dataset_id"] == dataset_id
        ), {})
        return tuple(
            str(item) for item in definition.get("required_route_partitions") or ()
        )

    def missing_route_partitions(
        self, dataset_id: str, routes: Sequence[Mapping[str, Any]],
    ) -> list[str]:
        required = set(self.required_route_partitions(dataset_id))
        available = {
            str(route.get("partition_key") or "")
            for route in routes if route.get("enabled")
        }
        return sorted(required - available)

    def assert_route_coverage(
        self, dataset_id: str, routes: Sequence[Mapping[str, Any]],
    ) -> None:
        if not routes:
            raise ValueError(f"dataset has no enabled verified route: {dataset_id}")
        missing = self.missing_route_partitions(dataset_id, routes)
        if missing:
            raise ValueError(
                f"dataset is missing required route partitions: {dataset_id}: "
                + ", ".join(missing)
            )

    @staticmethod
    def _route_is_usable(
        route: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        source = sources.get(str(route.get("source_id") or ""), {})
        if not (
            route.get("enabled")
            and source.get("enabled")
            and source.get("verification_status") == "verified"
        ):
            return False
        return any(
            capability.get("dataset_id") == route.get("dataset")
            and capability.get("endpoint_id") == route.get("endpoint")
            and capability.get("enabled")
            and capability.get("verification_status") == "verified"
            for capability in source.get("capabilities") or []
        )

    def freeze_route_snapshot(self, dataset_id: str, *, task_id: str) -> dict[str, Any]:
        routes = [route for route in self.list_routes() if route["dataset"] == dataset_id and route["enabled"]]
        sources = {source["source_id"]: source for source in self.list_sources()}
        usable = [
            route for route in routes
            if self._route_is_usable(route, sources)
        ]
        self.assert_route_coverage(dataset_id, usable)
        frozen_routes = [
            self._effective_route_payload(route, sources) for route in usable
        ]
        snapshot_id = f"drs-{uuid.uuid4().hex}"
        payload = {
            "dataset_id": dataset_id,
            "task_id": task_id,
            "routes": frozen_routes,
            "effective_config": self.effective_route_config(
                dataset_id, routes=frozen_routes
            ),
        }
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

    def effective_route_config(
        self, dataset_id: str, *, routes: Sequence[Mapping[str, Any]] | None = None,
        require_complete_route_coverage: bool = True,
    ) -> dict[str, Any]:
        usable = list(routes or [
            route for route in self.list_routes()
            if route["dataset"] == dataset_id and route["enabled"]
        ])
        sources = {source["source_id"]: source for source in self.list_sources()}
        usable = [
            dict(route) for route in usable
            if self._route_is_usable(route, sources)
        ]
        if require_complete_route_coverage:
            self.assert_route_coverage(dataset_id, usable)
        elif not usable:
            raise ValueError(f"dataset has no enabled verified route: {dataset_id}")
        usable.sort(key=lambda item: (int(item["priority"]), str(item["route_id"])))
        primary = usable[0]
        source = sources[str(primary["source_id"])]
        return {
            "dataset_id": dataset_id,
            "route_id": primary["route_id"],
            "source_id": primary["source_id"],
            "provider": primary["provider"],
            "endpoint": primary["endpoint"],
            "upstream": primary["upstream"],
            "fallback_policy": primary.get("fallback_policy") or "primary",
            "allowed_hosts": list(source.get("allowed_hosts") or []),
            "required_hosts": _required_hosts(str(primary.get("upstream") or "")),
            "requests_per_minute": min(
                int(primary["requests_per_minute"]), int(source["requests_per_minute"])
            ),
            "concurrency": min(int(primary["concurrency"]), int(source["concurrency"])),
            "timeout_seconds": int(primary["timeout_seconds"]),
            "retry_count": min(int(primary["retry_count"]), int(source["retry_count"])),
            "backoff_seconds": float(primary["backoff_seconds"]),
            "fallback_routes": [
                {
                    "route_id": item["route_id"],
                    "source_id": item["source_id"],
                    "fallback_policy": item.get("fallback_policy") or "primary",
                }
                for item in usable[1:]
            ],
            "route_partitions": [
                {
                    "partition_key": item.get("partition_key") or "",
                    "route_id": item["route_id"],
                    "source_id": item["source_id"],
                    "endpoint": item["endpoint"],
                }
                for item in usable
            ],
        }

    @staticmethod
    def _effective_route_payload(
        route: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        payload = dict(route)
        source = sources[str(payload["source_id"])]
        payload["requests_per_minute"] = min(
            int(payload["requests_per_minute"]),
            int(source["requests_per_minute"]),
        )
        payload["concurrency"] = min(
            int(payload["concurrency"]), int(source["concurrency"])
        )
        payload["retry_count"] = min(
            int(payload["retry_count"]), int(source["retry_count"])
        )
        return payload

    def get_route_snapshot(self, *, task_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM data_route_snapshots WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "snapshot_id": row["snapshot_id"],
            "task_id": row["task_id"],
            "dataset_id": row["dataset_id"],
            **json.loads(str(row["snapshot_json"] or "{}")),
            "created_at": row["created_at"],
        }

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
                if current.get("partition_key"):
                    values["fallback_policy"] = "primary"
                if min(values["requests_per_minute"], values["concurrency"], values["timeout_seconds"]) < 1:
                    raise ValueError("rate, concurrency and timeout must be positive")
                if values["retry_count"] < 0 or values["fallback_policy"] not in {"primary", "fill_missing", "on_failure"}:
                    raise ValueError("invalid retry count or fallback policy")
                source = sources.get(values["source_id"])
                if source is None:
                    raise ValueError("route source must come from the controlled registry")
                capability = connection.execute(
                    """
                    SELECT enabled, verification_status FROM data_source_capabilities
                    WHERE source_id=? AND endpoint_id=? AND dataset_id=?
                    """,
                    (values["source_id"], current["endpoint"], current["dataset"]),
                ).fetchone()
                if values["enabled"] and (
                    not source["enabled"] or source["verification_status"] != "verified"
                    or capability is None or not capability["enabled"]
                    or capability["verification_status"] != "verified"
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
                SELECT dataset, partition_key FROM data_source_routes
                WHERE enabled=1 AND fallback_policy='primary'
                GROUP BY dataset, partition_key HAVING COUNT(*) > 1
                LIMIT 1
                """
            ).fetchone()
            if duplicate_primary is not None:
                scope = str(duplicate_primary["partition_key"] or "default")
                raise ValueError(
                    "dataset has multiple enabled primary routes: "
                    f"{duplicate_primary['dataset']}:{scope}"
                )
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

    def record_source_probe(self, probe: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "probe_id": str(probe.get("probe_id") or f"dsp-{uuid.uuid4().hex}"),
            "source_id": str(probe["source_id"]),
            "route_id": _optional_text(probe.get("route_id")),
            "dataset_id": str(probe["dataset_id"]),
            "endpoint_id": str(probe["endpoint_id"]),
            "mode": str(probe.get("mode") or "contract_only"),
            "status": str(probe.get("status") or "failed"),
            "error_code": _optional_text(probe.get("error_code")),
            "error_class": _optional_text(probe.get("error_class")),
            "latency_ms": max(0, int(probe.get("latency_ms") or 0)),
            "sample_rows": max(0, int(probe.get("sample_rows") or 0)),
            "retryable": bool(probe.get("retryable")),
            "evidence": dict(probe.get("evidence") or {}),
            "created_at": _utc_now(),
        }
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_source_probes (
                    probe_id, source_id, route_id, dataset_id, endpoint_id, mode,
                    status, error_code, error_class, latency_ms, sample_rows,
                    retryable, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["probe_id"], payload["source_id"], payload["route_id"],
                    payload["dataset_id"], payload["endpoint_id"], payload["mode"],
                    payload["status"], payload["error_code"], payload["error_class"],
                    payload["latency_ms"], payload["sample_rows"],
                    int(payload["retryable"]), _dump(payload["evidence"]),
                    payload["created_at"],
                ),
            )
        return payload

    def list_source_probes(
        self, *, source_id: str = "", route_id: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        filters, values = [], []
        if source_id:
            filters.append("source_id=?")
            values.append(source_id)
        if route_id:
            filters.append("route_id=?")
            values.append(route_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        values.append(max(1, min(int(limit), 500)))
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                f"SELECT * FROM data_source_probes {where} ORDER BY created_at DESC, rowid DESC LIMIT ?",
                values,
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["retryable"] = bool(item["retryable"])
            item["evidence"] = json.loads(str(item.pop("evidence_json") or "{}"))
            result.append(item)
        return result

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
                    field_name, issue_category, workflow_status, block_release,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _optional_text(issue.get("field_name")),
                    _issue_category(str(issue.get("rule_id") or "")),
                    str(issue.get("workflow_status") or status),
                    int(bool(issue.get("block_release", severity == "error"))),
                    now, now,
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
            remediations = [dict(row) for row in connection.execute(
                "SELECT * FROM data_quality_remediations WHERE issue_id=? ORDER BY created_at",
                (issue_id,),
            ).fetchall()]
        for overlay in overlays:
            overlay["before"] = json.loads(str(overlay.pop("before_json") or "{}"))
            overlay["after"] = json.loads(str(overlay.pop("after_json") or "{}"))
        return {
            "issue": issue,
            "dispositions": dispositions,
            "overlays": overlays,
            "refetches": refetches,
            "remediations": remediations,
        }

    def create_remediation(
        self, issue_id: str, *, method: str, executor_type: str,
        executor_id: str = "", reason: str, operator: str,
    ) -> dict[str, Any]:
        issue = self.get_issue(issue_id)
        if issue["status"] not in {"open", "quarantined"}:
            raise ValueError(f"quality issue is already resolved: {issue_id}")
        allowed = {"refetch", "historical_backfill", "correction_overlay", "deduplicate", "recompute"}
        if method not in allowed:
            raise ValueError(f"unsupported remediation method: {method}")
        if not reason.strip():
            raise ValueError("remediation reason is required")
        now = _utc_now()
        remediation_id = f"dqr-{uuid.uuid4().hex}"
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO data_quality_remediations (
                    remediation_id, issue_id, method, executor_type, executor_id,
                    status, data_version_id, verification_scan_id, reason, operator,
                    last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'remediating', NULL, NULL, ?, ?, NULL, ?, ?)
                """,
                (
                    remediation_id, issue_id, method, executor_type,
                    executor_id or None, reason.strip(), operator or "local-user", now, now,
                ),
            )
            connection.execute(
                """
                UPDATE data_quality_issues
                SET status='quarantined', workflow_status='remediating', updated_at=?
                WHERE issue_id=?
                """,
                (now, issue_id),
            )
        return self.get_remediation(remediation_id)

    def get_remediation(self, remediation_id: str) -> dict[str, Any]:
        with closing(self._connect(read_only=True)) as connection:
            row = connection.execute(
                "SELECT * FROM data_quality_remediations WHERE remediation_id=?",
                (remediation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"quality remediation not found: {remediation_id}")
        return dict(row)

    def update_remediation(
        self, remediation_id: str, *, status: str, executor_id: str = "",
        data_version_id: str = "", verification_scan_id: str = "", last_error: str = "",
    ) -> dict[str, Any]:
        allowed = {
            "remediating", "awaiting_publish", "awaiting_recheck",
            "corrected", "failed",
        }
        if status not in allowed:
            raise ValueError(f"unsupported remediation status: {status}")
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT issue_id FROM data_quality_remediations WHERE remediation_id=?",
                (remediation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"quality remediation not found: {remediation_id}")
            connection.execute(
                """
                UPDATE data_quality_remediations SET status=?,
                    executor_id=COALESCE(?, executor_id),
                    data_version_id=COALESCE(?, data_version_id),
                    verification_scan_id=COALESCE(?, verification_scan_id),
                    last_error=COALESCE(?, last_error), updated_at=?
                WHERE remediation_id=?
                """,
                (
                    status, executor_id or None, data_version_id or None,
                    verification_scan_id or None, last_error or None, now,
                    remediation_id,
                ),
            )
            issue_status = "corrected" if status == "corrected" else "quarantined"
            connection.execute(
                "UPDATE data_quality_issues SET status=?, workflow_status=?, data_version_id=COALESCE(?, data_version_id), updated_at=? WHERE issue_id=?",
                (issue_status, status, data_version_id or None, now, str(row["issue_id"])),
            )
        return self.get_remediation(remediation_id)

    def mark_overlay_published(
        self, issue_id: str, *, data_version_id: str,
    ) -> dict[str, Any]:
        if not data_version_id:
            raise ValueError("published overlay requires a data version")
        now = _utc_now()
        with closing(self._connect()) as connection, connection:
            overlay = connection.execute(
                """
                SELECT overlay_id FROM data_correction_overlays
                WHERE issue_id=? AND status='pending_publish'
                ORDER BY created_at DESC LIMIT 1
                """,
                (issue_id,),
            ).fetchone()
            if overlay is None:
                raise ValueError("quality issue has no pending correction overlay")
            connection.execute(
                """
                UPDATE data_correction_overlays
                SET status='published', data_version_id=?
                WHERE overlay_id=?
                """,
                (data_version_id, str(overlay["overlay_id"])),
            )
            connection.execute(
                """
                UPDATE data_quality_remediations
                SET status='awaiting_recheck', data_version_id=?, updated_at=?
                WHERE issue_id=? AND executor_id=?
                  AND status='awaiting_publish'
                """,
                (data_version_id, now, issue_id, str(overlay["overlay_id"])),
            )
            connection.execute(
                """
                UPDATE data_quality_issues
                SET workflow_status='awaiting_recheck', data_version_id=?, updated_at=?
                WHERE issue_id=?
                """,
                (data_version_id, now, issue_id),
            )
        return self.get_issue_history(issue_id)

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
        statuses = {"accept": "accepted", "reject": "rejected", "quarantine": "quarantined", "correct": "quarantined"}
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
                overlay_id = f"dco-{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO data_correction_overlays (
                        overlay_id, issue_id, dataset, symbol, observation_at,
                        before_json, after_json, reason, operator, created_at, status, data_version_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        overlay_id, issue_id, issue["dataset"],
                        issue.get("symbol"), issue.get("observation_at"),
                        _dump(dict(before or {})), _dump(dict(after or {})),
                        reason.strip(), operator or "local-user", now, "pending_publish", None,
                    ),
                )
                remediation_id = f"dqr-{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO data_quality_remediations (
                        remediation_id, issue_id, method, executor_type, executor_id,
                        status, data_version_id, verification_scan_id, reason, operator,
                        last_error, created_at, updated_at
                    ) VALUES (?, ?, 'correction_overlay', 'data_correction_overlay', ?,
                              'awaiting_publish', NULL, NULL, ?, ?, NULL, ?, ?)
                    """,
                    (
                        remediation_id, issue_id, overlay_id, reason.strip(),
                        operator or "local-user", now, now,
                    ),
                )
            connection.execute(
                "UPDATE data_quality_issues SET status=?, workflow_status=?, updated_at=? WHERE issue_id=?",
                (
                    statuses[action],
                    "awaiting_publish" if action == "correct" else statuses[action],
                    now, issue_id,
                ),
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
                    "UPDATE data_quality_issues SET status=?, workflow_status=?, updated_at=? WHERE issue_id=?",
                    (statuses[action], statuses[action], now, issue_id),
                )
        return [self.get_issue(issue_id) for issue_id in ids]

    def preview_trading_status_issue_reconciliation(
        self, *, scan_id: str = "",
    ) -> dict[str, Any]:
        """Preview fail-closed closure of stale trading-status issue records."""

        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            return self._preview_trading_status_issue_reconciliation(
                connection, scan_id=scan_id, include_issue_ids=False,
            )

    def reconcile_trading_status_issues(
        self,
        *,
        scan_id: str,
        expected_issue_set_hash: str,
        operator: str,
        reason: str,
    ) -> dict[str, Any]:
        """Atomically close issue rows whose exact physical recheck has passed."""

        normalized_operator = str(operator or "").strip()
        normalized_reason = str(reason or "").strip()
        if not normalized_operator or len(normalized_operator) > 120:
            raise ValueError("operator is required and must not exceed 120 characters")
        if not normalized_reason or len(normalized_reason) > 500:
            raise ValueError("reason is required and must not exceed 500 characters")
        if len(str(expected_issue_set_hash or "")) != 64:
            raise ValueError("expected_issue_set_hash must be SHA-256")

        self.ensure_schema()
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                preview = self._preview_trading_status_issue_reconciliation(
                    connection, scan_id=scan_id, include_issue_ids=True,
                )
                if str(preview.get("issue_set_hash") or "") != str(
                    expected_issue_set_hash
                ):
                    raise ValueError("trading-status issue set changed after preview")
                if preview.get("status") != "ready":
                    raise ValueError("trading-status issue reconciliation is not ready")
                issue_ids = list(preview.pop("_issue_ids", []))
                if not issue_ids:
                    raise ValueError("no trading-status issues are eligible for reconciliation")
                now = _utc_now()
                for issue_id in issue_ids:
                    disposition_id = f"dqd-{uuid.uuid4().hex}"
                    connection.execute(
                        """
                        INSERT INTO data_quality_dispositions (
                            disposition_id, issue_id, action, reason, operator,
                            related_task_id, related_issue_id, created_at
                        ) VALUES (?, ?, 'correct', ?, ?, ?, NULL, ?)
                        """,
                        (
                            disposition_id, issue_id, normalized_reason,
                            normalized_operator, str(scan_id), now,
                        ),
                    )
                    changed = connection.execute(
                        """
                        UPDATE data_quality_issues
                        SET status='corrected', workflow_status='corrected',
                            block_release=0, updated_at=?
                        WHERE issue_id=? AND rule_id='trading_status_semantics'
                          AND status IN ('open','quarantined')
                        """,
                        (now, issue_id),
                    ).rowcount
                    if changed != 1:
                        raise ValueError(
                            f"trading-status issue changed during reconciliation: {issue_id}"
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {
            **preview,
            "status": "completed",
            "closed_count": len(issue_ids),
            "closed_issue_ids": issue_ids,
            "operator": normalized_operator,
            "reason": normalized_reason,
            "closed_at": now,
        }

    def _preview_trading_status_issue_reconciliation(
        self,
        connection: sqlite3.Connection,
        *,
        scan_id: str,
        include_issue_ids: bool,
    ) -> dict[str, Any]:
        scan_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='data_quality_scan_jobs'
            """
        ).fetchone()
        if scan_table is None:
            return {
                "status": "blocked", "scan_id": None, "issue_count": 0,
                "closable_count": 0, "blocking_count": 1,
                "issue_set_hash": sha256(b"").hexdigest(),
                "blockers": [{
                    "check_id": "quality_scan_missing",
                    "reason": "quality scan storage is unavailable",
                }],
            }
        if scan_id:
            scan = connection.execute(
                "SELECT * FROM data_quality_scan_jobs WHERE scan_id=?",
                (str(scan_id),),
            ).fetchone()
            scans = [scan] if scan is not None else []
        else:
            scans = connection.execute(
                """
                SELECT * FROM data_quality_scan_jobs
                WHERE status='passed' ORDER BY created_at DESC LIMIT 100
                """
            ).fetchall()
        selected: sqlite3.Row | None = None
        for candidate in scans:
            try:
                rules = set(json.loads(str(candidate["rules_json"] or "[]")))
                adjustments = set(json.loads(str(candidate["adjustments_json"] or "[]")))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                str(candidate["status"] or "") == "passed"
                and "trading_status_semantics" in rules
                and {"raw", "qfq", "hfq"} <= adjustments
            ):
                selected = candidate
                break
        if selected is None:
            return {
                "status": "blocked", "scan_id": str(scan_id or "") or None,
                "issue_count": 0, "closable_count": 0, "blocking_count": 1,
                "issue_set_hash": sha256(b"").hexdigest(),
                "blockers": [{
                    "check_id": "passed_trading_status_scan_required",
                    "reason": "a passed raw/qfq/hfq trading-status scan is required",
                }],
            }

        issues = connection.execute(
            """
            SELECT issue.issue_id, issue.symbol, issue.observation_at,
                   issue.status AS issue_status, issue.source_task_id,
                   status.rowid AS status_rowid, status.status AS physical_status,
                   status.is_tradable,
                   (
                       SELECT MAX(COALESCE(price.volume, 0))
                       FROM market_daily_prices price
                       WHERE price.symbol=issue.symbol
                         AND price.trade_date=issue.observation_at
                         AND price.adjustment IN ('raw','qfq','hfq')
                   ) AS max_volume
            FROM data_quality_issues issue
            LEFT JOIN security_trading_status_daily status
              ON status.symbol=issue.symbol
             AND status.trade_date=issue.observation_at
            WHERE issue.rule_id='trading_status_semantics'
              AND issue.status IN ('open','quarantined')
            ORDER BY issue.observation_at, issue.symbol, issue.issue_id
            """
        ).fetchall()
        try:
            scan_symbols = set(json.loads(str(selected["symbols_json"] or "[]")))
        except (TypeError, ValueError, json.JSONDecodeError):
            scan_symbols = set()
        current_symbols = {
            str(row[0]) for row in connection.execute(
                "SELECT symbol FROM market_symbols WHERE listing_status='current'"
            ).fetchall()
        }
        canonical: list[dict[str, Any]] = []
        closable_ids: list[str] = []
        blockers: list[dict[str, Any]] = []
        for row in issues:
            symbol = str(row["symbol"] or "")
            observation_at = str(row["observation_at"] or "")
            covered = bool(
                str(selected["date_from"]) <= observation_at <= str(selected["date_to"])
                and (
                    (str(selected["scope"]) == "symbols" and symbol in scan_symbols)
                    or (
                        str(selected["scope"]) == "all_current"
                        and symbol in current_symbols
                    )
                )
            )
            status_exists = row["status_rowid"] is not None
            is_tradable = row["is_tradable"]
            max_volume = float(row["max_volume"] or 0)
            still_failing = bool(
                not status_exists
                or is_tradable is None
                or (int(is_tradable) == 0 and max_volume > 0)
            )
            reason_code = (
                "scan_scope_does_not_cover_issue" if not covered
                else "trading_status_fact_missing" if not status_exists
                else "unknown_tradability" if is_tradable is None
                else "suspended_with_positive_volume" if still_failing
                else "physical_recheck_passed"
            )
            item = {
                "issue_id": str(row["issue_id"]), "symbol": symbol,
                "observation_at": observation_at, "covered": covered,
                "status_exists": status_exists,
                "physical_status": str(row["physical_status"] or ""),
                "is_tradable": None if is_tradable is None else bool(is_tradable),
                "max_volume": max_volume, "reason": reason_code,
            }
            canonical.append(item)
            if covered and not still_failing:
                closable_ids.append(str(row["issue_id"]))
            else:
                blockers.append(item)
        hash_payload = {
            "schema_version": "trading-status-issue-reconciliation-v1",
            "scan_id": str(selected["scan_id"]),
            "scan_finished_at": str(selected["finished_at"] or ""),
            "issues": canonical,
        }
        issue_set_hash = sha256(
            json.dumps(
                hash_payload, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        status = (
            "no_changes" if not issues
            else "ready" if not blockers and len(closable_ids) == len(issues)
            else "blocked"
        )
        result = {
            "status": status,
            "scan_id": str(selected["scan_id"]),
            "scan_finished_at": str(selected["finished_at"] or ""),
            "scan_scope": str(selected["scope"]),
            "scan_date_from": str(selected["date_from"]),
            "scan_date_to": str(selected["date_to"]),
            "issue_count": len(issues),
            "closable_count": len(closable_ids),
            "blocking_count": len(blockers),
            "issue_set_hash": issue_set_hash,
            "blockers": blockers[:20],
            "sample_closable": canonical[:20] if not blockers else [],
            "confirmation_phrase": "RECONCILE_TRADING_STATUS_ISSUES",
        }
        if include_issue_ids:
            result["_issue_ids"] = closable_ids
        return result

    def release_readiness(
        self, *, data_version_id: str = "", exempt_issue_id: str = "",
        exempt_executor_id: str = "",
    ) -> dict[str, Any]:
        self.ensure_schema()
        issue_exemption = ""
        issue_exemption_values: list[Any] = []
        if exempt_issue_id:
            issue_exemption += " AND issue_id<>?"
            issue_exemption_values.append(exempt_issue_id)
        if exempt_executor_id:
            issue_exemption += """
                AND NOT EXISTS (
                    SELECT 1 FROM data_quality_remediations release_remediation
                    WHERE release_remediation.issue_id=data_quality_issues.issue_id
                      AND release_remediation.executor_id=?
                )
            """
            issue_exemption_values.append(exempt_executor_id)
        overlay_exemption = " AND issue_id<>?" if exempt_issue_id else ""
        remediation_exemption = ""
        remediation_exemption_values: list[Any] = []
        if exempt_issue_id:
            remediation_exemption += " AND issue_id<>?"
            remediation_exemption_values.append(exempt_issue_id)
        if exempt_executor_id:
            remediation_exemption += " AND COALESCE(executor_id, '')<>?"
            remediation_exemption_values.append(exempt_executor_id)
        with closing(self._connect(read_only=True)) as connection:
            blocking = int(connection.execute(
                f"""
                SELECT COUNT(*) FROM data_quality_issues
                WHERE block_release=1
                  AND workflow_status IN ('open','quarantined','remediating','awaiting_publish','awaiting_recheck')
                  AND (?='' OR data_version_id IS NULL OR data_version_id=?)
                  {issue_exemption}
                """,
                (data_version_id, data_version_id, *issue_exemption_values),
            ).fetchone()[0])
            pending_overlays = int(connection.execute(
                f"SELECT COUNT(*) FROM data_correction_overlays WHERE status='pending_publish'{overlay_exemption}",
                ([exempt_issue_id] if exempt_issue_id else []),
            ).fetchone()[0])
            pending_remediations = int(connection.execute(
                f"""
                SELECT COUNT(*) FROM data_quality_remediations
                WHERE status IN ('remediating','awaiting_publish','awaiting_recheck')
                  AND (?='' OR data_version_id IS NULL OR data_version_id=?)
                  {remediation_exemption}
                """,
                (data_version_id, data_version_id, *remediation_exemption_values),
            ).fetchone()[0])
        checks = [
            {
                "check_id": "blocking_quality_issues",
                "status": "passed" if blocking == 0 else "blocked",
                "count": blocking,
            },
            {
                "check_id": "pending_correction_overlays",
                "status": "passed" if pending_overlays == 0 else "blocked",
                "count": pending_overlays,
            },
            {
                "check_id": "pending_remediations",
                "status": "passed" if pending_remediations == 0 else "blocked",
                "count": pending_remediations,
            },
        ]
        return {
            "status": "ready" if all(item["status"] == "passed" for item in checks) else "blocked",
            "data_version_id": data_version_id or None,
            "exempt_issue_id": exempt_issue_id or None,
            "exempt_executor_id": exempt_executor_id or None,
            "checks": checks,
        }

    def replace_index_component_snapshot(
        self,
        *,
        index_code: str,
        as_of_date: str,
        rows: Sequence[Mapping[str, Any]],
        source: str,
        source_version: str,
        observed_at: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Replace one same-source snapshot without inventing earlier history."""

        code = str(index_code or "").strip().upper()
        snapshot_date = str(as_of_date or "")[:10]
        _validate_iso_date(snapshot_date, "as_of_date")
        normalized = sorted({_symbol(item.get("symbol")) for item in rows if _symbol(item.get("symbol"))})
        if not code or not normalized:
            raise ValueError("index_code and at least one symbol are required")
        payload = dict(evidence or {})
        payload.update({"snapshot_semantics": "observed_snapshot_not_historical_reconstruction", "member_count": len(normalized)})
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "DELETE FROM index_component_intervals WHERE index_code=? AND valid_from=? AND source=?",
                (code, snapshot_date, source),
            )
            connection.execute(
                """UPDATE index_component_intervals
                   SET valid_to=date(?, '-1 day')
                   WHERE index_code=? AND source=? AND valid_from<? AND valid_to IS NULL""",
                (snapshot_date, code, source, snapshot_date),
            )
            connection.executemany(
                """INSERT INTO index_component_intervals (
                       index_code, symbol, valid_from, valid_to, source,
                       source_version, observed_at, evidence_json
                   ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?)""",
                [(code, symbol, snapshot_date, source, source_version, observed_at, _dump(payload)) for symbol in normalized],
            )
        return self.resolve_index_components(code, snapshot_date)

    def resolve_index_components(self, index_code: str, as_of_date: str) -> dict[str, Any]:
        code = str(index_code or "").strip().upper()
        target = str(as_of_date or "")[:10]
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """SELECT * FROM index_component_intervals
                   WHERE index_code=? AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY symbol, valid_from DESC""",
                (code, target, target),
            ).fetchall()
        latest = {}
        for row in rows:
            latest.setdefault(str(row["symbol"]), row)
        if not latest:
            return {"status": "unavailable", "reason": "index_component_facts_unavailable", "index_code": code, "as_of_date": target, "symbols": [], "intervals": []}
        selected = list(latest.values())
        return {
            "status": "ready", "index_code": code, "as_of_date": target,
            "symbols": sorted(latest), "intervals": [dict(row) for row in selected],
            "source": sorted({str(row["source"]) for row in selected}),
            "source_version": sorted({str(row["source_version"]) for row in selected if row["source_version"]}),
            "observed_at": max(str(row["observed_at"]) for row in selected),
        }

    def resolve_index_component_window(self, index_code: str, start_date: str, end_date: str) -> dict[str, Any]:
        code = str(index_code or "").strip().upper()
        start = str(start_date or "")[:10]
        end = str(end_date or "")[:10]
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """SELECT * FROM index_component_intervals
                   WHERE index_code=? AND valid_from<=?
                     AND (valid_to IS NULL OR valid_to>=?)
                   ORDER BY symbol, valid_from, source""",
                (code, end, start),
            ).fetchall()
        if not rows:
            return {"status": "unavailable", "reason": "index_component_facts_unavailable", "index_code": code, "start_date": start, "end_date": end, "symbols": [], "intervals": []}
        return {
            "status": "ready", "index_code": code, "start_date": start, "end_date": end,
            "symbols": sorted({str(row["symbol"]) for row in rows}),
            "intervals": [dict(row) for row in rows],
            "source": sorted({str(row["source"]) for row in rows}),
            "source_version": sorted({str(row["source_version"]) for row in rows if row["source_version"]}),
            "observed_at": max(str(row["observed_at"]) for row in rows),
        }

    def index_component_coverage(self) -> dict[str, Any]:
        self.ensure_schema()
        with closing(self._connect(read_only=True)) as connection:
            rows = connection.execute(
                """SELECT index_code, COUNT(DISTINCT symbol) AS symbol_count,
                          MIN(valid_from) AS min_date,
                          MAX(COALESCE(valid_to, valid_from)) AS max_date,
                          MAX(observed_at) AS observed_at
                   FROM index_component_intervals GROUP BY index_code ORDER BY index_code"""
            ).fetchall()
        return {"status": "ready" if rows else "unavailable", "reason": None if rows else "index_component_facts_unavailable", "items": [dict(row) for row in rows]}
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
        if self._has_table("data_quality_reports"):
            with closing(self._connect(read_only=True)) as connection:
                report = connection.execute(
                    "SELECT status FROM data_quality_reports WHERE quality_report_id=?",
                    (selected.get("quality_report_id"),),
                ).fetchone()
            if report is None or str(report["status"] or "") != "passed":
                raise ValueError("default version requires a passed quality report")
        assets = self.list_assets(version_id=version_id)["items"]
        if assets and any(str(item.get("quality_status") or "") != "passed" for item in assets):
            raise ValueError("default version contains members that failed quality gates")
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
        payload["credential_states"] = [
            {
                "env_name": env_name,
                "status": "configured" if bool(os.environ.get(str(env_name))) else "missing",
            }
            for env_name in payload["secret_env_names"]
        ]
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
        from data_platform.maintenance_transaction import transaction_connection
        active = transaction_connection(self.database_path)
        if active is not None:
            return active
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


def _issue_category(rule_id: str) -> str:
    value = str(rule_id or "").lower()
    if "missing" in value or "gap" in value:
        return "missing"
    if "duplicate" in value:
        return "duplicate"
    if "delay" in value or "fresh" in value:
        return "delay"
    if "valid" in value or "value" in value or "ohlcv" in value:
        return "incorrect"
    return "consistency"


def _required_hosts(upstream: str) -> list[str]:
    aliases = {
        "eastmoney": ["eastmoney.com"],
        "sina": ["sina.com.cn"],
        "csindex": ["csindex.com.cn"],
        "10jqka": ["10jqka.com.cn"],
        "cninfo": ["cninfo.com.cn"],
    }
    return aliases.get(str(upstream or "").lower(), [])


def _split_csv(value: str) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in str(value or "").split(",") if item.strip()))


def _symbol(value: Any) -> str:
    raw = str(value or "").strip().upper()
    code = raw.split(".", 1)[0]
    return code.zfill(6) if code.isdigit() else raw


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
