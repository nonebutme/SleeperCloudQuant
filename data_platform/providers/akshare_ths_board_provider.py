"""Bounded AKShare/THS board adapter with per-task catalog reuse."""

from __future__ import annotations

import importlib
import re
import threading
from collections.abc import Callable
from types import ModuleType
from typing import Any


_DIMENSION_CONFIG = {
    "industry": (
        "akshare.stock_feature.stock_board_industry_ths",
        "stock_board_industry_name_ths",
        "stock_board_industry_index_ths",
        "_get_stock_board_industry_name_ths",
    ),
    "concept": (
        "akshare.stock_feature.stock_board_concept_ths",
        "stock_board_concept_name_ths",
        "stock_board_concept_index_ths",
        "_get_stock_board_concept_name_ths",
    ),
}


class _BoundedRequests:
    def __init__(self, requests_module: Any, timeout_seconds: float) -> None:
        self._requests = requests_module
        self._timeout_seconds = timeout_seconds

    def get(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self._timeout_seconds)
        return self._requests.get(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._requests, name)


class AkshareThsBoardProvider:
    """Use public AKShare functions while bounding I/O and reusing name maps."""

    _locks = {dimension: threading.RLock() for dimension in _DIMENSION_CONFIG}

    def __init__(
        self,
        *,
        request_timeout_seconds: float = 15.0,
        module_loader: Callable[[str], ModuleType] = importlib.import_module,
    ) -> None:
        self.request_timeout_seconds = max(1.0, float(request_timeout_seconds))
        self._module_loader = module_loader
        self._catalogs: dict[str, dict[str, str]] = {}

    def fetch_catalog(self, dimension: str) -> list[dict[str, str]]:
        module, name_function, _, _ = self._module(dimension)
        with self._locks[dimension], self._bounded_requests(module):
            frame = getattr(module, name_function)()
        rows = [
            {"board_code": str(row.get("code") or ""), "board_name": str(row.get("name") or "")}
            for row in frame.to_dict("records")
            if row.get("code") and row.get("name")
        ]
        self._catalogs[dimension] = {row["board_name"]: row["board_code"] for row in rows}
        return rows

    def fetch_index(
        self,
        dimension: str,
        *,
        board_name: str,
        board_code: str,
        start_date: str,
        end_date: str,
    ) -> Any:
        module, _, index_function, map_function = self._module(dimension)
        mapping = dict(self._catalogs.get(dimension) or {})
        resolved_code = mapping.get(str(board_name))
        if resolved_code is None and re.fullmatch(r"\d{6}", str(board_code)):
            resolved_code = str(board_code)
        if resolved_code is None:
            self.fetch_catalog(dimension)
            mapping = dict(self._catalogs.get(dimension) or {})
            resolved_code = mapping.get(str(board_name))
        if resolved_code is None:
            raise KeyError(f"THS board code not found: {dimension}/{board_name}")
        mapping[str(board_name)] = resolved_code
        with self._locks[dimension]:
            original_map_loader = getattr(module, map_function)
            setattr(module, map_function, lambda: mapping)
            try:
                with self._bounded_requests(module):
                    return getattr(module, index_function)(
                        symbol=str(board_name),
                        start_date=str(start_date),
                        end_date=str(end_date),
                    )
            finally:
                setattr(module, map_function, original_map_loader)

    def _module(self, dimension: str) -> tuple[ModuleType, str, str, str]:
        if dimension not in _DIMENSION_CONFIG:
            raise ValueError(f"unsupported THS board dimension: {dimension}")
        module_name, name_function, index_function, map_function = _DIMENSION_CONFIG[dimension]
        return self._module_loader(module_name), name_function, index_function, map_function

    def _bounded_requests(self, module: ModuleType):
        return _RequestsPatch(module, self.request_timeout_seconds)


class _RequestsPatch:
    def __init__(self, module: ModuleType, timeout_seconds: float) -> None:
        self.module = module
        self.timeout_seconds = timeout_seconds
        self.original_requests: Any = None

    def __enter__(self) -> None:
        self.original_requests = self.module.requests
        self.module.requests = _BoundedRequests(self.original_requests, self.timeout_seconds)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.module.requests = self.original_requests
