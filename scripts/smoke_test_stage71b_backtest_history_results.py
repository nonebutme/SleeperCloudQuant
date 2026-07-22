"""Static/runtime smoke checks for Stage 71B backtest history and result fixes."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
JS = (ROOT / "web/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web/styles.css").read_text(encoding="utf-8")

def require(value, message):
    if not value: raise AssertionError(message)

require("/api/backtest/runs" in JS and "loadSingleRunHistory" in JS, "single-stock history contract missing")
require("is-selected" in JS and "currentScreeningTaskId" in JS, "selected task highlight contract missing")
require("result.has_next" in JS and "new Blob" in JS and "window.alert" in JS, "pagination/export contract missing")
for label in [r"\u8dcc\u505c", "-8%-", "-8~-6%", "-6~-4%", "-4~-2%", "-2~0%", "0~2%", "2~4%", "4~6%", "6~8%", "8%+", r"\u6da8\u505c"]:
    require(label in JS, f"return bucket missing: {label}")
require("currentIndustrySortMode" in JS and "industry-sort-toggle" in JS, "industry sorting contract missing")
require("/api/reporting/ai-workflows/" in JS and "/api/reporting/report-packages/" in JS, "reporting delete route contract missing")
require("configureReportingWorkspace" in JS and "reporting-section-nav" in JS, "reporting workspace navigation contract missing")
require("start_date" in JS and "end_date" in JS and "adjustment" in JS and "qfq" in JS, "query defaults contract missing")
require('["strategy", "single", "independent", "portfolio", "research"]' in JS, "strategy tab order missing")
require("is-selected" in CSS and "return-distribution-chart" in CSS, "stage 71B styles missing")
print("Stage 71B history/result smoke passed")
