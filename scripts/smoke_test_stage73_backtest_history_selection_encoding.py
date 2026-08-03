"""Static smoke checks for Stage 73 backtest history, selection and encoding fixes."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "web/index.html").read_text(encoding="utf-8")
JS = (ROOT / "web/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/styles.css").read_text(encoding="utf-8")

def require(value, message):
    if not value:
        raise AssertionError(message)

require('id="single-run-history"' in HTML and 'id="single-run-history-refresh"' in HTML, "single-stock history panel missing")
require("loadSingleRunHistory().catch" in JS, "single-stock history initial loading missing")
require("screening_task_id" in JS and "shared_cash_portfolio" in JS, "single-stock history mode filtering missing")
require("loadIndependentScreeningResultWorkspace" in JS, "independent result workspace missing")
require("entered_only=true&limit=100" in JS and "data-independent-result-run" in JS, "entered-stock result selector missing")
require("await loadBacktestResultPanel(selectedRunId)" in JS, "independent result detail auto-loading missing")
require('document.querySelectorAll("[data-ai-workflow]")' in JS, "AI workflow selected state missing")
require('document.querySelectorAll("[data-report-package]")' in JS, "report package selected state missing")
require('document.querySelectorAll("[data-report-package-directory]")' in JS, "report package directory selected state missing")
require("background: #eef5fb" in CSS and "independent-result-run-list button.is-selected" in CSS, "pale selected background missing")
require("???" not in JS and "\ufffd" not in JS + HTML + CSS, "mojibake marker remains")
asset_versions = dict(
    re.findall(r"/(styles\.css|app\.js|report-ui\.css|report-ui\.js)\?v=(\d+)", HTML)
)
require(
    {"styles.css", "app.js", "report-ui.css", "report-ui.js"} <= asset_versions.keys(),
    "static cache version missing",
)
require(
    asset_versions["report-ui.css"]
    == asset_versions["report-ui.js"]
    == asset_versions["app.js"]
    and int(asset_versions["app.js"]) >= int(asset_versions["styles.css"]),
    "static cache versions are inconsistent",
)
print("Stage 73 history/selection/encoding smoke passed")
