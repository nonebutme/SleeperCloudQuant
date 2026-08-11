"""Backend contract checks for the strategy Dataset catalog."""

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.api.strategy_datasets import build_strategy_dataset_routes
from app.main import SimpleApiApp
from app.runtime.http_adapter import dispatch_request
from app.services.strategy_dataset_service import StrategyDatasetService
from app.services.strategy_dataset_validation import validate_strategy_data_contract
from backtest_kernel.strategy_execution import execute_target_weights
from data_platform.data_center_catalog import DATASET_CATALOG


class _Catalog:
    def list_datasets(self):
        return list(DATASET_CATALOG)

    def list_routes(self):
        return [{"dataset_id": "a_share_daily", "source_id": "akshare", "enabled": True}]

    def get_source(self, source_id):
        return {"source_id": source_id, "display_name": "AKShare", "upstream_name": "public sources"}

    def list_versions(self):
        version = {
            "data_version_id": "dv-test", "status": "published",
            "as_of_trade_date": "2026-07-24", "quality_report_id": "qr-test",
        }
        return {"default_version_id": "dv-test", "default_version": version}

    def list_assets(self, *, version_id=""):
        return {"version_id": version_id, "items": [{
            "dataset": "a_share_daily", "adjustment": "qfq",
            "coverage_start": "2015-01-05", "coverage_end": "2026-07-24",
            "symbol_count": 5528, "row_count": 10000,
        }]}


def main() -> None:
    service = StrategyDatasetService(_Catalog())
    listing = service.list_products(consumer_scope="strategy")
    assert listing["summary"]["strategy_ready"] == 6
    assert listing["summary"]["template_only"] >= 5
    assert all(item["example_count"] == 3 for item in listing["items"])
    assert {item["dataset_id"] for item in listing["items"]} >= {
        "a_share_daily", "trade_calendar", "corporate_actions",
    }
    detail = service.get_product("a_share_daily")
    assert detail["schema_status"] == "available"
    assert detail["published_version"]["version_id"] == "dv-test"
    assert {item["kind"] for item in detail["examples"]} == {
        "getting_started", "research", "strategy",
    }
    instantiated = service.instantiate_example("a_share_daily", "a_share_daily-strategy")
    assert instantiated["validation"]["ok"] is True
    assert instantiated["strategy_draft"]["runtime_status"] == "executable"
    assert instantiated["writes"] == 0
    contract = validate_strategy_data_contract(instantiated["strategy_draft"]["source_code"])
    assert contract["ok"] is True
    bars = [
        {"trade_date": f"2026-01-{index + 1:02d}", "close": 10.0 + index}
        for index in range(25)
    ]
    commented_source = "# 中文策略注释：验证 Windows 子进程统一使用 UTF-8。\n" + instantiated["strategy_draft"]["source_code"]
    weights = execute_target_weights(
        commented_source, bars,
        instantiated["strategy_draft"]["parameters"],
    )
    assert len(weights) == len(bars)
    assert weights[-1] == 1.0

    app = SimpleApiApp("test", build_strategy_dataset_routes(service))
    status, payload = dispatch_request(
        app, method="GET", path="/api/strategy-datasets",
        query_string="layer_id=L1&consumer_scope=strategy",
    )
    assert status == 200
    assert payload["items"][0]["dataset_id"] == "a_share_daily"
    status, payload = dispatch_request(
        app, method="POST",
        path="/api/strategy-datasets/a_share_daily/examples/a_share_daily-strategy/instantiate",
        body=b"{}",
    )
    assert status == 200
    assert payload["result"]["validation"]["ok"] is True
    print("[strategy-datasets] passed")


if __name__ == "__main__":
    main()
