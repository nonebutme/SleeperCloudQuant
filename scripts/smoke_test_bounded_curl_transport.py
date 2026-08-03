"""Deterministic smoke tests for the bounded system-curl transport."""

from __future__ import annotations

import json
from types import SimpleNamespace

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()

from data_platform.providers.bounded_curl_transport import (  # noqa: E402
    BoundedCurlJsonTransport,
    CurlTransportError,
)


def main() -> None:
    calls: list[tuple[list[str], dict]] = []

    def success(command: list[str], **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"records": [{"SECCODE": "000001"}]}),
            stderr="",
        )

    transport = BoundedCurlJsonTransport(
        "curl-test",
        connect_timeout_seconds=3,
        max_time_seconds=7,
        runner=success,
    )
    payload = transport.request_json(
        "POST",
        "https://webapi.cninfo.com.cn/api/stock/p_stock2110",
        params={"scode": "000001", "sdate": "2020-01-01"},
        headers={"Accept": "*/*"},
    )
    command, kwargs = calls[0]
    assert payload["records"][0]["SECCODE"] == "000001"
    assert "--proto" in command and "=https" in command
    assert "--tlsv1.2" in command
    assert "--max-time" in command and "7" in command
    assert "scode=000001" in command[-1]
    assert kwargs["timeout"] == 12
    assert kwargs["check"] is False

    try:
        transport.request_json("GET", "http://www.cninfo.com.cn/example")
    except CurlTransportError as error:
        assert error.category == "policy_error"
    else:
        raise AssertionError("plain HTTP was not rejected")

    failing = BoundedCurlJsonTransport(
        "curl-test",
        runner=lambda *_args, **_kwargs: SimpleNamespace(
            returncode=60, stdout="", stderr="certificate verify failed"
        ),
    )
    try:
        failing.request_json("GET", "https://www.cninfo.com.cn/example")
    except CurlTransportError as error:
        assert error.category == "tls_error"
    else:
        raise AssertionError("curl TLS failure was not categorized")

    print("Bounded curl transport smoke passed")


if __name__ == "__main__":
    main()
