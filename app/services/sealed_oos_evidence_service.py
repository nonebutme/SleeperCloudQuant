"""Append-only SQLite persistence for sealed OOS manifests and view records."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.services.sealed_oos_evidence_gate import (
    build_oos_view_record,
    build_sealed_oos_manifest,
    verify_frozen_inputs,
)


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class SealedOosEvidenceService:
    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def seal(self, **values: Any) -> dict[str, Any]:
        manifest = build_sealed_oos_manifest(**values)
        encoded = _dump(manifest)
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT manifest_json FROM sealed_oos_manifests WHERE freeze_id=?",
                (manifest["freeze_id"],),
            ).fetchone()
            if existing is not None:
                saved = _load(existing["manifest_json"])
                if saved.get("freeze_sha256") != manifest.get("freeze_sha256"):
                    raise ValueError("sealed OOS manifest identity conflict")
                return saved
            connection.execute(
                "INSERT INTO sealed_oos_manifests (freeze_id, freeze_sha256, manifest_json) VALUES (?, ?, ?)",
                (manifest["freeze_id"], manifest["freeze_sha256"], encoded),
            )
        return manifest

    def get(self, freeze_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM sealed_oos_manifests WHERE freeze_id=?",
                (str(freeze_id),),
            ).fetchone()
        if row is None:
            raise KeyError(f"sealed OOS manifest not found: {freeze_id}")
        manifest = _load(row["manifest_json"])
        manifest["view_record"] = self.get_view_record(freeze_id)
        return manifest

    def verify_inputs(
        self,
        freeze_id: str,
        *,
        source_sha256: str,
        parameters: Mapping[str, Any],
        dataset_bindings: Sequence[Mapping[str, Any]],
        factor_bindings: Sequence[Mapping[str, Any]],
        universe_snapshot_id: str,
    ) -> dict[str, Any]:
        manifest = self.get(freeze_id)
        return verify_frozen_inputs(
            manifest,
            source_sha256=source_sha256,
            parameters=parameters,
            dataset_bindings=dataset_bindings,
            factor_bindings=factor_bindings,
            universe_snapshot_id=universe_snapshot_id,
        )

    def mark_viewed(
        self,
        freeze_id: str,
        *,
        result_sha256: str,
        viewed_at: str,
    ) -> dict[str, Any]:
        manifest = self.get(freeze_id)
        existing = manifest.get("view_record")
        if existing:
            if existing.get("result_sha256") != str(result_sha256):
                raise ValueError("sealed OOS view record is immutable")
            return dict(existing)
        record = build_oos_view_record(
            manifest,
            result_sha256=result_sha256,
            viewed_at=viewed_at,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sealed_oos_views (freeze_id, view_record_sha256, view_json) VALUES (?, ?, ?)",
                (freeze_id, record["view_record_sha256"], _dump(record)),
            )
        return record

    def get_view_record(self, freeze_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT view_json FROM sealed_oos_views WHERE freeze_id=?",
                (str(freeze_id),),
            ).fetchone()
        return _load(row["view_json"]) if row is not None else None

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sealed_oos_manifests (
                    freeze_id TEXT PRIMARY KEY,
                    freeze_sha256 TEXT NOT NULL UNIQUE,
                    manifest_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sealed_oos_views (
                    freeze_id TEXT PRIMARY KEY,
                    view_record_sha256 TEXT NOT NULL UNIQUE,
                    view_json TEXT NOT NULL,
                    FOREIGN KEY (freeze_id) REFERENCES sealed_oos_manifests(freeze_id)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection


def _dump(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str) -> dict[str, Any]:
    return json.loads(value)
