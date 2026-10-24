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
    assert 'dc-sidebar-subnav' in html
    assert "数据源配置" in html and "源路由配置" in html
    assert 'id="dc-sync-dataset-tree"' in html
    assert 'id="dc-sync-shards"' in html
    assert 'id="dc-disposition-form"' in script
    assert "/api/data-center/quality/summary" in script
    assert "/api/data-center/quality/issues/bulk/disposition" in script
    assert "/api/data-center/quality/issues/bulk/refetch" in script
    assert 'id="dc-quality-bulk"' in html
    assert 'data-quality-select-all' in script and 'role="checkbox"' in script
    assert '记录为不可用（不改数据）' in html and '重拉并自动生效' in html
    assert 'data-quality-bulk="correct"' in html
    assert '/api/data-center/quality/issues/bulk/correct' in script
    assert 'dc-quality-bulk-help' in html and 'updateQualityBulkState' in script
    assert 'name="date_from"' in html and 'name="date_to"' in html
    assert "selectedIssues" in script and "bulkQuality" in script
    assert "window.prompt" not in script
    assert 'data-vtable-mode="governance"' in script
    assert "@media(max-width:741px)" in styles
    assert "/data_center.css?v=925" in html
    assert "/data_center_stage_c.js?v=926" in html
    assert 'id="dc-source-probe-dialog"' in html
    assert "错误码与处理" in script and "常见原因" in script and "处理方法" in script
    assert "UPSTREAM_TIMEOUT" in script and "HOST_NOT_ALLOWED" in script
    assert 'id="dc-route-dialog"' in html and 'id="dc-route-test-dialog"' in html
    assert 'id="dc-route-check"' in html and ">检查配置<" in html
    assert 'id="dc-route-test"' in html and ">连接测试<" in html
    assert 'id="dc-route-live"' not in html
    assert 'id="dc-route-save"' in html and "应用当前配置" in html
    assert 'id="dc-routes-save"' not in html and 'id="dc-route-output"' not in html
    assert 'data-route-row' in script and 'data-vtable-row-action="true"' in script
    assert "backoff_seconds" in script and "isCompatibleRouteSource" in script
    assert 'result.status==="policy_blocked"' in script
    assert "preview_token" in script and "selected_shards" in script
    assert 'data-quality-scan-pause' in script and 'data-quality-scan-resume' in script and 'data-quality-scan-stop' in script
    assert 'history.hidden=mode!=="historical_gap"' in script and 'coverage_strategy' in script
    assert "当前有效数据" in script and "历史记录" in script
    assert 'id="dc-version-default"' in html and 'id="dc-version-latest"' in html
    assert "dc-global-status" in html
    assert "Stage 86 design-v1 information architecture" in styles
    assert '<h4>专项任务记录</h4>' in html and 'id="dc-maintenance-form"' in html
    assert 'class="dc-sync-create-column"' in html
    assert 'class="dc-surface dc-sync-preview-surface"' in html
    assert 'id="dc-sync-task-dialog"' in html
    assert "taskDuration" in script and "refreshTaskDurations" in script
    assert "taskModeLabel" in script and "数据中心同步" in script
    assert 'class="dc-quality-flow-guide"' in html
    assert "Data-center task workspace readability refresh" in styles
    assert 'data-task-delete' in script and 'method:"DELETE"' in script
    assert "deleteSyncTask" in script and "dc-danger-button" in styles
    assert "taskResolutionHtml" in script and "retryFailedTask" in script
    assert "data-task-detail-retry" in script and "data-task-open-routes" in script
    assert ".dc-task-resolution" in styles and ".dc-error-groups" in styles
    assert "--q-primary" in styles and "--q-border" in styles
    for breakpoint in ("1280px", "1024px", "768px", "480px"):
        assert f"max-width:{breakpoint}" in styles

    print("stage86 + stage-C data-center UI smoke passed")


if __name__ == "__main__":
    main()
