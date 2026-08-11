"""Static contract checks for the standalone Strategy Studio candidate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    html = (ROOT / "web" / "strategy-studio.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "strategy-studio.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "web" / "strategy-studio.css").read_text(encoding="utf-8")
    runner = (ROOT / "scripts" / "run_strategy_studio_web_demo.py").read_text(encoding="utf-8")

    for section in ("overview", "datasets", "signals", "portfolio", "risk", "execution", "code", "validation"):
        assert f'id="{section}"' in html
    assert 'href="/?page=backtest"' in html
    assert 'data-vtable-mode="edit"' in html
    assert '/vendor/vtable/vtable.min.js' in html
    assert '/vtable-adapter.js' in html
    assert '/api/datasets' in script
    assert '/api/strategy-studio/manifests' in script
    assert 'crypto.subtle.digest("SHA-256"' in script
    assert "point_in_time_required: true" in script
    assert "version_policy: \"latest_published\"" in script
    assert "strategy studio" in runner.lower()
    assert "build_strategy_studio_app" in runner
    assert "@media (max-width: 700px)" in stylesheet
    assert "--q-primary" in stylesheet
    print("[strategy-studio-ui] passed")


if __name__ == "__main__":
    main()
