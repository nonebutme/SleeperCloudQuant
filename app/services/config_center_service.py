"""Configuration center service for the Web MVP."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtest_kernel import RqalphaPackageRuntime

from config_center import UnifiedConfigManager


class ConfigCenterService:
    """Expose TradingAgents-style runtime configuration status without leaking secrets."""

    def __init__(
        self,
        manager: UnifiedConfigManager | None = None,
        draft_path: Path | None = None,
        sync_task_path: Path | None = None,
        a_share_scheduler: Any | None = None,
    ) -> None:
        self._manager = manager or UnifiedConfigManager()
        self._draft_path = draft_path or Path("var/runtime/config_runtime_draft.json")
        self._a_share_scheduler = a_share_scheduler

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
        effective.pop("market_provider", None)
        rqalpha_runtime_status = RqalphaPackageRuntime.probe_status()
        return {
            "data_sources": [
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
            "rqalpha_runtime_status": rqalpha_runtime_status,
            "security_notes": ["不在配置状态 API 中返回密钥、口令或令牌。", "真实外部数据源和 LLM 接入前必须完成人工确认。", "外部 LLM 仅在 SCQ_LLM_BASE_URL、SCQ_LLM_API_KEY、SCQ_LLM_MODEL 同时配置时调用。", "真实 rqalpha 包未安装或未批准执行真实策略包时会回退本地 SQLite runtime。"],
        }

    def get_backtest_profiles(self) -> dict[str, Any]:
        return self._manager.get_backtest_profiles()

    def get_a_share_scheduler_status(self) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"status": "unsupported", "reason": "a_share_scheduler_not_configured"}
        return dict(self._a_share_scheduler.get_status())

    def configure_a_share_scheduler(
        self,
        *,
        enabled: bool,
        run_time: str,
        timezone_name: str,
        adjustments: list[str],
    ) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"status": "unsupported", "reason": "a_share_scheduler_not_configured"}
        result = dict(self._a_share_scheduler.configure(
            enabled=enabled,
            run_time=run_time,
            timezone_name=timezone_name,
            adjustments=adjustments,
        ))
        if enabled:
            result["background"] = self._a_share_scheduler.start_background()
        else:
            result["background"] = self._a_share_scheduler.stop_background()
        return result

    def list_a_share_sync_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if self._a_share_scheduler is None:
            return []
        return list(self._a_share_scheduler.list_jobs(limit=limit))

    def create_a_share_sync_job(
        self,
        *,
        target_trade_date: str,
        symbols: list[str],
        all_current: bool,
        adjustments: list[str],
        run_now: bool,
    ) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"status": "unsupported", "reason": "a_share_scheduler_not_configured"}
        if not target_trade_date:
            raise ValueError("target_trade_date is required")
        job = dict(self._a_share_scheduler.create_job(
            target_trade_date=target_trade_date,
            symbols=symbols or None,
            all_current=all_current,
            adjustments=adjustments,
            mode="manual",
        ))
        if run_now and job.get("status") == "queued":
            return dict(self._a_share_scheduler.run_job(str(job["job_id"])))
        return job

    def get_a_share_sync_job(self, job_id: str) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"job_id": job_id, "status": "unsupported"}
        return dict(self._a_share_scheduler.get_job(job_id, include_items=True))

    def run_a_share_sync_job(self, job_id: str) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"job_id": job_id, "status": "unsupported"}
        return dict(self._a_share_scheduler.run_job(job_id))

    def retry_a_share_sync_job(self, job_id: str, *, run_now: bool = True) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"job_id": job_id, "status": "unsupported"}
        job = dict(self._a_share_scheduler.retry_quarantined(job_id))
        if run_now and job.get("status") == "queued":
            return dict(self._a_share_scheduler.run_job(job_id))
        return job

    def tick_a_share_scheduler(self) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"status": "unsupported", "reason": "a_share_scheduler_not_configured"}
        return dict(self._a_share_scheduler.run_due())

    def recover_a_share_scheduler(self) -> dict[str, Any]:
        if self._a_share_scheduler is None:
            return {"status": "unsupported", "reason": "a_share_scheduler_not_configured"}
        return dict(self._a_share_scheduler.recover_interrupted_jobs())

    def save_runtime_draft(self, settings: dict[str, Any]) -> dict[str, Any]:
        safe_settings = self._remove_sensitive_fields(settings)
        safe_settings.pop("market_provider", None)
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
        settings = self._remove_sensitive_fields(raw.get("settings") if isinstance(raw.get("settings"), dict) else {})
        settings.pop("market_provider", None)
        return {"settings": settings, "saved_at": raw.get("saved_at"), "source": raw.get("source")}

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




def _normalize_rqalpha_runtime(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    mode = str(raw.get("execution_mode") or "probe_then_local_fallback")
    if mode not in {"probe_then_local_fallback", "local_only"}:
        mode = "probe_then_local_fallback"
    return {
        "execution_mode": mode,
        "prefer_real_package": bool(raw.get("prefer_real_package", False)),
        "local_capabilities": ["package_probe", "strategy_library", "parameter_schema", "local_sqlite_backtest", "report_persistence", "fallback_trace"],
        "pending_real_capabilities": ["rqalpha_data_bundle", "strategy_file_execution", "commission_slippage_model", "benchmark_alignment"],
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
