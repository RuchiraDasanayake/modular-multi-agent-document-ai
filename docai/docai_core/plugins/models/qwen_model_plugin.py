"""QwenModelPlugin — on-prem/local Qwen-compatible HTTP endpoint adapter.

Implements ModelPlugin via structural Protocol compatibility.
No Qwen-specific extraction logic here — that belongs in QwenExtractionStep.
HTTP client (requests) is imported lazily inside generate() so that importing
this module never fails even if requests is absent.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from docai_core.plugins.models.base import (
    ModelPlugin,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)


@dataclass(slots=True)
class QwenModelPlugin:
    """ModelPlugin adapter for a local/on-prem Qwen-compatible HTTP endpoint.

    Tested interface is compatible with Ollama-style endpoints that accept a
    JSON body and return {"response": "..."} or {"message": {"content": "..."}}.
    Other shapes are handled defensively.
    """

    plugin_id: str = "qwen_model_plugin"
    provider_name: str = "qwen_on_prem"
    model_name: str = "qwen"
    endpoint_url: str = "http://localhost:11434/api/generate"
    timeout_seconds: int = 30
    api_key: str | None = None

    def generate(self, request: ModelRequest) -> ModelResponse:
        """POST the request to the on-prem endpoint and return a ModelResponse.

        Never raises — any transport or parsing failure returns a failed
        ModelResponse so callers can handle it uniformly.
        """
        try:
            import requests as _requests  # lazy — do not move to module level
        except ImportError:
            return ModelResponse(
                text="",
                is_stub=False,
                success=False,
                error_message="requests library not installed",
            )

        payload = self._build_payload(request)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = _requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            return ModelResponse(
                text="",
                is_stub=False,
                success=False,
                error_message=str(exc),
            )

        return self._parse_response(response)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_payload(self, request: ModelRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model_name,
            "prompt": request.prompt,
            "stream": False,
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt
        temp = request.temperature if request.temperature is not None else 0.0
        payload["options"] = {"temperature": temp}
        if request.max_tokens is not None:
            payload["options"] = {**payload["options"], "num_predict": request.max_tokens}  # type: ignore[dict-item]
        if request.json_mode is not None:
            payload["format"] = "json" if request.json_mode else ""
        if request.schema_hint:
            payload["schema_hint"] = dict(request.schema_hint)
        return payload

    def _parse_response(self, response: object) -> ModelResponse:
        """Extract response text from common Ollama/OpenAI-compatible shapes."""
        import json as _json

        raw_body: str = ""
        try:
            raw_body = response.text  # type: ignore[attr-defined]
            body = response.json()  # type: ignore[attr-defined]
        except Exception:
            return ModelResponse(
                text=raw_body,
                is_stub=False,
                success=bool(raw_body),
                error_message=None if raw_body else "empty response body",
                model_name=self.model_name,
                provider_name=self.provider_name,
            )

        extracted_text = self._extract_text_from_body(body, raw_body)
        if not extracted_text:
            return ModelResponse(
                text="",
                is_stub=False,
                success=False,
                error_message="no text found in response body",
                model_name=self.model_name,
                provider_name=self.provider_name,
            )

        parsed_json: dict[str, object] | None = None
        try:
            candidate = _json.loads(extracted_text)
            if isinstance(candidate, dict):
                parsed_json = candidate
        except Exception:
            pass

        usage: ModelUsage | None = None
        if isinstance(body, dict) and "usage" in body:
            u = body["usage"]
            if isinstance(u, dict):
                usage = ModelUsage(
                    prompt_tokens=u.get("prompt_tokens"),
                    completion_tokens=u.get("completion_tokens"),
                    total_tokens=u.get("total_tokens"),
                )

        return ModelResponse(
            text=extracted_text,
            parsed_json=parsed_json,
            model_name=self.model_name,
            provider_name=self.provider_name,
            is_stub=False,
            success=True,
            error_message=None,
            usage=usage,
        )

    @staticmethod
    def _extract_text_from_body(body: object, raw_body: str) -> str:
        """Try common response shapes in order; fall back to raw body string."""
        if isinstance(body, dict):
            # Ollama generate: {"response": "..."}
            if isinstance(body.get("response"), str):
                return body["response"]
            # OpenAI-style chat: {"message": {"content": "..."}}
            msg = body.get("message")
            if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                return msg["content"]
            # OpenAI completions: {"text": "..."}
            if isinstance(body.get("text"), str):
                return body["text"]
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    inner_msg = first.get("message") or {}
                    if isinstance(inner_msg, dict) and isinstance(inner_msg.get("content"), str):
                        return inner_msg["content"]
                    if isinstance(first.get("text"), str):
                        return first["text"]
        return raw_body
