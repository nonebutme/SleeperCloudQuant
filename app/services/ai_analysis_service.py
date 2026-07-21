"""Local-demo AI analysis service for the Web MVP."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from app.schemas.ai import AIAnalysisReportPayload
from app.services.factor_research_service import FactorResearchService
from app.services.llm_provider_service import LLMProviderGateway
from app.services.market_data_service import MarketDataService


class AIAnalysisService:
    """Generate a TradingAgents-style structured research workflow without external LLM dependency."""

    def __init__(
        self,
        market_data_service: MarketDataService,
        factor_research_service: FactorResearchService,
        workflow_store: Any | None = None,
        llm_provider: LLMProviderGateway | None = None,
    ) -> None:
        self._market_data_service = market_data_service
        self._factor_research_service = factor_research_service
        self._workflow_store = workflow_store
        self._llm_provider = llm_provider or LLMProviderGateway()

    def run_workflow(
        self,
        *,
        symbol: str,
        analysis_date: str | None = None,
        report_id: str | None = None,
        max_debate_rounds: int = 1,
        include_risk_notice: bool = True,
        enabled_analysts: Sequence[str] | None = None,
        enabled_researchers: Sequence[str] | None = None,
        risk_team: Sequence[str] | None = None,
        provider_profile: str | None = None,
        decision_policy: str | None = None,
    ) -> dict[str, Any]:
        bars = self._market_data_service.get_price_history(symbol=symbol, start_date="2020-01-01", end_date=analysis_date or "2020-01-02")
        factor_rows = self._factor_research_service.get_factor_summary(symbol=symbol, trade_date=analysis_date or "2020-01-02", start_date="2020-01-01", end_date=analysis_date or "2020-01-02")
        latest_close = bars[-1].close if bars else 0.0
        first_close = bars[0].close if bars else latest_close
        close_change = latest_close - first_close
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normalized_report_id = report_id or f"ai-{symbol.replace('.', '-').lower()}-{analysis_date or 'demo'}"
        rounds = max(1, min(int(max_debate_rounds or 1), 3))
        analyst_keys = _normalize_enabled(enabled_analysts, ["market", "fundamentals", "news", "social"])
        researcher_keys = _normalize_enabled(enabled_researchers, ["bull", "bear"])
        risk_keys = _normalize_enabled(risk_team, ["aggressive", "neutral", "conservative"])
        provider = provider_profile or "local-demo-tradingagents-style"
        policy = decision_policy or "watchlist_only_until_real_data"

        llm_prompt = _build_llm_prompt(symbol=symbol, analysis_date=analysis_date or "2020-01-02", latest_close=latest_close, close_change=close_change, factor_row_count=len(factor_rows))
        llm_result = self._llm_provider.generate_summary(provider_profile=provider, prompt=llm_prompt)
        analyst_catalog = {
            "market": {"agent": "Market Analyst", "stage": "analyst", "status": "completed", "artifact_key": "market_report", "content": f"{symbol} demo 区间末端收盘价 {latest_close:.2f}，区间变化 {close_change:.2f}。"},
            "fundamentals": {"agent": "Fundamentals Analyst", "stage": "analyst", "status": "demo-limited", "artifact_key": "fundamentals_report", "content": "财务数据源尚未接入，保留 fundamentals 槽位与待办。"},
            "news": {"agent": "News Analyst", "stage": "analyst", "status": "demo-limited", "artifact_key": "news_report", "content": "新闻源尚未接入，当前不生成外部新闻判断。"},
            "social": {"agent": "Social Analyst", "stage": "analyst", "status": "demo-limited", "artifact_key": "sentiment_report", "content": "社媒情绪源尚未接入，当前不生成情绪结论。"},
        }
        analyst_messages = [analyst_catalog[key] for key in analyst_keys if key in analyst_catalog]

        debate_rounds = []
        for round_index in range(1, rounds + 1):
            messages = []
            if "bull" in researcher_keys:
                messages.append({"agent": "Bull Researcher", "stance": "积极", "content": f"第 {round_index} 轮：价格样例上行，因子摘要数量 {len(factor_rows)}，可进入回测验证。"})
            if "bear" in researcher_keys:
                messages.append({"agent": "Bear Researcher", "stance": "谨慎", "content": f"第 {round_index} 轮：样例窗口过短，不能外推为稳定趋势。"})
            messages.append({"agent": "Research Manager", "stance": "折中", "content": "允许进入观察清单和回测验证，不形成真实交易建议。"})
            debate_rounds.append({"round": round_index, "messages": messages, "status": "completed"})

        risk_catalog = {
            "aggressive": {"agent": "Aggressive Risk Analyst", "vote": "conditional_watch", "content": "可小仓位试验，但必须限制回撤。"},
            "neutral": {"agent": "Neutral Risk Analyst", "vote": "watchlist_only", "content": "建议结合因子截面和回测报告交叉确认。"},
            "conservative": {"agent": "Conservative Risk Analyst", "vote": "reject_live_trade", "content": "真实数据未接入前不应给出真实操作结论。"},
        }
        risk_votes = [risk_catalog[key] for key in risk_keys if key in risk_catalog]
        vote_summary: dict[str, int] = {}
        for item in risk_votes:
            vote = str(item.get("vote") or "unknown")
            vote_summary[vote] = vote_summary.get(vote, 0) + 1
        decision_action = "watchlist_only" if policy == "watchlist_only_until_real_data" else policy
        portfolio_decision = {
            "action": decision_action,
            "confidence": "demo-low",
            "rationale": "当前只有本地 demo 行情与因子摘要，建议进入观察和回测验证，不进入真实交易。",
            "risk_vote_summary": vote_summary,
            "decision_policy": policy,
        }
        timeline = [
            {"stage": "llm_provider", "status": llm_result.status, "artifact": "llm_provider_trace", "summary": _llm_timeline_summary(llm_result.as_trace())},
            {"stage": "init", "status": "completed", "artifact": "workflow_config", "summary": f"加载本地配置：analysts={analyst_keys}, researchers={researcher_keys}, risk_team={risk_keys}。"},
            {"stage": "analyst_team", "status": "completed", "artifact": "analyst_messages", "summary": f"完成 {len(analyst_messages)} 个分析师中间产物。"},
            {"stage": "research_debate", "status": "completed", "artifact": "debate_rounds", "summary": f"完成 {rounds} 轮 bull/bear/research manager 辩论。"},
            {"stage": "risk_committee", "status": "completed", "artifact": "risk_votes", "summary": f"完成 {len(risk_votes)} 个风险角色投票。"},
            {"stage": "portfolio_manager", "status": "completed", "artifact": "portfolio_decision", "summary": f"组合经理按 {policy} 输出 {decision_action} 决策。"},
        ]
        risk_factors = [
            "当前报告使用本地 demo 数据生成，不能代表真实行情覆盖。",
            "AI 分析仅用于研究辅助，不构成投资建议。",
            "真实数据源、真实 LLM 与人工复核流程仍待确认。",
        ] if include_risk_notice else []
        artifacts = {item["artifact_key"]: item for item in analyst_messages}
        artifacts["investment_plan"] = portfolio_decision
        workflow = {
            "workflow_id": normalized_report_id,
            "symbol": symbol,
            "analysis_date": analysis_date or "2020-01-02",
            "report_id": report_id,
            "status": "completed",
            "generated_at": generated_at,
            "provider_mode": provider,
            "max_debate_rounds": rounds,
            "enabled_analysts": analyst_keys,
            "enabled_researchers": researcher_keys,
            "risk_team": risk_keys,
            "decision_policy": policy,
            "timeline": timeline,
            "agent_messages": analyst_messages,
            "debate_rounds": debate_rounds,
            "risk_votes": risk_votes,
            "portfolio_decision": portfolio_decision,
            "artifacts": artifacts,
            "metrics": {"latest_close": latest_close, "first_close": first_close, "close_change": close_change, "factor_row_count": len(factor_rows)},
            "risk_factors": risk_factors,
            "llm_provider_trace": llm_result.as_trace(),
            "source_trace": {"primary_reference": "TradingAgents-CN-main", "data_reference": "SleeperCloudQuant-old", "implemented_as": "app.services.AIAnalysisService.run_workflow", "provider_profile": provider, "llm_provider_status": llm_result.status},
        }
        self._save_workflow_trace(workflow)
        return workflow

    def list_workflows(self, *, symbol: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if self._workflow_store is None or not hasattr(self._workflow_store, "fetch_ai_workflow_runs"):
            return []
        rows = self._workflow_store.fetch_ai_workflow_runs(symbol=symbol, limit=limit)
        summaries: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row.get("payload") or {})
            summaries.append(
                {
                    "workflow_id": str(row.get("workflow_id") or payload.get("workflow_id") or ""),
                    "symbol": str(row.get("symbol") or payload.get("symbol") or ""),
                    "analysis_date": row.get("analysis_date") or payload.get("analysis_date"),
                    "report_id": row.get("report_id") or payload.get("report_id"),
                    "status": str(row.get("status") or payload.get("status") or "unknown"),
                    "generated_at": str(row.get("generated_at") or payload.get("generated_at") or ""),
                    "provider_mode": str(row.get("provider_mode") or payload.get("provider_mode") or ""),
                    "timeline_count": len(payload.get("timeline") or []),
                    "debate_round_count": len(payload.get("debate_rounds") or []),
                    "decision_action": str((payload.get("portfolio_decision") or {}).get("action") or ""),
                }
            )
        return summaries

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        if self._workflow_store is None or not hasattr(self._workflow_store, "fetch_ai_workflow_run"):
            return None
        row = self._workflow_store.fetch_ai_workflow_run(workflow_id)
        if row is None:
            return None
        return dict(row.get("payload") or {})

    def _save_workflow_trace(self, workflow: dict[str, Any]) -> None:
        if self._workflow_store is None or not hasattr(self._workflow_store, "save_ai_workflow_run"):
            return
        self._workflow_store.save_ai_workflow_run(
            workflow_id=str(workflow.get("workflow_id") or ""),
            symbol=str(workflow.get("symbol") or ""),
            analysis_date=workflow.get("analysis_date"),
            report_id=workflow.get("report_id"),
            status=str(workflow.get("status") or "unknown"),
            generated_at=str(workflow.get("generated_at") or ""),
            provider_mode=str(workflow.get("provider_mode") or "unknown"),
            payload=workflow,
        )

    def analyze_stock(
        self,
        *,
        symbol: str,
        analysis_date: str | None = None,
        report_id: str | None = None,
        include_risk_notice: bool = True,
    ) -> AIAnalysisReportPayload:
        workflow = self.run_workflow(
            symbol=symbol,
            analysis_date=analysis_date,
            report_id=report_id,
            max_debate_rounds=1,
            include_risk_notice=include_risk_notice,
        )
        metrics = workflow["metrics"]
        analyst_team = [
            {"role": item["agent"], "status": item["status"], "summary": item["content"]}
            for item in workflow["agent_messages"]
        ]
        research_debate = [
            {"speaker": message["agent"], "stance": message["stance"], "argument": message["content"], "round": round_item["round"]}
            for round_item in workflow["debate_rounds"]
            for message in round_item["messages"]
        ]
        risk_committee = [
            {"role": item["agent"], "view": item["content"], "vote": item["vote"]}
            for item in workflow["risk_votes"]
        ]
        return AIAnalysisReportPayload(
            report_id=workflow["workflow_id"],
            symbol=symbol,
            title=f"{symbol} TradingAgents 风格结构化研究摘要",
            status="generated",
            generated_at=workflow["generated_at"],
            data_basis=["本地行情 price-history demo 数据", "factor_lab 已存因子摘要", "TradingAgents-CN-main analyst/research/risk/portfolio 流程参考"],
            highlights=[f"{symbol} demo 区间末端收盘价为 {metrics['latest_close']:.2f}。", f"样例区间收盘价变化为 {metrics['close_change']:.2f}。", f"当前可读取 {metrics['factor_row_count']} 条因子摘要。"],
            risk_factors=workflow["risk_factors"],
            next_actions=["在数据中心确认真实数据覆盖后重新生成报告。", "在因子分析页核对 Top N 与截面结果。", "将报告与回测结果在报告中心交叉复核。"],
            disclaimer="本报告为本地 MVP demo/可选 LLM Provider 研究摘要，不构成投资建议。",
            provider_mode=workflow["provider_mode"],
            source_trace=workflow["source_trace"],
            analyst_team=analyst_team,
            research_debate=research_debate,
            risk_committee=risk_committee,
            portfolio_decision=workflow["portfolio_decision"],
            workflow_state={"timeline": workflow["timeline"], "artifact_keys": sorted(workflow["artifacts"].keys()), "workflow_id": workflow["workflow_id"]},
        )


def _normalize_enabled(value: Sequence[str] | None, default: list[str]) -> list[str]:
    if not value:
        return list(default)
    allowed = set(default)
    normalized = [str(item).strip().lower() for item in value if str(item).strip().lower() in allowed]
    return normalized or list(default)


def _build_llm_prompt(*, symbol: str, analysis_date: str, latest_close: float, close_change: float, factor_row_count: int) -> str:
    return (
        f"请基于以下本地量化上下文生成简短研究辅助摘要：标的={symbol}，日期={analysis_date}，"
        f"最新收盘价={latest_close:.2f}，区间变化={close_change:.2f}，因子摘要数量={factor_row_count}。"
        "要求：仅用于研究辅助，不给出确定性买卖建议。"
    )


def _llm_timeline_summary(trace: dict[str, Any]) -> str:
    status = trace.get("status") or "unknown"
    profile = trace.get("provider_profile") or "unknown"
    reason = trace.get("reason") or ""
    if status == "completed":
        return f"真实/外部 LLM Provider {profile} 已返回摘要。"
    if status == "skipped":
        return f"Provider {profile} 为本地 demo profile，跳过外部调用。"
    return f"Provider {profile} 未完成外部调用，状态 {status}；{reason}。"
