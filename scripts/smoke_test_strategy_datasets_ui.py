"""Static acceptance checks for the strategy Dataset catalog UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needles: tuple[str, ...], label: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"{label} missing: {missing}"


def main() -> None:
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "strategy-datasets.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "strategy-datasets.css").read_text(encoding="utf-8")
    require(html, ('src="/strategy-datasets.js?v=4"',), "HTML entry")
    require(script, (
        'button.dataset.page = "strategy-datasets"', "sd-categories", "sd-card-grid",
        'data-sd-tab="about"', 'data-sd-tab="documentation"',
        'data-sd-tab="research"', 'data-sd-tab="examples"',
        "数据概览", "使用文档", "研究分析", "代码示例",
        "documentationCodeBlock", "sd-workbench-gutter", "highlightStage76Python",
        "/api/strategy-datasets", "/instantiate", "AppVTable?.enhanceAll",
        "startNewStrategy", "/preview", "sd-preview-load", 'activateStage76Workspace("strategy")',
    ), "strategy Dataset UI")
    require(styles, (
        ".sd-shell", ".sd-sidebar", ".sd-card-grid", ".sd-detail-hero",
        ".sd-tabs", "@media (max-width: 980px)",
        ".sd-workbench-code", 'grid-template-columns: 48px minmax(0, 1fr)',
    ), "responsive styles")
    assert script.count('addEventListener("click", () => openCatalog())') == 1
    print("[strategy-datasets-ui] passed")


if __name__ == "__main__":
    main()
