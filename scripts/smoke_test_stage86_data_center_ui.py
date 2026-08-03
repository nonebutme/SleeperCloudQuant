"""Static contract checks for the stage-86 baseline plus stage-C data-center upgrade."""

from __future__ import annotations

from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    script = (root / "web" / "data_center_stage_c.js").read_text(encoding="utf-8")
    styles = (root / "web" / "data_center.css").read_text(encoding="utf-8")

    for view in ("overview", "routes", "sync", "quality", "assets", "versions"):
        assert f'data-dc-view="{view}"' in html
        assert f'id="dc-view-{view}"' in html
    for path in (
        "/api/data-center/overview", "/api/data-center/sources",
        "/api/data-center/datasets", "/api/data-center/routes",
        "/api/data-center/sync/preview", "/api/data-center/sync/tasks",
        "/api/data-center/quality/issues", "/api/data-center/versions",
    ):
        assert path in script
    assert "快捷追更" in html and "历史缺口修复" in html
    assert 'name="start_trade_date"' in html and 'id="dc-sync-latest"' in html
    assert 'id="dc-quality-dataset"' in html and 'id="dc-quality-source"' in html
    assert 'id="dc-quality-rule"' in html and 'id="dc-quality-task"' in html
    assert "/api/data-center/quality/filter-options" in script
    assert "NONCOMMERCIAL LOCAL RESEARCH" in html
    assert 'class="dc-sidebar-subnav"' in html
    assert "数据源配置" in html and "源路由配置" in html
    assert 'id="dc-sync-dataset-tree"' in html
    assert 'id="dc-sync-shards"' in html
    assert 'id="dc-disposition-form"' in script
    assert "/api/data-center/quality/summary" in script
    assert "/api/data-center/quality/issues/bulk/disposition" in script
    assert "/api/data-center/quality/issues/bulk/refetch" in script
    assert 'id="dc-quality-bulk"' in html
    assert 'data-quality-select-all' in script and 'role="checkbox"' in script
    assert '记录为不可用（不改数据）' in html and '生成修复任务' in html
    assert 'dc-quality-bulk-help' in html and 'updateQualityBulkState' in script
    assert 'name="date_from"' in html and 'name="date_to"' in html
    assert "selectedIssues" in script and "bulkQuality" in script
    assert "window.prompt" not in script
    assert 'data-vtable-mode="governance"' in script
    assert "@media(max-width:741px)" in styles
    assert "/data_center.css?v=879" in html
    assert "/data_center_stage_c.js?v=880" in html
    assert "preview_token" in script and "selected_shards" in script
    assert 'data-quality-scan-pause' in script and 'data-quality-scan-resume' in script and 'data-quality-scan-stop' in script
    assert 'history.hidden=mode!=="historical_gap"' in script and 'coverage_strategy' in script
    assert "当前默认研究版本" in script and "最新已发布版本" in script
    assert 'id="dc-version-default"' in html and 'id="dc-version-latest"' in html
    assert "dc-global-status" in html
    assert "Stage 86 design-v1 information architecture" in styles
    assert '<h4>任务列表</h4>' in html
    assert 'class="dc-sync-create-column"' in html
    assert 'class="dc-surface dc-sync-preview-surface"' in html
    assert 'id="dc-sync-task-dialog"' in html
    assert "taskDuration" in script and "refreshTaskDurations" in script
    assert "taskModeLabel" in script and "数据中心同步" in script
    assert 'class="dc-quality-flow-guide"' in html
    assert "Data-center task workspace readability refresh" in styles
    assert 'data-task-delete' in script and 'method:"DELETE"' in script
    assert "deleteSyncTask" in script and "dc-danger-button" in styles
    assert "--q-primary" in styles and "--q-border" in styles
    for breakpoint in ("1280px", "1024px", "768px", "480px"):
        assert f"max-width:{breakpoint}" in styles

    print("stage86 + stage-C data-center UI smoke passed")


if __name__ == "__main__":
    main()
