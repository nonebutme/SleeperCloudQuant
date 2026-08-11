"""Stage 69 smoke checks for backtest task usability and progress semantics."""

from pathlib import Path


def require(text: str, marker: str, message: str) -> None:
    if marker not in text:
        raise SystemExit(message)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    css = (root / "web" / "styles.css").read_text(encoding="utf-8")
    service = (root / "app" / "services" / "shared_portfolio_service.py").read_text(encoding="utf-8")
    api = (root / "app" / "api" / "backtest.py").read_text(encoding="utf-8")

    require(app_js, 'function newTaskId(prefix)', "Stage 69 smoke failed: automatic task IDs missing")
    require(app_js, 'values.task_id || newTaskId("screening")', "Stage 69 smoke failed: screening auto ID missing")
    require(app_js, 'values.task_id || newTaskId("portfolio")', "Stage 69 smoke failed: portfolio auto ID missing")
    require(app_js, '独立账户批量回测创建失败：', "Stage 69 smoke failed: screening error feedback missing")
    require(app_js, 'function friendlyApiError(message)', "Stage 69 smoke failed: friendly data-version error mapping missing")
    require(app_js, 'async function applyBacktestPublishedCoverageDefaults()', "Stage 69 smoke failed: published coverage date defaults missing")
    require(app_js, 'input.max = commonCoverageEnd', "Stage 69 smoke failed: backtest end-date maximum missing")
    require(app_js, 'function taskElapsedSeconds(task = {})', "Stage 69 smoke failed: elapsed time helper missing")
    require(app_js, 'function taskExecutionLabel(task = {})', "Stage 69 smoke failed: readable execution label missing")
    require(app_js, 'raw.phase === "preparing_symbols"', "Stage 69 smoke failed: portfolio preparation phase missing")
    require(app_js, 'const color = up ? "#c43d3d" : "#16845b"', "Stage 69 smoke failed: A-share candle colors reversed")
    require(app_js, 'const color = value >= 0 ? "#c43d3d" : "#16845b"', "Stage 70 smoke failed: profit/loss bar colors not unified")
    require(app_js, 'danger ? "#16845b" : "#315f9f"', "Stage 70 smoke failed: loss chart color not unified")
    require(html, '任务编号（留空自动）', "Stage 69 smoke failed: automatic task ID form hint missing")
    require(css, '--rise: #c43d3d', "Stage 69 smoke failed: rise color must be red")
    require(css, '--fall: #16845b', "Stage 69 smoke failed: fall color must be green")
    require(service, 'progress_json TEXT NOT NULL', "Stage 69 smoke failed: portfolio progress storage missing")
    require(service, 'phase="preparing_symbols"', "Stage 69 smoke failed: stock preparation progress updates missing")
    require(service, '95.0 if phase == "simulating_account"', "Stage 69 smoke failed: account simulation progress phase missing")
    require(api, '"phase": str(progress.get("phase")', "Stage 69 smoke failed: mode task progress mapping missing")

    print("Stage 69 backtest task usability smoke passed")


if __name__ == "__main__":
    main()