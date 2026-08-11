from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def main() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "web" / "strategy-explorer.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "strategy-explorer.css").read_text(encoding="utf-8")

    require(html, '/strategy-explorer.js?v=1', "explorer entrypoint")
    require(js, '/api/backtest/strategies', "strategy API")
    require(js, '/api/backtest/runs', "run API")
    require(js, '/versions', "version history API")
    require(js, 'cutoff.setMonth(cutoff.getMonth() - 3)', "three-month ranking window")
    require(js, "snapshot_time", "runtime equity timestamp mapping")
    require(js, "rowsOf(p.monthly_return_heatmap)", "monthly heatmap row mapping")
    for label in (
        "Top 10",
        "Out Of Sample Return",
        "Code",
        "Version Notes",
        "Strategy Equity",
        "Drawdown",
        "Benchmark / Excess Return",
        "Exposure",
        "Asset Sales Volume",
        "Portfolio Turnover",
        "Monthly Returns",
        "Annual Returns",
    ):
        require(js, label, label)
    if "Capacity" in js:
        raise AssertionError("Capacity chart must remain excluded")
    require(js, 'typeof selectStrategy === "function"', "existing code-workbench reuse")
    require(css, ".strategy-pc-workbench.se-detail-mode.se-code-mode", "code layout mode")
    require(css, "grid-template-columns", "responsive workbench grid")
    print("strategy explorer UI smoke test passed")


if __name__ == "__main__":
    main()
