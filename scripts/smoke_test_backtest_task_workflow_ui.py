"""Smoke test for the Stage 68 backtest task workflow UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")


def require(source: str, marker: str) -> None:
    assert marker in source, f"missing Stage 68 task workflow marker: {marker}"


for view in ("overview", "single", "strategy", "independent", "portfolio", "results"):
    require(HTML, f'data-backtest-view-target="{view}"')
    require(HTML, f'data-backtest-view="{view}"')

for step in ("strategy", "mode", "configure", "run", "results"):
    require(HTML, f'data-workflow-step="{step}"')

for element_id in (
    "backtest-task-overview-active",
    "single-run-progress",
    "screening-live-progress",
    "portfolio-live-progress",
    "mode-task-directory-list",
    "mode-task-directory-detail",
    "backtest-results-context",
    "backtest-results-refresh",
    "backtest-results-report",
):
    require(HTML, f'id="{element_id}"')

for marker in (
    "function renderTaskProgress",
    "function taskProgressModel",
    "function renderActiveTaskOverview",
    "function renderModeTaskSelection",
    "function renderBacktestResultsContext",
    "async function openBacktestWorkspaceView",
    "async function refreshBacktestResults",
    'status: "loading_result"',
    'activateBacktestView("results")',
    'is-indeterminate',
):
    require(JS, marker)

for marker in (
    ".task-mode-overview",
    ".task-directory-item",
    ".task-progress-shell",
    ".task-progress-track",
    ".task-status-badge",
    ".task-selection-panel",
    ".results-context-panel",
    ".technical-details",
    "@keyframes task-progress-slide",
):
    require(CSS, marker)

require(HTML, "<details class=\"technical-details\">")
print("Stage 68 backtest task workflow UI smoke passed")
