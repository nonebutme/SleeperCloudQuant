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

from app.services.strategy_dataset_validation import validate_strategy_data_contract


STRATEGY_ENTRYPOINT = "generate_target_weights"
STRATEGY_CONTRACT = "target-weights-v1"
PARAMETER_SCHEMA_NAME = "PARAMETER_SCHEMA"
_PARAMETER_TYPES = {"integer", "number", "boolean", "string", "enum", "date", "symbol", "list", "symbol_list"}

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


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


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
                WHERE d.archived = 0
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
        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as exc:
            issues.append({"code": "syntax_error", "message": str(exc), "line": str(exc.lineno or "")})
            return {"ok": False, "status": "invalid", "contract": STRATEGY_CONTRACT, "issues": issues, "warnings": warnings}

        entrypoint_found = False
        parameter_name = "parameters"
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                issues.append({"code": "import_forbidden", "message": "策略代码不能导入模块。", "line": str(node.lineno)})
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                issues.append({"code": "scope_forbidden", "message": "策略代码不能修改全局或外层作用域。", "line": str(node.lineno)})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == STRATEGY_ENTRYPOINT:
                entrypoint_found = True
                if len(node.args.args) != 2:
                    issues.append({"code": "invalid_signature", "message": f"{STRATEGY_ENTRYPOINT} 必须接收 bars, parameters 两个参数。", "line": str(node.lineno)})
                else:
                    parameter_name = node.args.args[1].arg
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
                issues.append({"code": "call_forbidden", "message": f"禁止调用 {node.func.id}。", "line": str(node.lineno)})
            elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
                issues.append({"code": "dunder_forbidden", "message": "禁止访问双下划线属性。", "line": str(node.lineno)})
        if not entrypoint_found:
            issues.append({"code": "entrypoint_missing", "message": f"必须定义 {STRATEGY_ENTRYPOINT}(bars, parameters)。", "line": ""})
        declared_schema, schema_issues = _read_parameter_schema(tree)
        issues.extend(schema_issues)
        used_parameters = _collect_parameter_keys(tree, parameter_name)
        if declared_schema is not None:
            declared_keys = set(declared_schema)
            for key in sorted(used_parameters - declared_keys):
                warnings.append({"code": "parameter_undeclared", "message": f"代码使用了未在 {PARAMETER_SCHEMA_NAME} 中声明的参数：{key}。", "line": "", "parameter": key})
            for key in sorted(key for key in declared_keys - used_parameters if declared_schema[key].get("scope") != "execution"):
                warnings.append({"code": "parameter_unused", "message": f"参数已声明但策略代码未使用：{key}。", "line": "", "parameter": key})
        parameter_schema = declared_schema or {}
        data_contract = validate_strategy_data_contract(source_code)
        if data_contract.get("strict_contract") is not None and not data_contract["ok"]:
            issues.extend(
                {
                    "code": f"data_contract_{item.get('code') or 'invalid'}",
                    "message": json.dumps(item, ensure_ascii=False, separators=(",", ":")),
                    "line": "",
                }
                for item in data_contract.get("issues") or []
            )
        return {
            "ok": not issues,
            "status": "valid" if not issues else "invalid",
            "contract": STRATEGY_CONTRACT,
            "issues": issues,
            "warnings": warnings,
            "parameter_schema": parameter_schema,
            "parameter_defaults": _parameter_defaults(parameter_schema),
            "parameter_keys": sorted(used_parameters),
            "source_sha256": _sha256(source_code),
            "data_contract": data_contract,
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
        source_schema = dict(validation.get("parameter_schema") or {})
        effective_schema = source_schema or dict(parameter_schema or {}) or _infer_parameter_schema(parameters or {})
        supplied_parameters = dict(parameters or {})
        if source_schema:
            effective_parameters = _parameter_defaults(source_schema)
            effective_parameters.update({key: value for key, value in supplied_parameters.items() if key in source_schema})
        else:
            effective_parameters = supplied_parameters
        parameter_issues = _validate_parameter_values(effective_parameters, effective_schema)
        if parameter_issues:
            raise ValueError(json.dumps({"status": "invalid_parameters", "issues": parameter_issues}, ensure_ascii=False))
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
                    editable, archived, active_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'local-versioned-strategy', 1, 0, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    archived = 0,
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
                    json.dumps(effective_parameters, ensure_ascii=False),
                    json.dumps(effective_schema, ensure_ascii=False),
                    STRATEGY_CONTRACT,
                    now,
                ),
            )
        return self.resolve_version(normalized_id, f"v{version_number}")

    def archive_strategy(self, strategy_id: str) -> dict[str, Any]:
        normalized_id = _normalize_strategy_id(strategy_id)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE strategy_definitions SET archived = 1, updated_at = ? WHERE strategy_id = ? AND archived = 0",
                (now, normalized_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"strategy not found: {normalized_id}")
        return {"strategy_id": normalized_id, "status": "archived", "archived_at": now}

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
                    archived INTEGER NOT NULL DEFAULT 0,
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
            columns = {row[1] for row in connection.execute("PRAGMA table_info(strategy_definitions)").fetchall()}
            if "archived" not in columns:
                connection.execute("ALTER TABLE strategy_definitions ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")

    def _seed_builtin_strategies(self) -> None:
        for item in _builtin_strategies():
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT 1 FROM strategy_definitions WHERE strategy_id = ?",
                    (item["strategy_id"],),
                ).fetchone()
            if not existing:
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
        connection = sqlite3.connect(self._database_path, factory=_ClosingConnection)
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
        schema[key] = {"type": kind, "default": value, "label": key}
    return schema


def _read_parameter_schema(tree: ast.AST) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    issues: list[dict[str, str]] = []
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == PARAMETER_SCHEMA_NAME for target in targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            return None, [{"code": "parameter_schema_not_literal", "message": f"{PARAMETER_SCHEMA_NAME} 必须是可静态读取的字典。", "line": str(getattr(node, "lineno", ""))}]
        if not isinstance(value, dict):
            return None, [{"code": "parameter_schema_invalid", "message": f"{PARAMETER_SCHEMA_NAME} 必须是字典。", "line": str(getattr(node, "lineno", ""))}]
        normalized: dict[str, Any] = {}
        for raw_key, raw_spec in value.items():
            key = str(raw_key).strip()
            if not key or not isinstance(raw_spec, dict):
                issues.append({"code": "parameter_spec_invalid", "message": f"参数 {raw_key!r} 的定义必须是字典。", "line": str(getattr(node, "lineno", ""))})
                continue
            spec = dict(raw_spec)
            kind = str(spec.get("type") or "string")
            if kind not in _PARAMETER_TYPES:
                issues.append({"code": "parameter_type_invalid", "message": f"参数 {key} 使用了不支持的类型：{kind}。", "line": str(getattr(node, "lineno", ""))})
                continue
            if kind == "enum" and not isinstance(spec.get("options"), (list, tuple)):
                issues.append({"code": "parameter_options_missing", "message": f"枚举参数 {key} 必须声明 options。", "line": str(getattr(node, "lineno", ""))})
                continue
            spec["type"] = kind
            spec.setdefault("label", key)
            normalized[key] = spec
        return normalized, issues
    return None, issues


def _collect_parameter_keys(tree: ast.AST, parameter_name: str) -> set[str]:
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and isinstance(node.func.value, ast.Name) and node.func.value.id == parameter_name and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            keys.add(node.args[0].value)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == parameter_name and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            keys.add(node.slice.value)
    return keys


def _parameter_defaults(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: spec["default"] for key, spec in schema.items() if isinstance(spec, dict) and "default" in spec}


def _validate_parameter_values(parameters: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for key, spec in schema.items():
        if key not in parameters:
            if spec.get("required"):
                issues.append({"code": "parameter_required", "parameter": key, "message": f"参数 {key} 不能为空。"})
            continue
        value = parameters[key]
        kind = str(spec.get("type") or "string")
        valid_type = True
        if kind == "integer":
            valid_type = isinstance(value, int) and not isinstance(value, bool)
        elif kind == "number":
            valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif kind == "boolean":
            valid_type = isinstance(value, bool)
        elif kind in {"list", "symbol_list"}:
            valid_type = isinstance(value, list)
        elif kind in {"string", "date", "symbol", "enum"}:
            valid_type = isinstance(value, str)
        if not valid_type:
            issues.append({"code": "parameter_type_mismatch", "parameter": key, "message": f"参数 {key} 的值不符合 {kind} 类型。"})
            continue
        options = spec.get("options") or []
        option_values = [item.get("value") if isinstance(item, dict) else item for item in options]
        if kind == "enum" and value not in option_values:
            issues.append({"code": "parameter_option_invalid", "parameter": key, "message": f"参数 {key} 必须是允许的选项之一。"})
        if kind in {"integer", "number"}:
            if spec.get("min") is not None and value < spec["min"]:
                issues.append({"code": "parameter_below_minimum", "parameter": key, "message": f"参数 {key} 不能小于 {spec['min']}。"})
            if spec.get("max") is not None and value > spec["max"]:
                issues.append({"code": "parameter_above_maximum", "parameter": key, "message": f"参数 {key} 不能大于 {spec['max']}。"})
    return issues


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
    dual_ma_atr = '''def generate_target_weights(bars, parameters):
    short_window = int(parameters.get("short_window", 5))
    long_window = int(parameters.get("long_window", 20))
    atr_window = int(parameters.get("atr_window", 14))
    atr_multiplier = float(parameters.get("atr_multiplier", 2.0))
    position_size = float(parameters.get("position_size", 1.0))
    short_window = max(1, short_window)
    long_window = max(short_window + 1, long_window)
    atr_window = max(1, atr_window)
    position_size = min(max(position_size, 0.0), 1.0)
    closes = [float(bar.get("close") or 0.0) for bar in bars]
    highs = [float(bar.get("high") or 0.0) for bar in bars]
    lows = [float(bar.get("low") or 0.0) for bar in bars]
    weights = [0.0 for bar in bars]
    true_ranges = []
    position = False
    entry_price = 0.0
    for index in range(len(bars)):
        previous_close = closes[index - 1] if index > 0 else closes[index]
        true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - previous_close), abs(lows[index] - previous_close)))
    def rolling_mean(values, end_index, window):
        start_index = end_index - window + 1
        if start_index < 0:
            return None
        return sum(values[start_index:end_index + 1]) / window
    for index in range(len(bars)):
        if index + 1 < long_window:
            continue
        short_ma = rolling_mean(closes, index, short_window)
        long_ma = rolling_mean(closes, index, long_window)
        previous_short_ma = rolling_mean(closes, index - 1, short_window)
        previous_long_ma = rolling_mean(closes, index - 1, long_window)
        atr = rolling_mean(true_ranges, index, atr_window) or 0.0
        signal = 0
        if short_ma is not None and long_ma is not None and previous_short_ma is not None and previous_long_ma is not None:
            if short_ma > long_ma and previous_short_ma <= previous_long_ma:
                signal = 1
            elif short_ma < long_ma and previous_short_ma >= previous_long_ma:
                signal = -1
        close = closes[index]
        if position and atr > 0.0 and close <= entry_price - atr_multiplier * atr:
            position = False
            entry_price = 0.0
        elif signal == 1 and not position:
            position = True
            entry_price = close
        elif signal == -1 and position:
            position = False
            entry_price = 0.0
        weights[index] = position_size if position else 0.0
        if index == len(bars) - 1:
            weights[index] = 0.0
    return weights

def generate_signal_scores(bars, parameters):
    short_window = max(1, int(parameters.get("short_window", 5)))
    long_window = max(short_window + 1, int(parameters.get("long_window", 20)))
    atr_window = max(1, int(parameters.get("atr_window", 14)))
    closes = [float(bar.get("close") or 0.0) for bar in bars]
    highs = [float(bar.get("high") or 0.0) for bar in bars]
    lows = [float(bar.get("low") or 0.0) for bar in bars]
    true_ranges = []
    scores = []
    for index in range(len(bars)):
        previous_close = closes[index - 1] if index > 0 else closes[index]
        true_ranges.append(max(highs[index] - lows[index], abs(highs[index] - previous_close), abs(lows[index] - previous_close)))
        if index + 1 < long_window:
            scores.append(None)
            continue
        short_ma = sum(closes[index - short_window + 1:index + 1]) / short_window
        long_ma = sum(closes[index - long_window + 1:index + 1]) / long_window
        atr_start = max(0, index - atr_window + 1)
        atr_values = true_ranges[atr_start:index + 1]
        atr = sum(atr_values) / len(atr_values) if atr_values else 0.0
        scores.append(max(-10.0, min(10.0, (short_ma - long_ma) / atr)) if atr > 0 else 0.0)
    return scores
'''
    return [        {"strategy_id": "moving_average_strategy", "name": "双均线趋势策略", "source_code": moving_average, "parameters": {"short_window": 5, "long_window": 20, "position_size": 1.0}, "category": "趋势跟随", "description": "短长均线交叉的本地可执行策略。"},
        {"strategy_id": "risk_controlled_breakout", "name": "突破策略", "source_code": breakout, "parameters": {"breakout_window": 20, "max_position": 0.5}, "category": "趋势突破", "description": "突破前期高点时建立目标仓位。"},
        {"strategy_id": "buy_and_hold", "name": "买入持有基线", "source_code": buy_hold, "parameters": {"position_size": 1.0}, "category": "基线", "description": "用于验证策略执行差异的买入持有基线。"},
        {"strategy_id": "dual_ma_atr_dynamic_stop", "name": "双均线 + ATR动态止损", "source_code": dual_ma_atr, "parameters": {"short_window": 5, "long_window": 20, "atr_window": 14, "atr_multiplier": 2.0, "position_size": 1.0, "commission": 0.0003}, "category": "趋势跟随 / 风险控制", "description": "MA5/MA20 金叉全仓买入、死叉清仓，持仓期间以开仓价减去 ATR14 的 2 倍作为动态止损线。"},
    ]
