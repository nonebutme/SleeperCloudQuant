"""Deterministic coverage for controlled-source connection-test semantics."""

from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from app.services.data_center_service import DataCenterService
from data_platform.storage.data_center_store import DataCenterStore


class _Frame:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def to_dict(self, orient: str) -> list[dict]:
        assert orient == "records"
        return list(self.rows)


class _GovernanceProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _rows(self, name: str) -> list[dict]:
        self.calls.append(name)
        return [{"source_call": name}]

    def list_symbols(self) -> list[dict]:
        return self._rows("list_symbols")

    def fetch_daily_prices(self, **_kwargs) -> list[dict]:
        return self._rows("fetch_daily_prices")

    def fetch_trade_calendar(self, **_kwargs) -> list[dict]:
        return self._rows("fetch_trade_calendar")

    def fetch_index_daily_prices(self, **_kwargs) -> list[dict]:
        return self._rows("fetch_index_daily_prices")

    def fetch_global_index_daily_prices(self, **_kwargs) -> list[dict]:
        return self._rows("fetch_global_index_daily_prices")

    def fetch_corporate_actions(self, **_kwargs) -> list[dict]:
        return self._rows("fetch_corporate_actions")

    def fetch_index_component_snapshot(self, **_kwargs) -> dict:
        self.calls.append("fetch_index_component_snapshot")
        return {"rows": [{"symbol": "000001"}]}

    def fetch_security_lifecycle_events(self, **_kwargs) -> list[dict]:
        return self._rows("fetch_security_lifecycle_events")


class _ThsProvider:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def fetch_catalog(self, dimension: str) -> list[dict]:
        self.calls.append(f"ths_catalog:{dimension}")
        return [{"board_code": "881001", "board_name": f"{dimension}-sample"}]

    def fetch_index(self, dimension: str, **_kwargs) -> _Frame:
        self.calls.append(f"ths_index:{dimension}")
        return _Frame([{"date": "2026-01-05"}])


class _CninfoProvider:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def fetch_industry_categories(self) -> list[dict]:
        self.calls.append("cninfo_categories")
        return [{"category_code": "A", "category_name": "sample"}]

    def fetch_industry_intervals(self, *_args) -> list[dict]:
        self.calls.append("cninfo_intervals")
        return [{"symbol": "000001", "category": "sample"}]

    def fetch_share_changes(self, *_args) -> list[dict]:
        raise AssertionError("disabled CNInfo share-change capability was called")

    def fetch_announcements(self, *_args) -> list[dict]:
        raise AssertionError("disabled CNInfo announcement capability was called")


class _Panorama:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.industry_flow_attempts = 0
        self.ths_board_provider = _ThsProvider(self.calls)
        self.cninfo_provider = _CninfoProvider(self.calls)

    def _fetch_catalog_curl(self, dimension: str) -> list[dict]:
        self.calls.append(f"eastmoney_catalog:{dimension}")
        return [{"board_code": "BK001", "board_name": f"{dimension}-sample"}]

    def _fetch_board_daily_range(
        self, dimension: str, _item: dict, _start_date: str, _end_date: str,
        *, allow_fallback: bool = True,
    ) -> list[dict]:
        assert not allow_fallback
        self.calls.append(f"eastmoney_board:{dimension}")
        return [{"trade_date": "2026-01-05", "source": f"eastmoney.{dimension}_board_kline_curl"}]

    def _fetch_fund_flow(self, dimension: str, _item: dict, _end_date: str) -> list[dict]:
        self.calls.append(f"eastmoney_flow:{dimension}")
        if dimension == "industry":
            self.industry_flow_attempts += 1
            if self.industry_flow_attempts == 1:
                raise RuntimeError("curl transport failed (56): peer reset")
        return [{"trade_date": "2026-01-05"}]

    def _fetch_events(self, *_args, **_kwargs) -> list[dict]:
        self.calls.append("eastmoney_events")
        return [{"event_date": "2026-01-05"}]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="scq-source-probes-") as temporary:
        database = Path(temporary) / "market.sqlite3"
        store = DataCenterStore(database)
        store.ensure_schema()
        governance = _GovernanceProvider()
        panorama = _Panorama()
        service = object.__new__(DataCenterService)
        service.store = store
        service.scheduler = SimpleNamespace(governance_provider=governance)
        service.panorama_service = panorama

        verified_results = {
            source_id: service.test_source(source_id, live=True)
            for source_id in ("akshare", "akshare_ths", "cninfo")
        }
        assert all(result["status"] == "passed" for result in verified_results.values())
        assert verified_results["akshare"]["active_tested_count"] == 13
        assert verified_results["akshare"]["skipped_count"] in {3, 4}
        assert verified_results["akshare_ths"]["active_tested_count"] == 3
        assert verified_results["akshare_ths"]["skipped_count"] == 1
        assert verified_results["cninfo"]["active_tested_count"] == 3
        assert verified_results["cninfo"]["skipped_count"] == 2
        retried = next(
            item for item in verified_results["akshare"]["items"]
            if item["endpoint_id"] == "stock_board_industry_fund_flow_hist"
        )
        assert retried["status"] == "passed"
        assert retried["evidence"]["attempts"] == 2
        assert len(retried["evidence"]["previous_errors"]) == 1
        global_probes = [
            item for item in verified_results["akshare"]["items"]
            if item["dataset_id"] == "global_index_daily"
            and item["status"] == "passed"
        ]
        assert {item["endpoint_id"] for item in global_probes} == {
            "index_us_stock_sina", "index_global_hist_sina",
        }

        ths_mismatch = next(
            item for item in store.get_source("akshare_ths")["capabilities"]
            if item["endpoint_id"] == "stock_board_industry_name_ths"
        )
        assert not ths_mismatch["enabled"]
        assert ths_mismatch["verification_status"] == "rejected"

        repair_route = store.get_route("industry-classification-repair")
        assert repair_route["source_id"] == "cninfo"
        assert repair_route["endpoint"] == "stock_industry_change_cninfo"
        repair_probe = next(
            item for item in verified_results["cninfo"]["items"]
            if item["route_id"] == "industry-classification-repair"
        )
        assert repair_probe["status"] == "passed"
        assert "cninfo_intervals" in panorama.calls

        candidate_results = {
            source_id: service.test_source(source_id, live=True)
            for source_id in (
                "baostock", "mootdx", "tencent_finance", "iwencai",
                "eastmoney_reportapi", "a_stock_data",
            )
        }
        assert all(result["status"] == "policy_blocked" for result in candidate_results.values())
        assert {
            item["error_code"]
            for result in candidate_results.values()
            for item in result["items"]
        } == {"SOURCE_NOT_VERIFIED", "NO_TESTABLE_CAPABILITY"}

        disabled_route = service.test_route("financial-statements", live=True)
        assert disabled_route["status"] == "policy_blocked"
        assert disabled_route["error_code"] == "CAPABILITY_DISABLED"
        assert "fetch_share_changes" not in panorama.calls
        assert "fetch_announcements" not in panorama.calls

        global_route = store.get_route("global-index-daily")
        assert not global_route["enabled"]
        assert store.get_route("global-index-us-sina")["enabled"]
        assert store.get_route("global-index-international-sina")["enabled"]
        try:
            store.update_routes([{"route_id": "global-index-daily", "enabled": True}])
        except ValueError as error:
            assert "enabled verified source capability" in str(error)
        else:
            raise AssertionError("disabled capability must not produce an enabled route")

        expected_probe_count = sum(
            result["tested_count"]
            for result in [*verified_results.values(), *candidate_results.values()]
        ) + 1
        with closing(sqlite3.connect(database)) as connection:
            actual_probe_count = connection.execute(
                "SELECT COUNT(*) FROM data_source_probes"
            ).fetchone()[0]
        assert actual_probe_count == expected_probe_count

    print("[source-probes] controlled connection semantics smoke passed")


if __name__ == "__main__":
    main()
