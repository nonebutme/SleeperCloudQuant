"""Professional reports for independent-screening and shared-portfolio modes."""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable


class BacktestModeReportService:
    """Build reports without mixing independent and shared-account semantics."""

    def __init__(
        self,
        reporting_service: Any,
        independent_screening_service: Any,
        shared_portfolio_service: Any,
        runtime_store: Any,
        classification_store: Any,
    ) -> None:
        self._reporting_service = reporting_service
        self._independent = independent_screening_service
        self._shared = shared_portfolio_service
        self._runtime_store = runtime_store
        self._classifications = classification_store

    def get_shared_portfolio_report(self, task_id: str) -> dict[str, Any]:
        task = self._shared.get_task(task_id)
        if task.get("status") == "not_found":
            return {"report_mode": "shared_portfolio", "status": "not_found", "task_id": task_id}
        run_id = str(task.get("run_id") or "")
        evaluation = self._reporting_service.get_strategy_evaluation(run_id) if run_id else None
        detail = self._reporting_service.get_run_detail(run_id) if run_id else None
        professional_report = _plain(evaluation)
        run_detail = _plain(detail)
        return {
            "report_mode": "shared_portfolio",
            "report_version": "stage74-shared-portfolio-seven-dimension-v2",
            "status": task.get("status"),
            "task_id": task_id,
            "run_id": run_id or None,
            "template": "shared_portfolio_strategy_evaluation_7_dimensions_v2",
            "task": task,
            "professional_report": professional_report,
            "run_detail": run_detail,
            "report_contract": {
                "scope": "shared_portfolio_account",
                "default_tab": "portfolio_evaluation",
                "tabs": ["portfolio_evaluation", "attribution", "positions_and_trades", "data_quality"],
                "demo_fallback_allowed": False,
            },
            "portfolio_sections": _shared_portfolio_sections(run_detail),
            "data_quality_gate": _shared_data_quality_gate(professional_report, run_detail),
            "semantic_boundary": {
                "account_scope": "single_shared_account",
                "equity_curve": "one_portfolio_curve",
                "not_independent_run_average": True,
            },
        }

    def get_independent_screening_report(self, task_id: str) -> dict[str, Any]:
        task = self._independent.get_task(task_id)
        if task.get("status") == "not_found":
            return {"report_mode": "independent_screening", "status": "not_found", "task_id": task_id}
        all_items = self._read_all_items(task_id)
        entered = [item for item in all_items if item.get("entered") and item.get("status") == "completed"]
        observations = [self._observation(item, task) for item in entered]
        returns = [float(row["total_returns"]) for row in observations if row.get("total_returns") is not None]
        distribution = _distribution_analysis(returns, seed=task_id)
        groups = {
            "market": _group_analysis(observations, lambda row: [str(row.get("market") or "未分类")]),
            "board": _group_analysis(observations, lambda row: [str(row.get("board") or "其他板块")]),
            "entry_period": _group_analysis(observations, lambda row: [str(row.get("entry_period") or "未建仓时段")]),
            "industry": _group_analysis(observations, lambda row: list(row.get("industries") or ["未分类"])),
            "concept": _group_analysis(observations, lambda row: list(row.get("concepts") or ["未分类"])),
        }
        coverage = {
            "industry": _classification_coverage(observations, "industries"),
            "concept": _classification_coverage(observations, "concepts"),
            "entry_period": _classification_coverage(observations, "entry_period"),
        }
        run_index = [_independent_run_index_entry(item) for item in entered]
        return {
            "report_mode": "independent_screening",
            "report_version": "stage74-independent-dual-layer-report-v2",
            "status": task.get("status"),
            "task_id": task_id,
            "title": "独立选股双层专业分析报告",
            "subtitle": "任务统计仅包含实际建仓股票；单股七维评估表示策略在该股票上的适配性。",
            "task": task,
            "sample_scope": {
                "universe_count": task.get("progress", {}).get("total", len(all_items)),
                "processed_count": task.get("progress", {}).get("processed", 0),
                "entered_count": len(entered),
                "failed_count": task.get("progress", {}).get("failed", 0),
                "no_entry_count": task.get("progress", {}).get("no_entry", 0),
                "statistics_scope": "entered_symbols_only",
            },
            "distribution": distribution,
            "risk_analysis": {
                "loss_probability": distribution.get("loss_probability"),
                "var_95": distribution.get("var_95"),
                "cvar_95": distribution.get("cvar_95"),
                "gain_loss_ratio": distribution.get("gain_loss_ratio"),
                "normality_warning": distribution.get("normality", {}).get("interpretation"),
            },
            "group_comparisons": groups,
            "classification_coverage": coverage,
            "observations": observations,
            "run_index": run_index,
            "factor_analysis": _independent_factor_analysis(observations, groups, coverage),
            "robustness_analysis": _robustness_analysis(returns),
            "report_contract": {
                "scope": "independent_capital_runs",
                "default_tab": "task_statistics",
                "tabs": ["task_statistics", "single_run_evaluation"],
                "single_run_evaluation": "strategy_on_one_symbol_not_portfolio_diversification",
                "demo_fallback_allowed": False,
            },
            "professional_sections": _professional_sections(distribution, groups, coverage, task),
            "methodology": {
                "normality_test": "Jarque-Bera; p-value uses chi-square(df=2) survival exp(-JB/2)",
                "confidence_interval": "95% mean CI; normal critical for n>=30, small-sample t critical table otherwise",
                "bootstrap": "deterministic 1000-resample percentile CI for mean",
                "histogram": "fixed A-share return buckets for UI; adaptive Freedman-Diaconis bins retained separately",
                "classification_as_of": "first effective BUY trade date",
                "look_ahead_control": "only effective-dated historical classifications are accepted",
                "correlation": "Spearman rank correlation; descriptive relationship, not causality",
            },
            "data_quality_notes": _data_quality_notes(returns, coverage),
        }

    def get_independent_run_report(self, task_id: str, run_id: str) -> dict[str, Any]:
        task = self._independent.get_task(task_id)
        if task.get("status") == "not_found":
            return {"report_mode": "independent_single_run", "status": "task_not_found", "task_id": task_id, "run_id": run_id}
        entered = [
            item for item in self._read_all_items(task_id)
            if item.get("entered") and item.get("status") == "completed" and item.get("run_id")
        ]
        selected = next((item for item in entered if str(item.get("run_id")) == run_id), None)
        if selected is None:
            return {"report_mode": "independent_single_run", "status": "run_not_in_task", "task_id": task_id, "run_id": run_id}
        evaluation = self._reporting_service.get_strategy_evaluation(run_id)
        detail = self._reporting_service.get_run_detail(run_id)
        selected_index = next(index for index, item in enumerate(entered) if str(item.get("run_id")) == run_id)
        return {
            "report_mode": "independent_single_run",
            "report_version": "stage74-independent-single-run-seven-dimension-v1",
            "status": "ready" if evaluation is not None and detail is not None else "result_unavailable",
            "task_id": task_id,
            "run_id": run_id,
            "symbol": selected.get("symbol"),
            "name": selected.get("name"),
            "item": selected,
            "professional_report": _adapt_independent_single_evaluation(_plain(evaluation)),
            "run_detail": _plain(detail),
            "navigation": {
                "run_ids": [str(item.get("run_id")) for item in entered],
                "selected_index": selected_index,
                "total": len(entered),
            },
            "semantic_boundary": {
                "account_scope": "one_independent_virtual_account",
                "evaluation_subject": "strategy_on_selected_symbol",
                "not_portfolio_evaluation": True,
            },
        }

    def _read_all_items(self, task_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self._independent.list_items(task_id, limit=500, offset=offset)
            items = list(page.get("items") or [])
            rows.extend(items)
            offset += len(items)
            if not items or offset >= int(page.get("total") or 0):
                return rows

    def _observation(self, item: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
        metrics = dict(item.get("metrics") or {})
        trades = list(self._runtime_store.fetch_backtest_trades(str(item.get("run_id") or "")))
        buys = [row for row in trades if str(row.get("side") or "").upper() == "BUY" and float(row.get("quantity") or 0) > 0]
        entry_date = min((str(row.get("trade_time") or "")[:10] for row in buys), default="")
        fallback_date = str((task.get("config") or {}).get("date_window", {}).get("start_date") or "")
        as_of = entry_date or fallback_date
        industries = [row["category"] for row in self._classifications.resolve(item.get("symbol"), "industry", as_of)] if as_of else []
        concepts = [row["category"] for row in self._classifications.resolve(item.get("symbol"), "concept", as_of)] if as_of else []
        return {
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "market": item.get("market") or "未分类",
            "board": _infer_market_board(str(item.get("symbol") or "")),
            "run_id": item.get("run_id"),
            "entry_date": entry_date or None,
            "entry_period": entry_date[:7] if entry_date else None,
            "industries": industries,
            "concepts": concepts,
            "total_returns": _optional_float(metrics.get("total_returns")),
            "annualized_returns": _optional_float(metrics.get("annualized_returns")),
            "max_drawdown": _optional_float(metrics.get("max_drawdown")),
            "sharpe": _optional_float(metrics.get("sharpe")),
        }


def _infer_market_board(symbol: str) -> str:
    code = symbol.split(".", 1)[0]
    suffix = symbol.split(".", 1)[1].upper() if "." in symbol else ""
    if suffix == "XBJ" or code.startswith(("4", "8", "9")):
        return "北交所"
    if code.startswith(("688", "689")):
        return "科创板"
    if code.startswith(("300", "301")):
        return "创业板"
    if code.startswith(("600", "601", "603", "605")):
        return "沪市主板"
    if code.startswith(("000", "001", "002", "003")):
        return "深市主板"
    return "其他板块"

def _adapt_independent_single_evaluation(report: dict[str, Any] | None) -> dict[str, Any] | None:
    """将组合型通用报告的第 7 维改写为独立单股账户的数据可靠性。"""
    if report is None:
        return None
    adapted = dict(report)
    dimensions = [dict(item) for item in adapted.get("dimensions") or []]
    evidence = dict(adapted.get("evidence_quality") or {})
    points = dict(evidence.get("points") or {})
    coverage = float(evidence.get("coverage_score") or 0.0)
    trade_points = int(points.get("trade_points") or 0)
    account_points = int(points.get("account_points") or 0)
    score = max(0, min(100, round(coverage * 70 + min(trade_points, 5) * 4 + min(account_points, 3) * 3)))
    level = "excellent" if score >= 85 else "good" if score >= 70 else "normal" if score >= 60 else "bad"
    replacement = {
        "key": "execution_data",
        "short_label": "执行数据",
        "title": "维度7：执行与数据可靠性",
        "score": score,
        "level": level,
        "evidence_status": evidence.get("grade") or "low",
        "score_reason": "评分仅依据该单股账户的真实账户、成交与覆盖证据，不使用组合分散度或演示值。",
        "metrics": [
            {"label": "证据等级", "value": evidence.get("grade") or "low"},
            {"label": "数据覆盖", "value": f"{coverage * 100:.2f}%"},
            {"label": "成交证据点", "value": trade_points},
            {"label": "账户证据点", "value": account_points},
        ],
        "chart": {
            "kind": "bar",
            "rows": [
                {"label": "数据覆盖", "value": round(coverage * 100, 2), "display": f"{coverage * 100:.2f}%"},
                {"label": "成交证据", "value": trade_points, "display": str(trade_points)},
                {"label": "账户证据", "value": account_points, "display": str(account_points)},
            ],
        },
    }
    dimensions = [replacement if item.get("key") == "diverse" else item for item in dimensions]
    adapted["dimensions"] = dimensions
    adapted["evaluation_scope"] = "independent_single_symbol_virtual_account"
    adapted["report_version"] = "stage74-independent-single-run-seven-dimension-v1"
    adapted["average_score"] = round(sum(float(item.get("score") or 0) for item in dimensions) / len(dimensions)) if dimensions else None
    adapted["data_quality_notes"] = list(adapted.get("data_quality_notes") or []) + [
        "独立选股单股报告不评价组合分散度；第 7 维仅评价该单股虚拟账户的执行与数据可靠性。"
    ]
    return adapted

def _independent_run_index_entry(item: dict[str, Any]) -> dict[str, Any]:
    metrics = dict(item.get("metrics") or {})
    return {
        "run_id": item.get("run_id"),
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "market": item.get("market"),
        "total_returns": _optional_float(metrics.get("total_returns")),
        "annualized_returns": _optional_float(metrics.get("annualized_returns")),
        "max_drawdown": _optional_float(metrics.get("max_drawdown")),
        "sharpe": _optional_float(metrics.get("sharpe")),
        "evaluation_link": f"/api/reporting/strategy-evaluation/{item.get('run_id')}",
    }


def _independent_factor_analysis(
    observations: list[dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    numeric_relationships = []
    for key, label in (
        ("annualized_returns", "年化收益"),
        ("max_drawdown", "最大回撤"),
        ("sharpe", "Sharpe"),
    ):
        pairs = [
            (float(row[key]), float(row["total_returns"]))
            for row in observations
            if row.get(key) is not None and row.get("total_returns") is not None
        ]
        numeric_relationships.append({
            "factor": key,
            "label": label,
            "sample_size": len(pairs),
            "spearman": _spearman(pairs),
            "interpretation": "performance_relationship_not_causality",
        })
    categorical = []
    for key, rows in groups.items():
        valid = [row for row in rows if row.get("sample_size")]
        ordered = sorted(valid, key=lambda row: float(row.get("mean") or 0.0))
        categorical.append({
            "factor": key,
            "category_count": len(valid),
            "sample_size": sum(int(row.get("sample_size") or 0) for row in valid),
            "best_category": ordered[-1].get("category") if ordered else None,
            "worst_category": ordered[0].get("category") if ordered else None,
            "mean_spread": (float(ordered[-1].get("mean") or 0.0) - float(ordered[0].get("mean") or 0.0)) if len(ordered) > 1 else None,
            "status": "ready" if len(valid) > 1 else "insufficient_groups",
        })
    registry = [
        {"factor": "market", "kind": "categorical", "status": "available", "as_of": "task_symbol_master"},
        {"factor": "board", "kind": "categorical", "status": "available", "as_of": "symbol_code_rule"},
        {"factor": "entry_period", "kind": "categorical", "status": "available", "as_of": "first_buy_date"},
        {"factor": "industry", "kind": "categorical", "status": "available" if coverage["industry"]["covered_count"] else "unavailable", "as_of": "first_buy_date"},
        {"factor": "concept", "kind": "multi_label", "status": "available" if coverage["concept"]["covered_count"] else "unavailable", "as_of": "first_buy_date"},
        {"factor": "benchmark_beta_correlation", "kind": "continuous", "status": "data_asset_required", "required_asset": "historical_benchmark_aligned_returns"},
        {"factor": "market_sentiment", "kind": "continuous", "status": "data_asset_required", "required_asset": "effective_dated_sentiment_series"},
        {"factor": "market_hotspot", "kind": "categorical", "status": "data_asset_required", "required_asset": "effective_dated_hotspot_series"},
        {"factor": "valuation_liquidity_size", "kind": "continuous", "status": "data_asset_required", "required_asset": "effective_dated_fundamental_factor_series"},
    ]
    return {
        "version": "stage74-factor-registry-v1",
        "outcome": "total_returns",
        "numeric_relationships": numeric_relationships,
        "categorical_effects": categorical,
        "factor_registry": registry,
        "causality_warning": "相关性和分组差异仅用于研究解释，不构成因果结论。",
    }


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor
        while end + 1 < len(order) and values[order[end + 1]] == values[order[cursor]]:
            end += 1
        rank = (cursor + end) / 2.0 + 1.0
        for position in range(cursor, end + 1):
            ranks[order[position]] = rank
        cursor = end + 1
    return ranks


def _spearman(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 3:
        return None
    left = _rank([row[0] for row in pairs])
    right = _rank([row[1] for row in pairs])
    left_mean = statistics.mean(left)
    right_mean = statistics.mean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right))
    return numerator / denominator if denominator else None


def _robustness_analysis(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"status": "insufficient_sample", "sample_size": 0}
    ordered = sorted(values)
    trimmed = ordered[1:-1] if len(ordered) >= 5 else ordered
    return {
        "status": "ready" if len(values) >= 8 else "limited_sample",
        "sample_size": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "trimmed_mean": statistics.mean(trimmed),
        "top_bottom_removed_count": len(values) - len(trimmed),
        "conclusion_stable": abs(statistics.mean(values) - statistics.mean(trimmed)) <= max(statistics.pstdev(values), 1e-12),
    }


def _shared_portfolio_sections(detail: Any) -> dict[str, Any]:
    if not isinstance(detail, dict):
        return {"status": "run_unavailable"}
    return {
        "status": "ready",
        "equity_point_count": len(detail.get("account_value_chart") or detail.get("accounts") or []),
        "trade_count": len(detail.get("trades") or []),
        "position_point_count": len(detail.get("positions") or []),
        "yearly_return_count": len(detail.get("yearly_returns") or detail.get("yearly_return_chart") or []),
        "metrics": detail.get("metrics") or {},
        "sections": ["net_value_and_drawdown", "seven_dimensions", "attribution", "positions", "cost_capacity", "data_quality"],
    }


def _shared_data_quality_gate(evaluation: Any, detail: Any) -> dict[str, Any]:
    if not isinstance(evaluation, dict) or not isinstance(detail, dict):
        return {"status": "unavailable", "score_allowed": False, "reason": "run_or_evaluation_missing"}
    dimensions = list(evaluation.get("dimensions") or [])
    evidence_quality = dict(evaluation.get("evidence_quality") or {})
    evidence_grade = str(evidence_quality.get("grade") or "low")
    score_allowed = len(dimensions) == 7 and evidence_grade in {"high", "medium"}
    return {
        "status": "ready" if score_allowed else "limited",
        "score_allowed": score_allowed,
        "reason": None if score_allowed else "seven_dimensions_or_evidence_quality_insufficient",
        "dimension_count": len(dimensions),
        "demo_fallback_used": False,
        "evidence_quality": evidence_quality,
    }

def _distribution_analysis(values: list[float], *, seed: str) -> dict[str, Any]:
    if not values:
        return {"sample_size": 0, "status": "insufficient_sample", "normality": {"status": "not_tested"}, "histogram": []}
    ordered = sorted(values)
    count = len(values)
    mean = statistics.mean(values)
    median = statistics.median(values)
    variance = statistics.variance(values) if count > 1 else 0.0
    stddev = math.sqrt(variance)
    skewness = sum((value - mean) ** 3 for value in values) / count / stddev ** 3 if count > 2 and stddev else 0.0
    kurtosis = sum((value - mean) ** 4 for value in values) / count / stddev ** 4 - 3.0 if count > 3 and stddev else 0.0
    jb = count / 6.0 * (skewness ** 2 + kurtosis ** 2 / 4.0) if count >= 8 else None
    p_value = math.exp(-jb / 2.0) if jb is not None else None
    standard_error = stddev / math.sqrt(count) if count else 0.0
    critical = 1.96 if count >= 30 else _t_critical_95(count - 1)
    confidence = [mean - critical * standard_error, mean + critical * standard_error] if count > 1 else [mean, mean]
    bootstrap = _bootstrap_mean_ci(values, seed=seed)
    losses = [value for value in values if value < 0]
    gains = [value for value in values if value > 0]
    var_95 = _quantile(ordered, 0.05)
    tail = [value for value in values if value <= var_95]
    return {
        "status": "ready",
        "sample_size": count,
        "mean": mean,
        "median": median,
        "variance": variance,
        "stddev": stddev,
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "q05": _quantile(ordered, 0.05),
        "q25": _quantile(ordered, 0.25),
        "q75": _quantile(ordered, 0.75),
        "q95": _quantile(ordered, 0.95),
        "skewness": skewness,
        "excess_kurtosis": kurtosis,
        "positive_probability": len(gains) / count,
        "loss_probability": len(losses) / count,
        "gain_loss_ratio": statistics.mean(gains) / abs(statistics.mean(losses)) if gains and losses else None,
        "mean_confidence_interval_95": confidence,
        "bootstrap_mean_confidence_interval_95": bootstrap,
        "var_95": var_95,
        "cvar_95": statistics.mean(tail) if tail else var_95,
        "normality": {
            "test": "Jarque-Bera",
            "statistic": jb,
            "p_value": p_value,
            "alpha": 0.05,
            "reject_normality": p_value < 0.05 if p_value is not None else None,
            "status": "tested" if p_value is not None else "insufficient_sample",
            "interpretation": (
                "收益分布显著偏离正态，不应只依赖均值和标准差。"
                if p_value is not None and p_value < 0.05
                else "当前样本未拒绝正态假设，但不代表已证明服从正态分布。"
                if p_value is not None
                else "样本少于 8，未执行 Jarque-Bera 正态性检验。"
            ),
        },
        "histogram": _a_share_return_histogram(values),
        "adaptive_histogram": _histogram(values),
    }


def _group_analysis(observations: list[dict[str, Any]], categories: Any) -> list[dict[str, Any]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in observations:
        value = row.get("total_returns")
        if value is None:
            continue
        labels = categories(row) or ["未分类"]
        for label in set(str(item or "未分类") for item in labels):
            buckets[label].append(float(value))
    result = []
    for label, values in buckets.items():
        ordered = sorted(values)
        result.append({
            "category": label,
            "sample_size": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stddev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "positive_probability": sum(value > 0 for value in values) / len(values),
            "q25": _quantile(ordered, 0.25),
            "q75": _quantile(ordered, 0.75),
        })
    return sorted(result, key=lambda row: (-float(row["mean"]), str(row["category"])))


def _classification_coverage(observations: list[dict[str, Any]], key: str) -> dict[str, Any]:
    total = len(observations)
    covered = sum(bool(row.get(key)) for row in observations)
    return {"sample_size": total, "covered_count": covered, "missing_count": total - covered, "coverage_ratio": covered / total if total else 0.0}


def _professional_sections(distribution: dict[str, Any], groups: dict[str, Any], coverage: dict[str, Any], task: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"key": "return_distribution", "title": "维度1：建仓股票收益分布", "metrics": {key: distribution.get(key) for key in ("mean", "median", "q05", "q95", "positive_probability")}},
        {"key": "tail_risk", "title": "维度2：下行与尾部风险", "metrics": {key: distribution.get(key) for key in ("loss_probability", "var_95", "cvar_95", "minimum")}},
        {"key": "risk_adjusted", "title": "维度3：横截面风险调整表现", "metrics": {"mean_over_stddev": distribution.get("mean") / distribution.get("stddev") if distribution.get("stddev") else None, "gain_loss_ratio": distribution.get("gain_loss_ratio")}},
        {"key": "stability", "title": "维度4：稳定性与正态性", "metrics": {"skewness": distribution.get("skewness"), "excess_kurtosis": distribution.get("excess_kurtosis"), **dict(distribution.get("normality") or {})}},
        {"key": "funnel", "title": "维度5：选股与建仓漏斗", "metrics": dict(task.get("progress") or {})},
        {"key": "classification", "title": "维度6：市场、行业、时段与概念对比", "metrics": {"group_counts": {key: len(value) for key, value in groups.items()}, "coverage": coverage}},
        {"key": "data_quality", "title": "维度7：样本与分类数据质量", "metrics": {"return_sample_size": distribution.get("sample_size"), "classification_coverage": coverage}},
    ]


def _data_quality_notes(values: list[float], coverage: dict[str, Any]) -> list[str]:
    notes = ["收益统计仅包含至少一笔有效 BUY 成交且运行完成的股票。"]
    if len(values) < 30:
        notes.append("收益样本少于 30，均值置信区间和正态性判断需谨慎解释。")
    for dimension in ("industry", "concept"):
        if coverage[dimension]["coverage_ratio"] < 1.0:
            notes.append(f"{dimension} 历史时点分类覆盖不足；未分类样本单独展示，不使用当前快照回填。")
    notes.append("统计关系不构成未来收益保证或投资建议。")
    return notes


def _a_share_return_histogram(values: list[float]) -> list[dict[str, Any]]:
    labels = ["跌停", "-8%-", "-8~-6%", "-6~-4%", "-4~-2%", "-2~0%", "0~2%", "2~4%", "4~6%", "6~8%", "8%+", "涨停"]
    counts = [0] * len(labels)
    for value in values:
        if value <= -0.095:
            index = 0
        elif value < -0.08:
            index = 1
        elif value < -0.06:
            index = 2
        elif value < -0.04:
            index = 3
        elif value < -0.02:
            index = 4
        elif value < 0.0:
            index = 5
        elif value < 0.02:
            index = 6
        elif value < 0.04:
            index = 7
        elif value < 0.06:
            index = 8
        elif value < 0.08:
            index = 9
        elif value < 0.095:
            index = 10
        else:
            index = 11
        counts[index] += 1
    return [{"bucket": label, "count": counts[index]} for index, label in enumerate(labels)]

def _histogram(values: list[float]) -> list[dict[str, Any]]:
    if not values:
        return []
    low, high = min(values), max(values)
    if low == high:
        return [{"lower": low, "upper": high, "count": len(values)}]
    ordered = sorted(values)
    iqr = _quantile(ordered, 0.75) - _quantile(ordered, 0.25)
    width = 2 * iqr / (len(values) ** (1 / 3)) if iqr else 0.0
    bins = math.ceil((high - low) / width) if width else math.ceil(math.sqrt(len(values)))
    bins = max(5, min(bins, 30))
    step = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - low) / step), bins - 1)
        counts[index] += 1
    return [{"lower": low + index * step, "upper": low + (index + 1) * step, "count": count} for index, count in enumerate(counts)]


def _bootstrap_mean_ci(values: list[float], *, seed: str) -> list[float]:
    if len(values) < 2:
        return [values[0], values[0]]
    generator = random.Random(seed)
    means = sorted(statistics.mean(generator.choices(values, k=len(values))) for _ in range(1000))
    return [_quantile(means, 0.025), _quantile(means, 0.975)]


def _quantile(ordered: list[float], probability: float) -> float:
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _t_critical_95(degrees: int) -> float:
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045}
    return table.get(max(degrees, 1), 1.96)


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [_plain(item) for item in value]
    return value
