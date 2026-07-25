"""Static acceptance checks for the Stage 74 professional report workspace."""

from __future__ import annotations

from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    root = ensure_project_root_on_sys_path()
    app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
    index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
    styles = (root / "web" / "styles.css").read_text(encoding="utf-8")
    api = (root / "app" / "api" / "reporting.py").read_text(encoding="utf-8")

    required_ids = ("mode-report-tabs", "independent-report-run-toolbar", "independent-report-run-search", "independent-report-run-select", "mode-report-radar")
    if any(f'id="{item}"' not in index_html for item in required_ids):
        raise SystemExit("stage74 workspace smoke failed: report workspace controls missing")
    required_functions = ("renderIndependentTaskStatistics", "loadIndependentModeSingleRun", "renderSharedModeReport", "setModeReportTab")
    if any(f"function {item}" not in app_js for item in required_functions):
        raise SystemExit("stage74 workspace smoke failed: report workspace behavior missing")
    if "buildSevenDimensionReport" in app_js or "演示 3.98%" in app_js:
        raise SystemExit("stage74 workspace smoke failed: demo fallback remains")
    if "?? Run" in app_js or "${labels[index]}?${count} ?" in app_js:
        raise SystemExit("stage74 workspace smoke failed: question-mark mojibake remains")
    if "independent-screening/{task_id}/runs/{run_id}" not in api:
        raise SystemExit("stage74 workspace smoke failed: independent run report route missing")
    if ".mode-report-tabs button.is-selected" not in styles or ".independent-report-run-toolbar" not in styles:
        raise SystemExit("stage74 workspace smoke failed: PC workspace selection styles missing")
    for path, content in (("app.js", app_js), ("index.html", index_html), ("styles.css", styles), ("reporting.py", api)):
        if "\ufffd" in content:
            raise SystemExit(f"stage74 workspace smoke failed: replacement character found in {path}")
    print("stage74 professional report workspace smoke test passed")


if __name__ == "__main__":
    main()