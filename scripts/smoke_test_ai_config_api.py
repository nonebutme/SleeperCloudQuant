"""Smoke test for AI analysis and configuration-center API routes."""

from __future__ import annotations

import json

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    from app.runtime.demo_registry import build_demo_app
    from app.runtime.http_adapter import dispatch_request

    app = build_demo_app()
    routes = {route.name: route for route in app.routes}
    for route_name in ("ai_analyze_stock", "ai_workflow_run", "ai_workflow_history", "ai_workflow_detail", "config_status", "config_backtest_profiles", "config_runtime_draft_save"):
        if route_name not in routes:
            raise SystemExit(f"AI/config smoke test failed: missing route {route_name}")

    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/ai/analyze",
        body=json.dumps({"symbol": "000001.XSHE", "analysis_date": "2020-01-02"}).encode("utf-8"),
    )
    report = payload.get("report", {})
    if status_code != 200 or report.get("status") != "generated" or not report.get("highlights"):
        raise SystemExit("AI/config smoke test failed: AI analyze route mismatch")
    if report.get("provider_mode") != "local-demo-tradingagents-style" or not report.get("risk_factors") or not report.get("analyst_team"):
        raise SystemExit("AI/config smoke test failed: AI report boundary fields mismatch")
    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/ai/workflow/run",
        body=json.dumps({"symbol": "000001.XSHE", "analysis_date": "2020-01-02", "max_debate_rounds": 2}).encode("utf-8"),
    )
    workflow = payload.get("workflow", {})
    if status_code != 200 or workflow.get("status") != "completed" or len(workflow.get("timeline", [])) < 5:
        raise SystemExit("AI/config smoke test failed: workflow route mismatch")
    if len(workflow.get("debate_rounds", [])) != 2 or not workflow.get("risk_votes") or not workflow.get("portfolio_decision"):
        raise SystemExit("AI/config smoke test failed: workflow state fields mismatch")

    status_code, payload = dispatch_request(
        app,
        method="GET",
        path="/api/ai/workflows",
        query_string="symbol=000001.XSHE&limit=5",
    )
    workflows = payload.get("workflows", [])
    if status_code != 200 or not workflows or workflows[0].get("workflow_id") != workflow.get("workflow_id"):
        raise SystemExit("AI/config smoke test failed: workflow history mismatch")

    status_code, payload = dispatch_request(
        app,
        method="GET",
        path=f"/api/ai/workflow/{workflow.get('workflow_id')}",
    )
    if status_code != 200 or payload.get("workflow", {}).get("workflow_id") != workflow.get("workflow_id"):
        raise SystemExit("AI/config smoke test failed: workflow detail mismatch")
    draft_body = {
        "settings": {
            "data_source_mode": "local-demo",
            "llm_provider_mode": "local-demo-ai",
            "default_backtest_profile": "default_a_share",
            "api_key": "must-not-be-persisted",
        }
    }
    draft_body["settings"]["ai_workflow"] = {
        "enabled_analysts": ["market", "news"],
        "enabled_researchers": ["bear"],
        "risk_team": ["neutral"],
        "max_debate_rounds": 3,
        "provider_profile": "local-demo-ai-configured",
        "decision_policy": "watchlist_only_until_real_data",
    }
    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/config/runtime-draft",
        body=json.dumps(draft_body).encode("utf-8"),
    )
    if status_code != 200 or payload.get("status") != "draft_saved":
        raise SystemExit("AI/config smoke test failed: config draft save route mismatch")
    if "api_key" in json.dumps(payload.get("draft", {}), ensure_ascii=False):
        raise SystemExit("AI/config smoke test failed: config draft leaked sensitive key")

    status_code, payload = dispatch_request(app, method="GET", path="/api/config/status")
    status = payload.get("status", {})
    if status_code != 200 or not status.get("data_sources") or not status.get("llm_providers") or not status.get("agent_settings"):
        raise SystemExit("AI/config smoke test failed: config status route mismatch")
    if status.get("runtime_draft", {}).get("settings", {}).get("llm_provider_mode") != "local-demo-ai":
        raise SystemExit("AI/config smoke test failed: saved config draft not visible in status")
    ai_workflow = status.get("runtime_settings", {}).get("ai_workflow", {})
    if ai_workflow.get("max_debate_rounds") != 3 or ai_workflow.get("enabled_analysts") != ["market", "news"]:
        raise SystemExit("AI/config smoke test failed: AI workflow config not effective")

    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/ai/workflow/run",
        body=json.dumps({"symbol": "000001.XSHE", "analysis_date": "2020-01-02", **ai_workflow}).encode("utf-8"),
    )
    configured_workflow = payload.get("workflow", {})
    if status_code != 200 or configured_workflow.get("max_debate_rounds") != 3:
        raise SystemExit("AI/config smoke test failed: configured workflow rounds mismatch")
    if configured_workflow.get("enabled_analysts") != ["market", "news"] or configured_workflow.get("risk_team") != ["neutral"]:
        raise SystemExit("AI/config smoke test failed: configured workflow role selection mismatch")
    if any("password" in str(item).lower() or "token" in str(item).lower() for item in status.values()):
        raise SystemExit("AI/config smoke test failed: config status leaked sensitive-looking field")


    external_draft_body = {
        "settings": {
            "llm_provider_mode": "openai-compatible",
            "ai_workflow": {
                "enabled_analysts": ["market"],
                "enabled_researchers": ["bull", "bear"],
                "risk_team": ["neutral"],
                "max_debate_rounds": 1,
                "provider_profile": "openai-compatible",
                "decision_policy": "watchlist_only_until_real_data",
                "api_key": "must-not-be-persisted",
            },
        }
    }
    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/config/runtime-draft",
        body=json.dumps(external_draft_body).encode("utf-8"),
    )
    if status_code != 200 or "api_key" in json.dumps(payload, ensure_ascii=False):
        raise SystemExit("AI/config smoke test failed: external provider draft leaked sensitive key")
    status_code, payload = dispatch_request(app, method="GET", path="/api/config/status")
    status_payload = payload.get("status", {})
    llm_status = status_payload.get("llm_provider_status", {})
    effective_provider = llm_status.get("provider_profile") or status_payload.get("runtime_settings", {}).get("ai_workflow", {}).get("provider_profile")
    if status_code != 200 or effective_provider != "openai-compatible":
        raise SystemExit("AI/config smoke test failed: external provider status missing")
    if llm_status.get("enabled") or llm_status.get("status") != "fallback_to_local_demo":
        raise SystemExit("AI/config smoke test failed: unconfigured external provider should fallback")
    if not {"SCQ_LLM_BASE_URL", "SCQ_LLM_API_KEY", "SCQ_LLM_MODEL"}.issubset(set(llm_status.get("missing", []))):
        raise SystemExit("AI/config smoke test failed: missing LLM env vars not visible")
    ai_workflow = payload.get("status", {}).get("runtime_settings", {}).get("ai_workflow", {})
    status_code, payload = dispatch_request(
        app,
        method="POST",
        path="/api/ai/workflow/run",
        body=json.dumps({"symbol": "000001.XSHE", "analysis_date": "2020-01-02", **ai_workflow}).encode("utf-8"),
    )
    workflow = payload.get("workflow", {})
    trace = workflow.get("llm_provider_trace", {})
    if status_code != 200 or trace.get("status") != "fallback_to_local_demo":
        raise SystemExit("AI/config smoke test failed: workflow should record LLM provider fallback")
    if not any(item.get("stage") == "llm_provider" for item in workflow.get("timeline", [])):
        raise SystemExit("AI/config smoke test failed: workflow timeline missing LLM provider stage")
    status_code, payload = dispatch_request(app, method="GET", path="/api/config/backtest-profiles")
    if status_code != 200 or not isinstance(payload.get("profiles"), dict):
        raise SystemExit("AI/config smoke test failed: backtest profiles route mismatch")

    print("AI/config smoke test passed")


if __name__ == "__main__":
    main()








