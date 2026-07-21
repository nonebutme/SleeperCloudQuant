"""Smoke test for stage 23 real-provider entry gates and safe fallback."""

from __future__ import annotations

import json
import os

from _project_bootstrap import ensure_project_root_on_sys_path


def main() -> None:
    ensure_project_root_on_sys_path()

    for key in ("SCQ_MARKET_PROVIDER_BASE_URL", "SCQ_MARKET_PROVIDER_API_KEY"):
        os.environ.pop(key, None)

    from app.runtime import build_demo_app, dispatch_request
    from backtest_kernel import RqalphaPackageRuntime
    from data_platform import ExternalMarketProviderRepository

    external = ExternalMarketProviderRepository()
    status = external.provider_status()
    if status.get("enabled") or status.get("status") != "fallback_to_local_sqlite":
        raise SystemExit("stage23 smoke failed: external market provider should fallback without env")
    if "SCQ_MARKET_PROVIDER_BASE_URL" not in status.get("missing", []) or "SCQ_MARKET_PROVIDER_API_KEY" not in status.get("missing", []):
        raise SystemExit("stage23 smoke failed: missing market provider env vars not reported")
    if external.fetch_price_history("000001.XSHE", "2020-01-02", "2020-01-10"):
        raise SystemExit("stage23 smoke failed: unconfigured external provider should not return rows")

    draft_configured = ExternalMarketProviderRepository(
        base_url="https://market.example/api",
        provider_name="stage24-configured-provider",
        timeout_seconds=12,
        enabled=True,
    ).provider_status()
    if draft_configured.get("enabled") or not draft_configured.get("base_url_configured") or draft_configured.get("api_key_configured"):
        raise SystemExit("stage24 smoke failed: public provider draft should require env API key")
    if draft_configured.get("status") != "fallback_to_local_sqlite" or "SCQ_MARKET_PROVIDER_API_KEY" not in draft_configured.get("missing", []):
        raise SystemExit("stage24 smoke failed: public provider draft fallback status mismatch")

    probe = RqalphaPackageRuntime.probe_status()
    if probe.get("provider") != "rqalpha" or probe.get("status") not in {"package_missing", "package_detected", "import_failed"}:
        raise SystemExit("stage23 smoke failed: rqalpha probe status invalid")

    from app.runtime.demo_registry import _build_market_repository
    from backtest_kernel import LocalSQLiteBacktestRuntime

    direct_runtime = RqalphaPackageRuntime(LocalSQLiteBacktestRuntime(_build_market_repository()))
    direct_result = direct_runtime.run(
        {
            "run_id": "stage23-direct-runtime-probe",
            "strategy_name": "moving_average_strategy",
            "symbol": "000001.XSHE",
            "start_date": "2020-01-02",
            "end_date": "2020-06-30",
            "benchmark": "000300.XSHG",
            "parameters": {"symbol": "000001.XSHE", "short_window": 3, "long_window": 5, "position_size": 1.0},
        }
    )
    if direct_result.get("raw_result", {}).get("engine_probe", {}).get("provider") != "rqalpha":
        raise SystemExit("stage23 smoke failed: direct runtime probe trace missing")

    app = build_demo_app()
    status_code, config_payload = dispatch_request(
        app,
        method="POST",
        path="/api/config/runtime-draft",
        body=json.dumps(
            {
                "settings": {
                    "market_provider": {
                        "enabled": True,
                        "provider_name": "stage24-configured-provider",
                        "base_url": "https://market.example/api",
                        "timeout_seconds": 12,
                        "api_key": "must-not-be-persisted",
                    },
                    "rqalpha_runtime": {"execution_mode": "probe_then_local_fallback", "prefer_real_package": False},
                }
            }
        ).encode("utf-8"),
    )
    if status_code != 200 or "api_key" in json.dumps(config_payload, ensure_ascii=False):
        raise SystemExit("stage24 smoke failed: config draft leaked market provider API key")
    status_code, config_payload = dispatch_request(app, method="GET", path="/api/config/status")
    config_status = config_payload.get("status", {})
    market_status = config_status.get("market_provider_status", {})
    if status_code != 200 or market_status.get("provider") != "stage24-configured-provider" or not market_status.get("base_url_configured"):
        raise SystemExit("stage24 smoke failed: market provider public config not visible")
    if market_status.get("enabled") or market_status.get("api_key_configured"):
        raise SystemExit("stage24 smoke failed: market provider should wait for env API key")
    if not config_status.get("rqalpha_runtime_status") or not config_status.get("runtime_settings", {}).get("rqalpha_runtime", {}).get("local_capabilities"):
        raise SystemExit("stage24 smoke failed: rqalpha runtime local capabilities missing")

    run_id = "stage23-real-provider-entry-smoke"
    request = {
        "run_id": run_id,
        "strategy_name": "moving_average_strategy",
        "strategy_id": "moving_average_strategy",
        "strategy_version": "v1",
        "symbol": "000001.XSHE",
        "benchmark": "000300.XSHG",
        "start_date": "2020-01-02",
        "end_date": "2020-06-30",
        "parameters": {"short_window": 3, "long_window": 5, "position_size": 1.0},
        "extra_config": {"runtime_mode": "rqalpha_package_probe"},
    }
    status_code, payload = dispatch_request(app, method="POST", path="/api/backtest/run-once", body=json.dumps(request).encode("utf-8"))
    result = payload.get("result", {})
    if status_code != 200 or result.get("status") != "completed":
        raise SystemExit("stage23 smoke failed: backtest should complete through fallback runtime")

    detail_status, detail_payload = dispatch_request(app, method="GET", path=f"/api/reporting/run-detail/{run_id}")
    detail = detail_payload.get("detail", {})
    if detail_status != 200 or not detail.get("account_value_chart"):
        raise SystemExit("stage23 smoke failed: report detail missing after rqalpha probe run")

    if not detail.get("trade_activity_chart"):
        raise SystemExit("stage23 smoke failed: report trade chart missing after rqalpha probe run")

    print("stage23 real provider entry smoke test passed")


if __name__ == "__main__":
    main()


