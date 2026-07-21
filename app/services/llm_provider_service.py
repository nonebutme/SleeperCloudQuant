"""Safe optional LLM provider gateway for AI workflow traces."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMProviderResult:
    status: str
    provider_profile: str
    model: str | None = None
    content: str | None = None
    reason: str | None = None
    request_summary: dict[str, Any] | None = None

    def as_trace(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider_profile": self.provider_profile,
            "model": self.model,
            "content": self.content,
            "reason": self.reason,
            "request_summary": self.request_summary or {},
        }


class LLMProviderGateway:
    """Call an OpenAI-compatible chat endpoint only when explicitly configured."""

    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get_provider_status(self, provider_profile: str | None = None) -> dict[str, Any]:
        profile = provider_profile or os.environ.get("SCQ_LLM_PROVIDER_PROFILE") or "local-demo-tradingagents-style"
        base_url = os.environ.get("SCQ_LLM_BASE_URL")
        model = os.environ.get("SCQ_LLM_MODEL")
        has_key = bool(os.environ.get("SCQ_LLM_API_KEY"))
        enabled = _is_external_profile(profile) and bool(base_url and model and has_key)
        return {
            "provider_profile": profile,
            "enabled": enabled,
            "mode": "external-openai-compatible" if _is_external_profile(profile) else "local-demo",
            "base_url_configured": bool(base_url),
            "api_key_configured": has_key,
            "model": model or "未配置",
            "status": "ready" if enabled else "fallback_to_local_demo",
            "missing": [name for name, ready in (("SCQ_LLM_BASE_URL", bool(base_url)), ("SCQ_LLM_API_KEY", has_key), ("SCQ_LLM_MODEL", bool(model))) if not ready] if _is_external_profile(profile) else [],
        }

    def generate_summary(self, *, provider_profile: str | None, prompt: str) -> LLMProviderResult:
        profile = provider_profile or "local-demo-tradingagents-style"
        status = self.get_provider_status(profile)
        if not _is_external_profile(profile):
            return LLMProviderResult(status="skipped", provider_profile=profile, reason="local_demo_profile")
        if not status["enabled"]:
            return LLMProviderResult(
                status="fallback_to_local_demo",
                provider_profile=profile,
                model=str(status.get("model") or "未配置"),
                reason="missing_external_llm_configuration",
                request_summary={"missing": status.get("missing", [])},
            )
        try:
            content = self._call_chat_completion(prompt=prompt)
        except Exception as exc:  # pragma: no cover - network path is environment-dependent.
            return LLMProviderResult(
                status="provider_error_fallback_to_local_demo",
                provider_profile=profile,
                model=os.environ.get("SCQ_LLM_MODEL"),
                reason=type(exc).__name__,
            )
        return LLMProviderResult(
            status="completed",
            provider_profile=profile,
            model=os.environ.get("SCQ_LLM_MODEL"),
            content=content,
            request_summary={"prompt_chars": len(prompt)},
        )

    def _call_chat_completion(self, *, prompt: str) -> str:
        base_url = str(os.environ["SCQ_LLM_BASE_URL"]).rstrip("/")
        api_key = os.environ["SCQ_LLM_API_KEY"]
        model = os.environ["SCQ_LLM_MODEL"]
        endpoint = f"{base_url}/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是量化研究辅助分析员。只输出研究辅助摘要，不给出确定性投资建议。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover - network path is environment-dependent.
            raise RuntimeError(f"llm provider http error: {exc.code}") from exc
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not choices:
            return ""
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return str(message.get("content") or "")
        return ""


def _is_external_profile(profile: str | None) -> bool:
    normalized = str(profile or "").strip().lower()
    return normalized in {"openai-compatible", "dashscope-compatible", "external-openai-compatible", "real-llm-provider"}
