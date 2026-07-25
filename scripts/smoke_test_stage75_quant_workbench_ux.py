"""阶段 75 量化工作台交互内聚静态烟测。"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    required_app = [
        "configureStage75Shell",
        "strategy-pc-workbench",
        "backtest-common-config",
        "createAndRunStage75",
        "cloneStage75SingleRun",
        "cloneStage75Task",
        "openStage75ResultDock",
        "stage75-report-compare",
        "addStage75ComparisonRun",
        "page-report-management",
        "configureStage75Relocations",
        "mode-report-active",
        "updateStage75Url",
    ]
    for marker in required_app:
        assert marker in app, marker
    for marker in ["Stage 75 PC quant workbench", ".strategy-pc-workbench", ".stage75-result-dock", ".comparison-chart-grid"]:
        assert marker in css, marker
    assert "/app.js?v=769" in html
    assert "/styles.css?v=769" in html
    assert "最多同时对比 4 个 Run" in app
    assert "不会自动启动" in app
    print("stage75 quant workbench ux smoke passed")


if __name__ == "__main__":
    main()
