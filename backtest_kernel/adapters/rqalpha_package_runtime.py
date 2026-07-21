"""Runtime selector that probes the real rqalpha package before falling back locally."""

from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from typing import Any

from backtest_kernel.adapters.rqalpha_ricequant_gateway import RqalphaRuntimeProtocol


class RqalphaPackageRuntime:
    """Probe a real rqalpha installation while preserving the local runtime fallback."""

    def __init__(self, fallback_runtime: RqalphaRuntimeProtocol) -> None:
        self._fallback_runtime = fallback_runtime

    def run(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        status = self.probe_status()
        if not status["available"]:
            result = dict(self._fallback_runtime.run(payload))
            raw_result = dict(result.get("raw_result") or {})
            logs = list(raw_result.get("logs") or [])
            logs.append(
                {
                    "recorded_at": str(result.get("end_date") or payload.get("end_date") or ""),
                    "level": "INFO",
                    "stage": "rqalpha_package_probe",
                    "message": "real rqalpha package unavailable; local SQLite runtime fallback used",
                    "details": status,
                }
            )
            raw_result["logs"] = logs
            raw_result["engine_probe"] = status
            raw_result["engine"] = raw_result.get("engine") or "local_sqlite_backtest_runtime"
            result["raw_result"] = raw_result
            return result
        result = dict(self._fallback_runtime.run(payload))
        raw_result = dict(result.get("raw_result") or {})
        raw_result["engine_probe"] = status
        raw_result["real_rqalpha_status"] = "detected_not_executed_yet"
        raw_result["execution_boundary"] = "real rqalpha package is installed, but stage23 still normalizes through local SQLite runtime until strategy/data bundle execution is approved"
        result["raw_result"] = raw_result
        return result

    @staticmethod
    def probe_status() -> dict[str, Any]:
        spec = importlib.util.find_spec("rqalpha")
        if spec is None:
            return {
                "provider": "rqalpha",
                "available": False,
                "status": "package_missing",
                "reason": "Python package rqalpha is not installed in the active runtime.",
            }
        version = "unknown"
        try:
            import rqalpha  # type: ignore

            version = str(getattr(rqalpha, "__version__", "unknown"))
        except Exception as exc:  # pragma: no cover - depends on external package state
            return {
                "provider": "rqalpha",
                "available": False,
                "status": "import_failed",
                "reason": str(exc),
            }
        return {
            "provider": "rqalpha",
            "available": True,
            "status": "package_detected",
            "version": version,
        }
