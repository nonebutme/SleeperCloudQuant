from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")


def require(source: str, marker: str) -> None:
    assert marker in source, f"missing Stage 68B marker: {marker}"


for view in ("overview", "strategy", "independent", "portfolio", "results"):
    require(HTML, f'data-backtest-view-target="{view}"')
    require(HTML, f'data-backtest-view="{view}"')

for step in ("strategy", "mode", "configure", "run"):
    require(HTML, f'data-workflow-step="{step}"')

for element_id in (
    "backtest-workspace-header",
    "backtest-context-summary",
    "screening-advanced-toggle",
    "portfolio-advanced-toggle",
    "screening-config-preview",
    "portfolio-config-preview",
):
    require(HTML, f'id="{element_id}"')

require(HTML, "independent-screening")
require(HTML, "shared-portfolio")
require(JS, "function activateBacktestView")
require(JS, "function renderBacktestConfigPreview")
require(JS, "function bindBacktestWorkspace")
require(JS, 'event.target.closest("[data-strategy-id]")')
require(CSS, ".strategy-library-item.is-selected")
require(JS, "updateScreeningActions(task);")
require(JS, "updatePortfolioActions(task);")
require(JS, "bindBacktestWorkspace();")
require(JS, r"\s]+/).filter(Boolean)")
require(CSS, ".backtest-view-panel { display: none; }")
require(CSS, ".backtest-view-panel.is-active { display: block; }")
require(CSS, ".backtest-context-summary { display: grid;")
require(CSS, ".backtest-config-preview { display: grid;")
require(CSS, ".advanced-field.is-hidden { display: none; }")
require(CSS, "@media (max-width: 560px)")

print("Stage 68B backtest workspace UI smoke passed")
