"""Immutable Strategy Manifest persistence for the new strategy studio."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from domain.strategy import StrategyManifest


class StrategyManifestService:
    def __init__(self, database_path: str | Path, *, dataset_product_service: Any) -> None:
        self._database_path = Path(database_path)
        self._dataset_product_service = dataset_product_service
        self._ensure_schema()

    def save(self, manifest: StrategyManifest) -> dict[str, Any]:
        validation = self.validate(manifest)
        if not validation["ok"]:
            raise ValueError(json.dumps(validation, ensure_ascii=False))
        payload = asdict(manifest)
        payload["validation"] = {**dict(payload.get("validation") or {}), **validation}
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT manifest_sha256, manifest_json, created_at
                FROM strategy_manifests
                WHERE strategy_id = ? AND strategy_version = ?
                """,
                (manifest.strategy_id, manifest.strategy_version),
            ).fetchone()
            if existing is not None:
                if str(existing["manifest_sha256"]) != digest:
                    raise ValueError("strategy manifest version is immutable")
                return self._row_payload(
                    manifest_json=str(existing["manifest_json"]),
                    manifest_sha256=str(existing["manifest_sha256"]),
                    created_at=str(existing["created_at"]),
                )
            connection.execute(
                """
                INSERT INTO strategy_manifests (
                    strategy_id, strategy_version, manifest_version,
                    source_sha256, manifest_sha256, manifest_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.strategy_id,
                    manifest.strategy_version,
                    manifest.manifest_version,
                    manifest.source_sha256,
                    digest,
                    encoded,
                    created_at,
                ),
            )
            connection.commit()
        return self._row_payload(encoded, digest, created_at)

    def validate(self, manifest: StrategyManifest) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        for requirement in manifest.dataset_requirements:
            try:
                product = self._dataset_product_service.get_product(requirement.dataset_id)
            except KeyError:
                issues.append({"code": "unknown_dataset", "dataset_id": requirement.dataset_id})
                continue
            if product.get("status") != "connected":
                issues.append(
                    {
                        "code": "dataset_unavailable",
                        "dataset_id": requirement.dataset_id,
                        "status": product.get("status"),
                    }
                )
            available_fields = {str(item.get("name")) for item in product.get("fields") or []}
            missing_fields = sorted(set(requirement.required_fields) - available_fields)
            if missing_fields and product.get("schema_status") == "available":
                issues.append(
                    {
                        "code": "dataset_fields_missing",
                        "dataset_id": requirement.dataset_id,
                        "fields": missing_fields,
                    }
                )
            elif missing_fields:
                warnings.append(
                    {
                        "code": "dataset_schema_metadata_pending",
                        "dataset_id": requirement.dataset_id,
                        "fields_not_yet_verified": missing_fields,
                    }
                )
        return {
            "ok": not issues,
            "status": "valid" if not issues and not warnings else "valid_with_warnings" if not issues else "invalid",
            "issues": issues,
            "warnings": warnings,
        }

    def get(self, strategy_id: str, strategy_version: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT manifest_json, manifest_sha256, created_at
                FROM strategy_manifests
                WHERE strategy_id = ? AND strategy_version = ?
                """,
                (strategy_id, strategy_version),
            ).fetchone()
        if row is None:
            raise KeyError(f"strategy manifest not found: {strategy_id}@{strategy_version}")
        return self._row_payload(str(row["manifest_json"]), str(row["manifest_sha256"]), str(row["created_at"]))

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT manifest_json, manifest_sha256, created_at
                FROM strategy_manifests
                ORDER BY created_at DESC, strategy_id, strategy_version
                """
            ).fetchall()
        return [
            self._row_payload(str(row["manifest_json"]), str(row["manifest_sha256"]), str(row["created_at"]))
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_manifests (
                    strategy_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    manifest_version TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    manifest_sha256 TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, strategy_version)
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row_payload(manifest_json: str, manifest_sha256: str, created_at: str) -> dict[str, Any]:
        payload = json.loads(manifest_json)
        payload["manifest_sha256"] = manifest_sha256
        payload["created_at"] = created_at
        return payload

