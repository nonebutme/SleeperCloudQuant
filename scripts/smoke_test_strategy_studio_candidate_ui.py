"""Canonical static contract checks for the Strategy Studio candidate UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    html = (ROOT / "web" / "strategy-studio.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "strategy-studio.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "web" / "strategy-studio.css").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "run_strategy_studio_web_demo.py").read_text(encoding="utf-8")

    sections = ("overview", "datasets", "signals", "portfolio", "risk", "execution", "code", "validation")
    assert all(f'id="{section}"' in html for section in sections)
    assert 'href="/?page=backtest"' in html
    assert 'data-vtable-mode="edit"' in html
    assert '/vendor/vtable/vtable.min.js' in html and '/vtable-adapter.js' in html
    assert '/api/datasets' in script and '/api/strategy-studio/manifests' in script
    assert 'crypto.subtle.digest("SHA-256"' in script
    assert "point_in_time_required: true" in script
    assert "version_policy: \"latest_published\"" in script
    assert "strategy studio" in runner.lower()
    assert "build_strategy_studio_app" in runner
    assert "@media (max-width: 700px)" in stylesheet
    assert "--q-primary" in stylesheet
    print("[strategy-studio-candidate-ui] passed")


if __name__ == "__main__":
    main()
