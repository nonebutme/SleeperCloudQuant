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


def _write_payload(payload: dict[str, Any]) -> None:
    """Write worker JSON with an explicit UTF-8 binary boundary."""

    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(encoded)


def main() -> None:
    try:
        # Windows redirected stdin can inherit a locale encoding such as GBK.
        # The parent always sends UTF-8, so decode the byte stream explicitly;
        # otherwise Chinese strategy comments can become surrogate characters.
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
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
        _write_payload({"status": "completed", "weights": weights, "scores": scores})
    except Exception as exc:
        _write_payload({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})


if __name__ == "__main__":
    main()
