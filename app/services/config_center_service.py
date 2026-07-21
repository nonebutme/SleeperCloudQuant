"""Configuration center service for the Web MVP."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backtest_kernel import RqalphaPackageRuntime
from data_platform import ExternalMarketProviderRepository, SqliteMetadataStore

from config_center import UnifiedConfigManager


class ConfigCenterService:
    """Expose TradingAgents-style runtime configuration status without leaking secrets."""

    def __init__(self, manager: UnifiedConfigManager | None = None, draft_path: Path | None = None, sync_task_path: Path | None = None) -> None:
        self._manager = manager or UnifiedConfigManager()
        self._draft_path = draft_path or Path("var/runtime/config_runtime_draft.json")
        self._sync_task_path = sync_task_path or Path("var/runtime/market_provider_sync_tasks.json")
        self._market_bar_store = SqliteMetadataStore(Path("tmp") / "formal_http_demo.sqlite3")
        self._market_sync_tasks: dict[str, dict[str, Any]] = {}
        self._market_sync_task_counter = 0

    def get_status(self) -> dict[str, Any]:
        profiles = self._manager.get_backtest_profiles()
        draft = self._load_runtime_draft()
        default_ai_workflow = {
            "enabled_analysts": ["market", "fundamentals", "news", "social"],
            "enabled_researchers": ["bull", "bear"],
            "risk_team": ["aggressive", "neutral", "conservative"],
            "max_debate_rounds": 2,
            "provider_profile": "local-demo-tradingagents-style",
            "decision_policy": "watchlist_only_until_real_data",
            "online_tools_enabled": False,
        }
        effective = self._manager.get_effective_runtime_settings(
            defaults={
                "data_source_mode": "local-demo",
                "llm_provider_mode": "local-demo",
                "default_backtest_profile": "default_a_share",
                "report_template_mode": "structured-demo",
                "market_provider": {
                    "enabled": False,
                    "provider_name": "open-http-market-provider",
                    "base_url": "",
                    "timeout_seconds": 8,
                },
                "rqalpha_runtime": {
                    "execution_mode": "probe_then_local_fallback",
                    "prefer_real_package": False,
                },
                "ai_workflow": default_ai_workflow,
            },
            file_settings=draft.get("settings", {}),
        )
        ai_workflow = self._normalize_ai_workflow(effective.get("ai_workflow"), default_ai_workflow)
        effective["ai_workflow"] = ai_workflow
        effective["rqalpha_runtime"] = _normalize_rqalpha_runtime(effective.get("rqalpha_runtime"))
        llm_env_status = _llm_env_status(ai_workflow["provider_profile"])
        market_provider_config = _normalize_market_provider(effective.get("market_provider"))
        effective["market_provider"] = market_provider_config
        market_provider_status = ExternalMarketProviderRepository(
            base_url=market_provider_config["base_url"],
            provider_name=market_provider_config["provider_name"],
            timeout_seconds=market_provider_config["timeout_seconds"],
            enabled=market_provider_config["enabled"],
            endpoint_spec=market_provider_config["endpoint_spec"],
        ).provider_status()
        rqalpha_runtime_status = RqalphaPackageRuntime.probe_status()
        return {
            "data_sources": [
                {"name": "external_market_provider", "enabled": market_provider_status["enabled"], "priority": 5, "mode": "open-http", "status": market_provider_status["status"]},
                {"name": "ricequant", "enabled": False, "priority": 10, "mode": "boundary-defined", "status": "待确认真实授权与密钥"},
                {"name": "local_demo_cache", "enabled": True, "priority": 1, "mode": "demo", "status": "已用于 MVP 验证"},
                {"name": "news_provider", "enabled": False, "priority": 30, "mode": "placeholder", "status": "TradingAgents 风格新闻流占位"},
            ],
            "llm_providers": [
                {"name": "local-demo-ai", "enabled": True, "model": "structured-demo", "status": "本地结构化 mock"},
                {"name": "openai-compatible", "enabled": llm_env_status["enabled"] and ai_workflow["provider_profile"] == "openai-compatible", "model": llm_env_status["model"], "status": llm_env_status["status"]},
                {"name": "dashscope-compatible", "enabled": llm_env_status["enabled"] and ai_workflow["provider_profile"] == "dashscope-compatible", "model": llm_env_status["model"], "status": "待确认区域与密钥" if ai_workflow["provider_profile"] != "dashscope-compatible" else llm_env_status["status"]},
            ],
            "agent_settings": {
                "analysts": ai_workflow["enabled_analysts"],
                "researchers": ai_workflow["enabled_researchers"],
                "risk_team": ai_workflow["risk_team"],
                "max_debate_rounds": ai_workflow["max_debate_rounds"],
                "provider_profile": ai_workflow["provider_profile"],
                "decision_policy": ai_workflow["decision_policy"],
                "online_tools_enabled": ai_workflow["online_tools_enabled"],
            },
            "backtest_profiles": sorted(profiles.keys()),
            "runtime_settings": effective,
            "runtime_draft": draft,
            "report_templates": [
                {"name": "backtest_summary", "enabled": True, "status": "SleeperCloudQuant-old 风格摘要"},
                {"name": "backtest_replay", "enabled": True, "status": "交易/持仓/账户/年度收益"},
                {"name": "ai_stock_analysis", "enabled": True, "status": "TradingAgents 风格结构化报告"},
            ],
            "cache_policy": {"metadata_store": "sqlite", "factor_store": "sqlite", "runtime_store": "sqlite", "ttl_seconds": 60},
            "llm_provider_status": llm_env_status,
            "market_provider_status": market_provider_status,
            "rqalpha_runtime_status": rqalpha_runtime_status,
            "security_notes": ["不在配置状态 API 中返回密钥、口令或令牌。", "真实外部数据源和 LLM 接入前必须完成人工确认。", "外部 LLM 仅在 SCQ_LLM_BASE_URL、SCQ_LLM_API_KEY、SCQ_LLM_MODEL 同时配置时调用。", "外部行情仅在 SCQ_MARKET_PROVIDER_BASE_URL 与 SCQ_MARKET_PROVIDER_API_KEY 同时配置时调用。", "真实 rqalpha 包未安装或未批准执行真实策略包时会回退本地 SQLite runtime。"],
        }

    def get_backtest_profiles(self) -> dict[str, Any]:
        return self._manager.get_backtest_profiles()

    def preflight_market_provider(self, *, symbol: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        config = _normalize_market_provider(self._effective_market_provider_settings())
        provider = ExternalMarketProviderRepository(
            base_url=config["base_url"],
            provider_name=config["provider_name"],
            timeout_seconds=config["timeout_seconds"],
            enabled=config["enabled"],
            endpoint_spec=config["endpoint_spec"],
        )
        requested_symbol = str(symbol or "000001.XSHE")
        requested_start = start_date or "2020-01-01"
        requested_end = end_date or requested_start
        rows = list(provider.fetch_price_history(requested_symbol, requested_start, requested_end))
        status = provider.provider_status()
        sample = [dict(row) for row in rows[:3]]
        field_coverage = _market_preflight_field_coverage(sample)
        serialized = json.dumps({"status": status, "sample": sample}, ensure_ascii=False)
        secret_values = [value for value in (os.environ.get("SCQ_MARKET_PROVIDER_API_KEY"),) if value]
        return {
            "status": "passed" if rows and status.get("last_call", {}).get("status") == "success" else "needs_attention",
            "symbol": requested_symbol,
            "start_date": requested_start,
            "end_date": requested_end,
            "row_count": len(rows),
            "sample_rows": sample,
            "field_coverage": field_coverage,
            "provider_status": status,
            "endpoint_spec": status.get("endpoint_spec", {}),
            "checks": {
                "base_url_configured": bool(status.get("base_url_configured")),
                "api_key_configured": bool(status.get("api_key_configured")),
                "provider_call_success": status.get("last_call", {}).get("status") == "success",
                "rows_returned": bool(rows),
                "required_fields_present": all(field_coverage.values()) if field_coverage else False,
                "secret_leak_detected": any(secret in serialized for secret in secret_values),
            },
            "non_persistent": True,
        }

    def list_market_provider_sync_tasks(self) -> list[dict[str, Any]]:
        self._load_market_provider_sync_tasks()
        return [self._public_sync_task(task) for task in self._market_sync_tasks.values()]

    def create_market_provider_sync_task(
        self,
        *,
        symbols: list[str] | None = None,
        start_date: str = "2020-01-01",
        end_date: str = "2020-01-02",
        interval_seconds: int | None = None,
    ) -> dict[str, Any]:
        self._load_market_provider_sync_tasks()
        normalized_symbols = _normalize_sync_symbols(symbols)
        normalized_start = str(start_date or "2020-01-01")
        normalized_end = str(end_date or normalized_start)
        interval = _normalize_interval_seconds(interval_seconds)
        self._market_sync_task_counter += 1
        task_id = f"market-sync-{self._market_sync_task_counter:04d}"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        task = {
            "task_id": task_id,
            "dataset": "price_history",
            "symbols": normalized_symbols,
            "date_window": {"start_date": normalized_start, "end_date": normalized_end},
            "cursor_by_symbol": {},
            "status": "created",
            "retry_count": 0,
            "run_count": 0,
            "row_count": 0,
            "sample_rows": [],
            "last_error": None,
            "provider_status": {},
            "schedule": {"mode": "fixed_interval" if interval else "manual", "interval_seconds": interval},
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "next_run_hint": _next_run_hint(now, interval),
            "checks": {},
        }
        self._market_sync_tasks[task_id] = task
        self._save_market_provider_sync_tasks()
        return self._public_sync_task(task)

    def get_market_provider_sync_task(self, task_id: str) -> dict[str, Any]:
        self._load_market_provider_sync_tasks()
        task = self._market_sync_tasks.get(str(task_id))
        return self._public_sync_task(task) if task else {"task_id": str(task_id), "status": "not_found"}

    def run_market_provider_sync_task(self, task_id: str) -> dict[str, Any]:
        self._load_market_provider_sync_tasks()
        task = self._market_sync_tasks.get(str(task_id))
        if task is None:
            return {"task_id": str(task_id), "status": "not_found"}
        return self._execute_market_provider_sync_task(task, manual_retry=False)

    def retry_market_provider_sync_task(self, task_id: str) -> dict[str, Any]:
        self._load_market_provider_sync_tasks()
        task = self._market_sync_tasks.get(str(task_id))
        if task is None:
            return {"task_id": str(task_id), "status": "not_found"}
        task["retry_count"] = int(task.get("retry_count") or 0) + 1
        return self._execute_market_provider_sync_task(task, manual_retry=True)

    def _execute_market_provider_sync_task(self, task: dict[str, Any], *, manual_retry: bool) -> dict[str, Any]:
        config = _normalize_market_provider(self._effective_market_provider_settings())
        provider = ExternalMarketProviderRepository(
            base_url=config["base_url"],
            provider_name=config["provider_name"],
            timeout_seconds=config["timeout_seconds"],
            enabled=config["enabled"],
            endpoint_spec=config["endpoint_spec"],
        )
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        task["status"] = "running"
        task["run_count"] = int(task.get("run_count") or 0) + 1
        task["last_run_at"] = now
        task["updated_at"] = now
        task["last_error"] = None
        all_rows: list[dict[str, Any]] = []
        next_cursors: dict[str, str] = {}
        window = task.get("date_window") if isinstance(task.get("date_window"), dict) else {}
        cursor_by_symbol = task.get("cursor_by_symbol") if isinstance(task.get("cursor_by_symbol"), dict) else {}
        try:
            for symbol in task.get("symbols", []):
                start = _cursor_start_date(cursor_by_symbol.get(symbol), str(window.get("start_date") or "2020-01-01"))
                end = str(window.get("end_date") or start)
                rows = [dict(row) for row in provider.fetch_price_history(str(symbol), start, end)]
                all_rows.extend({"symbol": symbol, **row} for row in rows)
                cursor = _latest_row_date(rows)
                if cursor:
                    next_cursors[str(symbol)] = cursor
                if rows:
                    self._market_bar_store.upsert_price_bars(
                        symbol=str(symbol),
                        rows=rows,
                        source="market_provider_sync_task",
                        synced_at=now,
                    )
        except Exception as error:  # pragma: no cover - user-configured provider safety net.
            task["status"] = "failed"
            task["last_error"] = f"{type(error).__name__}: {error}"
        status = provider.provider_status()
        field_coverage = _market_preflight_field_coverage(all_rows[:5])
        serialized = json.dumps({"provider_status": status, "sample_rows": all_rows[:5]}, ensure_ascii=False)
        secret_values = [value for value in (os.environ.get("SCQ_MARKET_PROVIDER_API_KEY"),) if value]
        success = bool(all_rows) and status.get("last_call", {}).get("status") == "success" and task.get("status") != "failed"
        if success:
            cursor_by_symbol.update(next_cursors)
            task["cursor_by_symbol"] = cursor_by_symbol
            task["status"] = "completed"
            task["last_error"] = None
        elif task.get("status") != "failed":
            last_call = status.get("last_call", {}) if isinstance(status.get("last_call"), dict) else {}
            task["status"] = "skipped" if last_call.get("status") == "skipped" else "needs_attention"
            task["last_error"] = last_call.get("reason") or status.get("status") or "provider_returned_no_rows"
        task["row_count"] = len(all_rows)
        task["sample_rows"] = all_rows[:5]
        task["provider_status"] = status
        task["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        task["next_run_hint"] = _next_run_hint(task["updated_at"], task.get("schedule", {}).get("interval_seconds"))
        task["checks"] = {
            "base_url_configured": bool(status.get("base_url_configured")),
            "api_key_configured": bool(status.get("api_key_configured")),
            "provider_call_success": status.get("last_call", {}).get("status") == "success",
            "rows_returned": bool(all_rows),
            "cursor_advanced": bool(success and next_cursors),
            "required_fields_present": all(field_coverage.values()) if field_coverage else False,
            "secret_leak_detected": any(secret in serialized for secret in secret_values),
            "manual_retry": manual_retry,
        }
        self._save_market_provider_sync_tasks()
        return self._public_sync_task(task)

    def _load_market_provider_sync_tasks(self) -> None:
        if not self._sync_task_path.exists():
            self._market_sync_tasks = {}
            self._market_sync_task_counter = 0
            return
        try:
            raw = json.loads(self._sync_task_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._market_sync_tasks = {}
            self._market_sync_task_counter = 0
            return
        rows = raw.get("tasks") if isinstance(raw, dict) else []
        tasks = {}
        for item in rows if isinstance(rows, list) else []:
            if isinstance(item, dict) and item.get("task_id"):
                tasks[str(item["task_id"])] = item
        self._market_sync_tasks = tasks
        self._market_sync_task_counter = max([_sync_task_counter_from_id(task_id) for task_id in tasks] or [0])

    def _save_market_provider_sync_tasks(self) -> None:
        self._sync_task_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tasks": list(self._market_sync_tasks.values()), "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._sync_task_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _public_sync_task(self, task: dict[str, Any]) -> dict[str, Any]:
        public = json.loads(json.dumps(task, ensure_ascii=False, default=str))
        return public

    def _effective_market_provider_settings(self) -> dict[str, Any]:
        draft = self._load_runtime_draft()
        effective = self._manager.get_effective_runtime_settings(
            defaults={"market_provider": {"enabled": False, "provider_name": "open-http-market-provider", "base_url": "", "timeout_seconds": 8, "endpoint_spec": _default_market_endpoint_spec()}},
            file_settings=draft.get("settings", {}),
        )
        provider = effective.get("market_provider") if isinstance(effective, dict) else {}
        return provider if isinstance(provider, dict) else {}
    def save_runtime_draft(self, settings: dict[str, Any]) -> dict[str, Any]:
        safe_settings = self._remove_sensitive_fields(settings)
        draft = {"settings": safe_settings, "saved_at": datetime.now(timezone.utc).isoformat(), "source": "web-mvp-config-center"}
        self._draft_path.parent.mkdir(parents=True, exist_ok=True)
        self._draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        if hasattr(self._manager, "_provider") and hasattr(self._manager._provider, "invalidate"):
            self._manager._provider.invalidate()
        return draft

    def _normalize_ai_workflow(self, value: Any, default: dict[str, Any]) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        allowed = {
            "enabled_analysts": {"market", "fundamentals", "news", "social"},
            "enabled_researchers": {"bull", "bear"},
            "risk_team": {"aggressive", "neutral", "conservative"},
        }
        normalized = dict(default)
        for key, choices in allowed.items():
            items = raw.get(key)
            if isinstance(items, list):
                selected = [str(item).strip().lower() for item in items if str(item).strip().lower() in choices]
                if selected:
                    normalized[key] = selected
        try:
            normalized["max_debate_rounds"] = max(1, min(int(raw.get("max_debate_rounds", default["max_debate_rounds"])), 3))
        except (TypeError, ValueError):
            normalized["max_debate_rounds"] = default["max_debate_rounds"]
        if raw.get("provider_profile"):
            normalized["provider_profile"] = str(raw["provider_profile"])
        if raw.get("decision_policy"):
            normalized["decision_policy"] = str(raw["decision_policy"])
        normalized["online_tools_enabled"] = bool(raw.get("online_tools_enabled", default["online_tools_enabled"]))
        return normalized
    def _load_runtime_draft(self) -> dict[str, Any]:
        if not self._draft_path.exists():
            return {"settings": {}, "saved_at": None, "source": None}
        try:
            raw = json.loads(self._draft_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"settings": {}, "saved_at": None, "source": "unreadable-draft"}
        if not isinstance(raw, dict):
            return {"settings": {}, "saved_at": None, "source": "invalid-draft"}
        settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
        return {"settings": self._remove_sensitive_fields(settings), "saved_at": raw.get("saved_at"), "source": raw.get("source")}

    def _remove_sensitive_fields(self, settings: dict[str, Any]) -> dict[str, Any]:
        blocked = ("key", "secret", "token", "password", "passwd", "credential")
        safe: dict[str, Any] = {}
        for key, value in settings.items():
            normalized = str(key).lower()
            if any(marker in normalized for marker in blocked):
                continue
            if isinstance(value, dict):
                safe[key] = self._remove_sensitive_fields(value)
            elif isinstance(value, list):
                safe[key] = [self._remove_sensitive_fields(item) if isinstance(item, dict) else item for item in value]
            else:
                safe[key] = value
        return safe




def _normalize_market_provider(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    try:
        timeout = float(raw.get("timeout_seconds", 8))
    except (TypeError, ValueError):
        timeout = 8.0
    timeout = max(1.0, min(timeout, 60.0))
    return {
        "enabled": bool(raw.get("enabled", False)),
        "provider_name": str(raw.get("provider_name") or "open-http-market-provider"),
        "base_url": str(raw.get("base_url") or ""),
        "timeout_seconds": timeout,
        "api_key_policy": "env_only_SCQ_MARKET_PROVIDER_API_KEY",
        "endpoint_spec": _normalize_market_endpoint_spec(raw.get("endpoint_spec")),
    }


def _normalize_rqalpha_runtime(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    mode = str(raw.get("execution_mode") or "probe_then_local_fallback")
    if mode not in {"probe_then_local_fallback", "local_only"}:
        mode = "probe_then_local_fallback"
    return {
        "execution_mode": mode,
        "prefer_real_package": bool(raw.get("prefer_real_package", False)),
        "local_capabilities": ["package_probe", "strategy_library", "parameter_schema", "local_sqlite_backtest", "report_persistence", "fallback_trace"],
        "pending_real_capabilities": ["rqalpha_data_bundle", "strategy_file_execution", "commission_slippage_model", "benchmark_alignment", "external_provider_e2e"],
    }
def _llm_env_status(provider_profile: str | None) -> dict[str, Any]:
    profile = str(provider_profile or "local-demo-tradingagents-style")
    external = profile in {"openai-compatible", "dashscope-compatible", "external-openai-compatible", "real-llm-provider"}
    base_url_ready = bool(os.environ.get("SCQ_LLM_BASE_URL"))
    api_key_ready = bool(os.environ.get("SCQ_LLM_API_KEY"))
    model = os.environ.get("SCQ_LLM_MODEL") or "未配置"
    enabled = external and base_url_ready and api_key_ready and model != "未配置"
    missing = [name for name, ready in (("SCQ_LLM_BASE_URL", base_url_ready), ("SCQ_LLM_API_KEY", api_key_ready), ("SCQ_LLM_MODEL", model != "未配置")) if not ready]
    return {
        "provider_profile": profile,
        "enabled": enabled,
        "mode": "external-openai-compatible" if external else "local-demo",
        "model": model,
        "base_url_configured": base_url_ready,
        "api_key_configured": api_key_ready,
        "missing": missing if external else [],
        "status": "ready" if enabled else ("fallback_to_local_demo" if external else "local_demo"),
    }






def _default_market_endpoint_spec() -> dict[str, Any]:
    return {
        "price_history_path": "/price-history",
        "price_history_rows_path": "rows",
        "trading_calendar_path": "/trading-calendar",
        "trading_calendar_days_path": "days",
        "field_mapping": {
            "date": ["date", "trade_date"],
            "open": ["open", "open_price"],
            "high": ["high", "high_price"],
            "low": ["low", "low_price"],
            "close": ["close", "close_price"],
            "volume": ["volume", "vol"],
        },
        "pagination": {"enabled": False, "page_param": "page", "page_size_param": "page_size", "page_size": 200, "next_cursor_path": "next_cursor", "next_cursor_param": "cursor", "max_pages": 1},
        "retry": {"max_attempts": 1},
    }


def _normalize_market_endpoint_spec(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    default = _default_market_endpoint_spec()
    spec = dict(default)
    for key in ("price_history_path", "price_history_rows_path", "trading_calendar_path", "trading_calendar_days_path"):
        if raw.get(key):
            spec[key] = str(raw[key])
    field_mapping = raw.get("field_mapping") if isinstance(raw.get("field_mapping"), dict) else {}
    normalized_mapping: dict[str, list[str]] = {}
    for key, fallback in default["field_mapping"].items():
        value = field_mapping.get(key)
        if isinstance(value, str):
            aliases = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            aliases = [str(item).strip() for item in value if str(item).strip()]
        else:
            aliases = []
        normalized_mapping[key] = aliases or list(fallback)
    spec["field_mapping"] = normalized_mapping
    pagination = raw.get("pagination") if isinstance(raw.get("pagination"), dict) else {}
    retry = raw.get("retry") if isinstance(raw.get("retry"), dict) else {}
    try:
        page_size = int(pagination.get("page_size", default["pagination"]["page_size"]))
    except (TypeError, ValueError):
        page_size = default["pagination"]["page_size"]
    try:
        max_pages = int(pagination.get("max_pages", default["pagination"]["max_pages"]))
    except (TypeError, ValueError):
        max_pages = default["pagination"]["max_pages"]
    try:
        max_attempts = int(retry.get("max_attempts", default["retry"]["max_attempts"]))
    except (TypeError, ValueError):
        max_attempts = default["retry"]["max_attempts"]
    spec["pagination"] = {
        "enabled": bool(pagination.get("enabled", default["pagination"]["enabled"])),
        "page_param": str(pagination.get("page_param") or default["pagination"]["page_param"]),
        "page_size_param": str(pagination.get("page_size_param") or default["pagination"]["page_size_param"]),
        "page_size": max(1, min(page_size, 5000)),
        "next_cursor_path": str(pagination.get("next_cursor_path") or default["pagination"]["next_cursor_path"]),
        "next_cursor_param": str(pagination.get("next_cursor_param") or default["pagination"]["next_cursor_param"]),
        "max_pages": max(1, min(max_pages, 50)),
    }
    spec["retry"] = {"max_attempts": max(1, min(max_attempts, 5))}
    return spec




def _market_preflight_field_coverage(rows: list[dict[str, Any]]) -> dict[str, bool]:
    required = ("date", "open", "high", "low", "close", "volume")
    if not rows:
        return {field: False for field in required}
    return {field: all(row.get(field) not in (None, "") for row in rows) for field in required}


def _normalize_sync_symbols(symbols: list[str] | None) -> list[str]:
    values = symbols if isinstance(symbols, list) else []
    normalized = []
    for value in values:
        symbol = str(value).strip()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    return normalized[:50] or ["000001.XSHE"]


def _normalize_interval_seconds(value: int | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return max(30, min(seconds, 86400))


def _next_run_hint(iso_timestamp: str, interval_seconds: int | None) -> str | None:
    interval = _normalize_interval_seconds(interval_seconds)
    if not interval:
        return None
    try:
        current = datetime.fromisoformat(str(iso_timestamp).replace("Z", "+00:00"))
    except ValueError:
        current = datetime.now(timezone.utc)
    return (current + timedelta(seconds=interval)).isoformat(timespec="seconds")


def _cursor_start_date(cursor: Any, fallback: str) -> str:
    cursor_text = str(cursor or "").strip()
    if not cursor_text:
        return fallback
    try:
        return (datetime.fromisoformat(cursor_text).date() + timedelta(days=1)).isoformat()
    except ValueError:
        return fallback


def _latest_row_date(rows: list[dict[str, Any]]) -> str | None:
    dates = [str(row.get("date") or "").strip() for row in rows if row.get("date")]
    return max(dates) if dates else None

def _sync_task_counter_from_id(task_id: str) -> int:
    try:
        return int(str(task_id).rsplit("-", 1)[-1])
    except ValueError:
        return 0