"""Isolated contracts for the bounded AKShare/THS board adapter."""

from __future__ import annotations

from types import ModuleType

import pandas as pd

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.providers.akshare_ths_board_provider import AkshareThsBoardProvider


class _FakeRequests:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def get(self, *_args, **kwargs):
        self.timeouts.append(float(kwargs["timeout"]))
        return object()


def main() -> None:
    module = ModuleType("fake_ths_concept")
    requests = _FakeRequests()
    module.requests = requests

    def original_map_loader():
        raise AssertionError("the upstream name-map loader must be replaced by the cached map")

    module._get_stock_board_concept_name_ths = original_map_loader

    def fetch_names():
        module.requests.get("https://example.invalid/names")
        return pd.DataFrame([{"name": "AI PC", "code": "309121"}])

    def fetch_index(*, symbol: str, start_date: str, end_date: str):
        mapping = module._get_stock_board_concept_name_ths()
        module.requests.get("https://example.invalid/index")
        assert mapping == {"AI PC": "309121"}
        assert symbol == "AI PC"
        assert (start_date, end_date) == ("20260701", "20260724")
        return pd.DataFrame([{"日期": "2026-07-24", "收盘价": 1.0}])

    module.stock_board_concept_name_ths = fetch_names
    module.stock_board_concept_index_ths = fetch_index

    provider = AkshareThsBoardProvider(
        request_timeout_seconds=7,
        module_loader=lambda _name: module,
    )
    assert provider.fetch_catalog("concept") == [
        {"board_code": "309121", "board_name": "AI PC"}
    ]
    frame = provider.fetch_index(
        "concept",
        board_name="AI PC",
        board_code="BK001",
        start_date="20260701",
        end_date="20260724",
    )
    assert len(frame) == 1
    assert requests.timeouts == [7.0, 7.0]
    assert module.requests is requests
    assert module._get_stock_board_concept_name_ths is original_map_loader

    try:
        provider.fetch_catalog("unsupported")
    except ValueError as error:
        assert "unsupported THS board dimension" in str(error)
    else:
        raise AssertionError("unsupported dimensions must fail closed")

    print("AKShare THS board provider smoke passed")


if __name__ == "__main__":
    main()
