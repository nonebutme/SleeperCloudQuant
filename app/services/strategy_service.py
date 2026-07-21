"""Versioned local strategy library and validation service."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STRATEGY_ENTRYPOINT = "generate_target_weights"
STRATEGY_CONTRACT = "target-weights-v1"

_FORBIDDEN_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "input",
    "locals",
    "open",
}


class StrategyService:
    """Persist immutable strategy versions and resolve executable snapshots."""

    def __init__(
        self,
        database_path: str | Path = "var/runtime/strategy_library.sqlite3",
        *,
        legacy_drafts_path: str | Path = "var/runtime/strategy_drafts.json",
    ) -> None:
        self._database_path = Path(database_path)
        self._legacy_drafts_path = Path(legacy_drafts_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._seed_builtin_strategies()
        self._import_legacy_drafts_once()

    def list_strategies(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.strategy_id, d.name, d.category, d.description,
                       d.source_reference, d.editable, d.active_version,
                       v.version_number, v.parameters_json, v.parameter_schema_json,
                       v.source_code, v.source_sha256, v.validation_status,
                       v.created_at
                FROM strategy_definitions AS d
                JOIN strategy_versions AS v
                  ON v.strategy_id = d.strategy_id
                 AND v.version_number = d.active_version
                ORDER BY d.updated_at DESC, d.strategy_id
                """
            ).fetchall()
        return [self._row_to_strategy(row) for row in rows]

    def list_versions(self, strategy_id: str) -> list[dict[str, Any]]:
        normalized_id = _normalize_strategy_id(strategy_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT d.strategy_id, d.name, d.category, d.description,
                       d.source_reference, d.editable, d.active_version,
                       v.version_number, v.parameters_json, v.parameter_schema_json,
                       v.source_code, v.source_sha256, v.validation_status,
                       v.created_at
                FROM strategy_definitions AS d
                JOIN strategy_versions AS v ON v.strategy_id = d.strategy_id
                WHERE d.strategy_id = ?
                ORDER BY v.version_number
                """,
                (normalized_id,),
            ).fetchall()
        return [self._row_to_strategy(row) for row in rows]

    def resolve_version(self, strategy_id: str, version: str | None = None) -> dict[str, Any]:
        versions = self.list_versions(strategy_id)
        if not versions:
            raise KeyError(f"strategy not found: {strategy_id}")
        if not version:
            return versions[-1]
        normalized_version = str(version).lower().removeprefix("v")
        for item in versions:
            if str(item["version_number"]) == normalized_version:
                return item
        raise KeyError(f"strategy version not found: {strategy_id} {version}")

    def validate_source(self, source_code: str) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            issues.append({"code": "syntax_error", "message": str(exc), "line": str(exc.lineno or "")})
            return {"ok": False, "status": "invalid", "contract": STRATEGY_CONTRACT, "issues": issues}

        entrypoint_found = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                issues.append({"code": "import_forbidden", "message": "策略代码不能导入模块。", "line": str(node.lineno)})
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                issues.append({"code": "scope_forbidden", "message": "策略代码不能修改全局或外层作用域。", "line": str(node.lineno)})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == STRATEGY_ENTRYPOINT:
                entrypoint_found = True
                if len(node.args.args) != 2:
                    issues.append({"code": "invalid_signature", "message": f"{STRATEGY_ENTRYPOINT} 必须接收 bars, parameters 两个参数。", "line": str(node.lineno)})
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                issues.append({"code": "call_forbidden", "message": f"禁止调用 {node.func.id}。", "line": str(node.lineno)})
            elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                issues.append({"code": "dunder_forbidden", "message": "禁止访问双下划线属性。", "line": str(node.lineno)})
        if not entrypoint_found:
            issues.append({"code": "entrypoint_missing", "message": f"必须定义 {STRATEGY_ENTRYPOINT}(bars, parameters)。", "line": ""})
        return {
            "ok": not issues,
            "status": "valid" if not issues else "invalid",
            "contract": STRATEGY_CONTRACT,
            "issues": issues,
            "source_sha256": _sha256(source_code),
        }

    def save_version(
        self,
        *,
        strategy_id: str,
        name: str,
        source_code: str,
        parameters: dict[str, Any] | None = None,
        parameter_schema: dict[str, Any] | None = None,
        category: str = "自定义策略",
        description: str = "本地自定义 Python 策略。",
    ) -> dict[str, Any]:
        normalized_id = _normalize_strategy_id(strategy_id)
        validation = self.validate_source(source_code)
        if not validation["ok"]:
            raise ValueError(json.dumps(validation, ensure_ascii=False))
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) FROM strategy_versions WHERE strategy_id = ?",
                (normalized_id,),
            ).fetchone()
            version_number = int(row[0]) + 1
            connection.execute(
                """
                INSERT INTO strategy_definitions (
                    strategy_id, name, category, description, source_reference,
                    editable, active_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'local-versioned-strategy', 1, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    active_version = excluded.active_version,
                    updated_at = excluded.updated_at
                """,
                (normalized_id, name.strip() or normalized_id, category, description, version_number, now, now),
            )
            connection.execute(
                """
                INSERT INTO strategy_versions (
                    strategy_id, version_number, source_code, source_sha256,
                    parameters_json, parameter_schema_json, validation_status,
                    contract_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'valid', ?, ?)
                """,
                (
                    normalized_id,
                    version_number,
                    source_code,
                    validation["source_sha256"],
                    json.dumps(parameters or {}, ensure_ascii=False),
                    json.dumps(parameter_schema or _infer_parameter_schema(parameters or {}), ensure_ascii=False),
                    STRATEGY_CONTRACT,
                    now,
                ),
            )
        return self.resolve_version(normalized_id, f"v{version_number}")

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS strategy_definitions (
                    strategy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    editable INTEGER NOT NULL,
                    active_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_versions (
                    strategy_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    source_code TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    parameter_schema_json TEXT NOT NULL,
                    validation_status TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (strategy_id, version_number),
                    FOREIGN KEY (strategy_id) REFERENCES strategy_definitions(strategy_id)
                );
                CREATE TABLE IF NOT EXISTS strategy_migrations (
                    migration_id TEXT PRIMARY KEY,
                    completed_at TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )

    def _seed_builtin_strategies(self) -> None:
        with self._connect() as connection:
            existing = connection.execute("SELECT COUNT(*) FROM strategy_definitions").fetchone()[0]
        if existing:
            return
        for item in _builtin_strategies():
            self.save_version(**item)

    def _import_legacy_drafts_once(self) -> None:
        migration_id = "legacy-strategy-drafts-json-v1"
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM strategy_migrations WHERE migration_id = ?", (migration_id,)).fetchone():
                return
        imported = 0
        if self._legacy_drafts_path.is_file():
            try:
                raw = json.loads(self._legacy_drafts_path.read_text(encoding="utf-8"))
                records = raw.get("versions", []) if isinstance(raw, dict) else []
            except (OSError, json.JSONDecodeError):
                records = []
            for item in records:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source_code") or "")
                if not self.validate_source(source)["ok"]:
                    continue
                self.save_version(
                    strategy_id=str(item.get("strategy_id") or "legacy_strategy"),
                    name=str(item.get("name") or "旧版策略"),
                    source_code=source,
                    parameters=dict(item.get("parameters") or {}),
                    parameter_schema=dict(item.get("parameter_schema") or {}),
                    category=str(item.get("category") or "迁移策略"),
                    description=str(item.get("description") or "从旧 JSON 草稿迁移。"),
                )
                imported += 1
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO strategy_migrations (migration_id, completed_at, details_json) VALUES (?, ?, ?)",
                (migration_id, now, json.dumps({"imported_versions": imported}, ensure_ascii=False)),
            )

    def _row_to_strategy(self, row: sqlite3.Row) -> dict[str, Any]:
        with self._connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM strategy_versions WHERE strategy_id = ?", (row["strategy_id"],)).fetchone()[0]
        return {
            "strategy_id": row["strategy_id"],
            "name": row["name"],
            "category": row["category"],
            "description": row["description"],
            "parameters": json.loads(row["parameters_json"]),
            "parameter_schema": json.loads(row["parameter_schema_json"]),
            "source_code": row["source_code"],
            "source_reference": row["source_reference"],
            "editable": bool(row["editable"]),
            "latest_version": f"v{row['version_number']}",
            "version_number": row["version_number"],
            "version_count": count,
            "saved_at": row["created_at"],
            "source_sha256": row["source_sha256"],
            "validation_status": row["validation_status"],
            "execution_contract": STRATEGY_CONTRACT,
        }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _normalize_strategy_id(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip()).strip("_").lower()
    if not normalized:
        raise ValueError("strategy_id is required")
    return normalized


def _sha256(source_code: str) -> str:
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()


def _infer_parameter_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, int):
            kind = "integer"
        elif isinstance(value, float):
            kind = "number"
        else:
            kind = "string"
        schema[key] = {"type": kind}
    return schema


def _builtin_strategies() -> list[dict[str, Any]]:
    moving_average = '''def generate_target_weights(bars, parameters):
    short_window = int(parameters.get("short_window", 5))
    long_window = int(parameters.get("long_window", 20))
    position_size = float(parameters.get("position_size", 1.0))
    closes = [float(bar["close"]) for bar in bars]
    weights = []
    for index in range(len(closes)):
        if index + 1 < long_window:
            weights.append(0.0)
            continue
        short_ma = sum(closes[index - short_window + 1:index + 1]) / short_window
        long_ma = sum(closes[index - long_window + 1:index + 1]) / long_window
        weights.append(position_size if short_ma >= long_ma else 0.0)
    return weights
'''
    breakout = '''def generate_target_weights(bars, parameters):
    window = int(parameters.get("breakout_window", 20))
    max_position = float(parameters.get("max_position", 0.5))
    closes = [float(bar["close"]) for bar in bars]
    highs = [float(bar["high"]) for bar in bars]
    weights = []
    for index in range(len(closes)):
        previous_highs = highs[max(0, index - window):index]
        weights.append(max_position if previous_highs and closes[index] > max(previous_highs) else 0.0)
    return weights
'''
    buy_hold = '''def generate_target_weights(bars, parameters):
    position_size = float(parameters.get("position_size", 1.0))
    return [position_size for bar in bars]
'''
    return [
        {"strategy_id": "moving_average_strategy", "name": "双均线趋势策略", "source_code": moving_average, "parameters": {"short_window": 5, "long_window": 20, "position_size": 1.0}, "category": "趋势跟随", "description": "短长均线交叉的本地可执行策略。"},
        {"strategy_id": "risk_controlled_breakout", "name": "突破策略", "source_code": breakout, "parameters": {"breakout_window": 20, "max_position": 0.5}, "category": "趋势突破", "description": "突破前期高点时建立目标仓位。"},
        {"strategy_id": "buy_and_hold", "name": "买入持有基线", "source_code": buy_hold, "parameters": {"position_size": 1.0}, "category": "基线", "description": "用于验证策略执行差异的买入持有基线。"},
    ]
