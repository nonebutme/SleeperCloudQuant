"""Stage 77 backtest result and analysis report UI static smoke test."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    report_ui = (ROOT / "web" / "report-ui.js").read_text(encoding="utf-8")
    report_css = (ROOT / "web" / "report-ui.css").read_text(encoding="utf-8")

    for marker in [
        "/report-ui.css?v=871",
        "/report-ui.js?v=871",
        "/app.js?v=921",
    ]:
        assert marker in html, marker

    for marker in [
        '"单品种测试"',
        '"独立账户批量回测"',
        '"投资组合回测"',
        'rise: "#e74c3c"',
        'fall: "#2ecc71"',
        'warning: "#f39c12"',
        "metricCard",
        "svgLine",
        "svgBars",
        "svgMultiLine",
        "deriveTradeMetrics",
        "benchmarkUsable",
        "value === null || value === undefined",
        "变更需重新回测",
        "account_value_chart",
        "回测分析",
        "交易明细",
        "持仓快照",
        "账户快照",
        "data-report-download",
        "data-table-sort",
        "data-table-filter",
        "data-table-export",
        "独立账户、无限资金",
        "绝不提供总汇总净值曲线",
        "本报告不提供总的汇总净值曲线",
        "不使用演示值",
        "renderSingleAnalysis",
        "renderBatchAnalysis",
        "renderPortfolioAnalysis",
        "年化波动率",
        "平均持有天数",
        "Newey-West IC t值",
        "Q5年化收益",
        "双边年化换手率",
        "有效日期覆盖率",
        "模拟成交/VWAP偏离",
        "策略收盘持仓权重",
        "日度 IC 与累计 IC",
        "Q1—Q5 分层累计收益",
        "不可用",
    ]:
        assert marker in report_ui, marker

    for marker in [
        "window.ReportUI?.mount",
        "window.ReportUI?.renderResult",
        "window.ReportUI?.renderRawTables",
        "window.ReportUI?.renderSingleAnalysis",
        "window.ReportUI?.renderBatchAnalysis",
        "window.ReportUI?.renderPortfolioAnalysis",
    ]:
        assert marker in app, marker

    for marker in [
        "--report-rise: #e74c3c",
        "--report-fall: #2ecc71",
        "--report-warning: #f39c12",
        ".report-floating-toolbar",
        ".stage75-result-dock.report-workspace",
        "position: fixed",
        "overflow-x: hidden",
        "padding-bottom: 88px",
        ".report-primary-tabs",
        ".report-header-controls",
        ".report-metric-card",
        ".report-chart-card",
        ".report-warning",
        ".report-data-table",
        "@media (max-width:700px)",
    ]:
        assert marker in report_css, marker

    assert 'pick(metrics, ["trade_count"], trades.length)' not in report_ui
    assert 'id="report-cost-preset" disabled' in report_ui
    assert 'data-stage76-result-tab="analysis"' in report_ui
    assert "panel.querySelector('[data-stage76-result-section=\"analysis\"]')" in report_ui
    assert 'data-stage76-result-tab="overview">查看结果' not in report_ui
    assert 'data-stage76-result-tab="report">查看分析' not in report_ui
    assert report_ui.index("renderSingleAnalysis") < report_ui.index("renderBatchAnalysis")
    assert report_ui.index("renderBatchAnalysis") < report_ui.index("renderPortfolioAnalysis")
    print("stage77 backtest report ui smoke passed")


if __name__ == "__main__":
    main()
