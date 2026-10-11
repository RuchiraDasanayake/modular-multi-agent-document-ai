"""Small chat-model boundary for opt-in schema and value proposals."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class ModelReply:
    text: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None


class OpenAICompatibleChat:
    """Uses an OpenAI-compatible chat endpoint without storing the key in config."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str,
        timeout_s: int = 60,
        max_tokens: int = 1200,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env):
            raise ValueError("api_key_env must name one environment variable")
        key = os.environ.get(api_key_env, "").strip()
        if not key:
            raise ValueError(f"{api_key_env} is not set")
        parsed = urlparse(base_url)
        is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_local):
            raise ValueError("model base URL must use HTTPS or local HTTP")
        if not parsed.netloc or not model.strip():
            raise ValueError("model base URL and model ID are required")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the cloud extra to use an OpenAI-compatible model") from exc
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max(1, int(max_tokens))
        self.client = OpenAI(api_key=key, base_url=self.base_url, timeout=max(1, timeout_s))

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        started = time.perf_counter()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
            )
            content = response.choices[0].message.content if response.choices else ""
            usage = getattr(response, "usage", None)
            return ModelReply(
                text=content or "",
                latency_ms=(time.perf_counter() - started) * 1000,
                prompt_tokens=_usage_count(usage, "prompt_tokens"),
                completion_tokens=_usage_count(usage, "completion_tokens"),
                finish_reason=getattr(response.choices[0], "finish_reason", None) if response.choices else None,
            )
        except Exception as exc:
            # Provider exception strings can contain credentials or document text.
            status = getattr(exc, "status_code", None)
            error = f"http_{status}" if isinstance(status, int) else type(exc).__name__
            return ModelReply(text="", latency_ms=(time.perf_counter() - started) * 1000, error=error)


def _usage_count(usage: object, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if type(value) is int and value >= 0 else None
