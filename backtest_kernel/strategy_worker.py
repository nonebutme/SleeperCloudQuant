"""Child-process entrypoint for target-weight strategy execution."""

from __future__ import annotations

import json
import sys
from typing import Any


_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
        namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
        source_code = str(payload.get("source_code") or "")
        exec(compile(source_code, "<strategy>", "exec"), namespace, namespace)
        entrypoint = namespace.get("generate_target_weights")
        if not callable(entrypoint):
            raise ValueError("generate_target_weights entrypoint is missing")
        bars = list(payload.get("bars") or [])
        parameters = dict(payload.get("parameters") or {})
        weights = list(entrypoint(bars, parameters))
        score_entrypoint = namespace.get("generate_signal_scores")
        scores = list(score_entrypoint(bars, parameters)) if callable(score_entrypoint) else None
        sys.stdout.write(json.dumps({"status": "completed", "weights": weights, "scores": scores}))
    except Exception as exc:
        sys.stdout.write(json.dumps({"status": "failed", "error": f"{type(exc).__name__}: {exc}"}))


if __name__ == "__main__":
    main()
