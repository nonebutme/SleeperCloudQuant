"""Stage 76 unified strategy-task-result-report workspace smoke test."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.backtest import _mode_task_entry
from app.services.single_backtest_task_service import SingleBacktestTaskService


@dataclass
class _Status:
    value: str = "completed"


@dataclass
class _Result:
    run_id: str
    strategy_name: str = "moving_average_strategy"
    status: _Status = field(default_factory=_Status)
    metrics: dict = None

    def __post_init__(self) -> None:
        self.metrics = self.metrics or {"total_returns": 0.01}


class _BacktestService:
    def run_once(self, request):
        return _Result(run_id=request.run_id)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
    css = (root / "web" / "styles.css").read_text(encoding="utf-8")
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    for marker in [
        "configureStage76InformationArchitecture",
        "策略工作台",
        "创建回测任务",
        "任务工作台",
        "submitSingleBacktestTask",
        "loadStage76Tasks",
        "capabilities",
        "stage76-result-tabs",
        "renderStage76ResultDetails",
        "loadStage76EmbeddedReport",
        "单股择时报告",
        "全市场普查报告",
        "多票组合报告",
        "仅支持相同回测模式的 Run 对比",
        "oldTabs.remove()",
        'const editorMeta = $("#strategy-editor-meta")',
        'const stage76Validation = $("#strategy-validation-output")',
        "strategy-library-sort",
        "stage76TaskPageSize",
        "stage76-task-table-header",
        "stage76-retired-result-technical",
        'action==="result" || action==="report"',
        "configureStage76ModeForm",
        "syncStage76CommonFields",
        "setStage76ModeTaskState",
        "stage76-form-actions",
        "stage76-common-duplicate",
        "configureStage76CodeEditor",
        "highlightStage76Python",
        "stage76-code-theme",
        "currentSingleTask",
        "回测编号（自动生成）",
        "const runId=newTaskId(\"single-run\")",
        "策略代码编写指南",
        "拖动右下角手柄调整高度",
        "strategy-version-select",
        "legacyVersionSection",
        "versionSelectorBlock.append(versionHistory)",
        "stage76-code-resize-handle",
        "stage76-sidebar-subnav",
        'data-stage76-form-action="result"',
        'data-stage76-form-action="report"',
        '"function-call"',
    ]:
        assert marker in app_js, marker
    assert '$("#screening-task-list")?.closest(".panel")' not in app_js
    assert '$("#portfolio-task-list")?.closest(".panel")' not in app_js
    assert "stage76-open-full-report" not in app_js
    assert "inspector.append(guideBlock)" not in app_js
    assert "const [detail, entered] = await Promise.all" not in app_js
    assert "renderScreeningEnteredResults(entered.result?.items || [])" not in app_js
    assert app_js.index("[editorHeader, fields, actions, parameterSection]") < app_js.index("inspector.append(versionSelectorBlock)")
    assert 'if(task.mode==="single") { activatePage("reporting")' not in app_js
    for marker in [".stage76-workspace-nav", ".stage76-task-row", ".stage76-result-tabs", ".stage76-report-hero", ".stage76-task-pager", "Stage 76.2 PC density", "Stage 76.3 unified forms", ".stage76-mode-form", ".stage76-mode-task-state", "Stage 76.4 strategy editor", ".stage76-code-editor-shell", "Stage 76.5 compact current-task strip", "Stage 76.6 strategy guide", "Stage 76.7 restored version selector", "Stage 76.9 sidebar workspace navigation"]:
        assert marker in css, marker
    assert "/app.js?v=769" in html and "/styles.css?v=769" in html

    with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        service = SingleBacktestTaskService(_BacktestService(), Path(temp_dir) / "single.sqlite3")
        task = service.create_task(
            task_id="stage76-single-smoke",
            run_id="stage76-single-smoke-run",
            strategy_name="moving_average_strategy",
            strategy_id="moving_average_strategy",
            strategy_version="v1",
            symbol="000001.XSHE",
            benchmark="000300.XSHG",
            start_date="2020-01-02",
            end_date="2020-01-10",
            adjustment="qfq",
        )
        assert task["status"] == "ready"
        completed = service.start_task(task["task_id"], wait=True)
        assert completed["status"] == "completed"
        normalized = _mode_task_entry("single", completed)
        assert normalized["mode"] == "single"
        assert normalized["capabilities"]["can_view_result"] is True
        assert normalized["capabilities"]["can_delete"] is True
        assert normalized["links"]["result"].endswith("/panel")
    print("stage76 unified backtest workspace smoke passed")


if __name__ == "__main__":
    main()
