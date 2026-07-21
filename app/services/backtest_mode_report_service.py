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
        return {
            "report_mode": "shared_portfolio",
            "report_version": "stage63-shared-portfolio-current-template-v1",
            "status": task.get("status"),
            "task_id": task_id,
            "run_id": run_id or None,
            "template": "current_strategy_evaluation_7_dimensions",
            "task": task,
            "professional_report": _plain(evaluation),
            "run_detail": _plain(detail),
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
            "entry_period": _group_analysis(observations, lambda row: [str(row.get("entry_period") or "未建仓时段")]),
            "industry": _group_analysis(observations, lambda row: list(row.get("industries") or ["未分类"])),
            "concept": _group_analysis(observations, lambda row: list(row.get("concepts") or ["未分类"])),
        }
        coverage = {
            "industry": _classification_coverage(observations, "industries"),
            "concept": _classification_coverage(observations, "concepts"),
            "entry_period": _classification_coverage(observations, "entry_period"),
        }
        return {
            "report_mode": "independent_screening",
            "report_version": "stage63-independent-statistical-report-v1",
            "status": task.get("status"),
            "task_id": task_id,
            "title": "独立选股建仓汇总专业分析报告",
            "subtitle": "仅对实际建仓股票进行横截面统计；未建仓股票保留在筛选漏斗，不混入收益分布。",
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
            "professional_sections": _professional_sections(distribution, groups, coverage, task),
            "methodology": {
                "normality_test": "Jarque-Bera; p-value uses chi-square(df=2) survival exp(-JB/2)",
                "confidence_interval": "95% mean CI; normal critical for n>=30, small-sample t critical table otherwise",
                "bootstrap": "deterministic 1000-resample percentile CI for mean",
                "histogram": "Freedman-Diaconis width with bounded bin count",
                "classification_as_of": "first effective BUY trade date",
                "look_ahead_control": "only effective-dated historical classifications are accepted",
            },
            "data_quality_notes": _data_quality_notes(returns, coverage),
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
        "histogram": _histogram(values),
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
