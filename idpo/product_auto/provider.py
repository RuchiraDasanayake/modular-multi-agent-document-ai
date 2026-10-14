"""Small chat-model boundary for opt-in schema and value proposals."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from idpo.product_auto.visual_input import PreparedVisualRequest


@dataclass(frozen=True)
class ModelReply:
    text: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None
    error: str | None = None
    error_category: str | None = None
    sdk_attempts: int | None = None
    refusal: bool = False


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
        parsed = urlparse(base_url)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not local_http:
            raise ValueError("model base URL must use HTTPS or local HTTP")
        if not parsed.netloc or not model.strip():
            raise ValueError("model base URL and model ID are required")
        key = os.environ.get(api_key_env, "").strip()
        if not key and not local_http:
            raise ValueError(f"{api_key_env} is not set")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the cloud extra to use an OpenAI-compatible model") from exc
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max(1, int(max_tokens))
        # The SDK requires a nonempty key even when a loopback server has no authentication.
        # Never forward a cloud key from this process to a local model server.
        self.client = OpenAI(
            api_key="local-no-auth" if local_http else key,
            base_url=self.base_url,
            timeout=max(1, timeout_s),
            # A retry after a lost response can duplicate a billable request.
            # Revisit only with a provider-backed idempotency and billing policy.
            max_retries=0,
        )

    def complete_json(
        self, *, system: str, prompt: str, response_format: dict[str, object] | None = None,
    ) -> ModelReply:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
        }
        if response_format is not None:
            if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
                raise ValueError("response_format must be an explicit strict JSON Schema")
            named_schema = response_format.get("json_schema")
            if not isinstance(named_schema, dict) or named_schema.get("strict") is not True or \
                    not isinstance(named_schema.get("name"), str) or not isinstance(named_schema.get("schema"), dict):
                raise ValueError("response_format must be an explicit strict JSON Schema")
            # Copy and bound the server-selected schema before sending it to an external model.
            encoded = json.dumps(response_format, ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > 32_768:
                raise ValueError("response_format exceeds the 32 KiB limit")
            request["response_format"] = json.loads(encoded)
        return self._complete_request(request)

    def complete_visual_json(self, request: PreparedVisualRequest) -> ModelReply:
        """Send an immutable, preplanned image request without fallback or retry."""
        import hashlib
        import httpx
        from idpo.product_auto.visual_input import MAX_REQUEST_BYTES, PreparedVisualRequest, VisualInputError

        if not isinstance(request, PreparedVisualRequest):
            raise ValueError("visual request must be prepared with complete page coverage")
        body = request.validated_body(model=self.model, max_tokens=self.max_tokens)
        expected = hashlib.sha256(request.body_json).hexdigest()

        def verify_wire(actual: httpx.Request) -> None:
            # Inspect the SDK's actual serialization before any bytes reach the network.
            if len(actual.content) > MAX_REQUEST_BYTES or hashlib.sha256(actual.content).hexdigest() != expected:
                raise VisualInputError("visual_wire_body_mismatch")

        with httpx.Client(timeout=self.client.timeout, follow_redirects=False,
                          event_hooks={"request": [verify_wire]}) as guarded:
            client = self.client.with_options(http_client=guarded, max_retries=0)
            return self._complete_request(body, client=client)

    def _complete_request(self, request: dict[str, object], *, client=None) -> ModelReply:
        started = time.perf_counter()
        try:
            response = (client or self.client).chat.completions.create(**request)
            message = response.choices[0].message if response.choices else None
            content = message.content if message is not None else ""
            usage = getattr(response, "usage", None)
            return ModelReply(
                text=content or "",
                latency_ms=(time.perf_counter() - started) * 1000,
                prompt_tokens=_usage_count(usage, "prompt_tokens"),
                completion_tokens=_usage_count(usage, "completion_tokens"),
                finish_reason=getattr(response.choices[0], "finish_reason", None) if response.choices else None,
                sdk_attempts=1,
                refusal=bool(getattr(message, "refusal", None)),
            )
        except Exception as exc:  # noqa: BLE001 - redact provider failures before they reach artifacts
            # Provider exception strings can contain credentials or document text.
            status = getattr(exc, "status_code", None)
            error = f"http_{status}" if type(status) is int else type(exc).__name__
            return ModelReply(
                text="",
                latency_ms=(time.perf_counter() - started) * 1000,
                error=error,
                error_category=_error_category(exc, status),
                sdk_attempts=1,
            )


def _usage_count(usage: object, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if type(value) is int and value >= 0 else None


def _error_category(exc: Exception, status: object) -> str:
    """Classify failures without persisting provider messages or document text."""
    if type(status) is int:
        if status == 401:
            return "authentication"
        if status == 408:
            # An HTTP timeout does not establish whether the provider completed or charged the call.
            return "transport_timeout"
        if status == 429:
            return "rate_limit"
        if status >= 500:
            return "provider_server"
        if status >= 400:
            return "request_rejected"
        return "provider_http"

    names: set[str] = set()
    seen: set[int] = set()
    current: BaseException | None = exc
    for _ in range(5):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        names.add(type(current).__name__)
        current = current.__cause__
    if names & {"APITimeoutError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout", "TimeoutError"}:
        return "transport_timeout"
    if names & {"ConnectError", "ConnectionRefusedError", "gaierror", "NetworkError"}:
        return "transport_connect"
    if names & {"RemoteProtocolError", "LocalProtocolError", "ProtocolError"}:
        return "transport_protocol"
    if "APIConnectionError" in names:
        return "transport_other"
    return "provider_other"
