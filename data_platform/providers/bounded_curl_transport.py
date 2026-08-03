"""Bounded HTTPS JSON transport backed by an existing system curl binary."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Callable, Mapping
from urllib.parse import urlencode


class CurlTransportError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"{category}: {message}")
        self.category = category


class BoundedCurlJsonTransport:
    """Perform one TLS-verified JSON request with a hard wall-clock bound."""

    def __init__(
        self,
        executable: str,
        *,
        connect_timeout_seconds: int = 10,
        max_time_seconds: int = 25,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.executable = str(executable)
        self.connect_timeout_seconds = max(1, int(connect_timeout_seconds))
        self.max_time_seconds = max(
            self.connect_timeout_seconds, int(max_time_seconds)
        )
        self.runner = runner

    @classmethod
    def auto(
        cls,
        *,
        connect_timeout_seconds: int = 10,
        max_time_seconds: int = 25,
    ) -> BoundedCurlJsonTransport | None:
        executable = shutil.which("curl.exe") or shutil.which("curl")
        if not executable:
            return None
        return cls(
            executable,
            connect_timeout_seconds=connect_timeout_seconds,
            max_time_seconds=max_time_seconds,
        )

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        if not str(url).lower().startswith("https://"):
            raise CurlTransportError("policy_error", "only HTTPS URLs are allowed")
        target = str(url)
        if params:
            separator = "&" if "?" in target else "?"
            target = f"{target}{separator}{urlencode(dict(params), doseq=True)}"
        command = [
            self.executable,
            "-sS",
            "--fail-with-body",
            "--proto",
            "=https",
            "--tlsv1.2",
            "--connect-timeout",
            str(self.connect_timeout_seconds),
            "--max-time",
            str(self.max_time_seconds),
            "--request",
            str(method).upper(),
        ]
        for key, value in dict(headers or {}).items():
            if key.lower() == "accept-encoding":
                continue
            command.extend(["--header", f"{key}: {value}"])
        for key, value in dict(data or {}).items():
            command.extend(["--data-urlencode", f"{key}={value}"])
        command.append(target)
        try:
            completed = self.runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.max_time_seconds + 5,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise CurlTransportError("timeout", "curl process exceeded hard limit") from error
        except Exception as error:
            raise CurlTransportError(
                "transport_error", f"{type(error).__name__}: {str(error)[:200]}"
            ) from error
        if completed.returncode != 0:
            category = _returncode_category(int(completed.returncode))
            message = str(completed.stderr or completed.stdout or "").strip()[:240]
            raise CurlTransportError(
                category, f"curl exit {completed.returncode}: {message}"
            )
        try:
            payload = json.loads(str(completed.stdout))
        except json.JSONDecodeError as error:
            raise CurlTransportError(
                "json_error", f"invalid JSON at position {error.pos}"
            ) from error
        if not isinstance(payload, dict):
            raise CurlTransportError("schema_error", "response is not a JSON object")
        return payload


def _returncode_category(returncode: int) -> str:
    if returncode == 28:
        return "timeout"
    if returncode in {35, 51, 53, 58, 59, 60, 64, 66, 77, 80, 82, 83, 90, 91}:
        return "tls_error"
    if returncode in {5, 6, 7, 52, 55, 56}:
        return "connection_error"
    if returncode == 22:
        return "http_error"
    return "transport_error"
