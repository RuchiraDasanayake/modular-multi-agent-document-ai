"""Unit tests: QwenModelPlugin.

No real HTTP calls. All network I/O is monkeypatched via a fake requests module
or a fake response object. Tests verify payload construction, response parsing,
error handling, and header behaviour.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field as dc_field
from types import ModuleType
from typing import Any

import pytest

from docai_core.plugins.models.base import ModelRequest
from docai_core.plugins.models.qwen_model_plugin import QwenModelPlugin


# ---------------------------------------------------------------------------
# Shared fake HTTP helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeResponse:
    _body: dict | str
    status_code: int = 200

    @property
    def text(self) -> str:
        if isinstance(self._body, dict):
            return json.dumps(self._body)
        return self._body

    def json(self) -> Any:
        if isinstance(self._body, dict):
            return self._body
        return json.loads(self._body)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _make_fake_requests(response_body: dict | str, *, raises: Exception | None = None):
    """Return a fake requests module that captures POST calls."""
    captured: dict[str, Any] = {}

    class FakeRequests(ModuleType):
        def post(self, url, *, json=None, headers=None, timeout=None):  # noqa: A002
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            captured["timeout"] = timeout
            if raises is not None:
                raise raises
            return FakeResponse(response_body)

    mod = FakeRequests("requests")
    return mod, captured


def _plugin(**kwargs) -> QwenModelPlugin:
    return QwenModelPlugin(**kwargs)


def _request(**kwargs) -> ModelRequest:
    defaults = dict(prompt="Extract JSON", system_prompt="System")
    defaults.update(kwargs)
    return ModelRequest(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_qwen_model_plugin_sends_model_request_payload(monkeypatch) -> None:
    fake_requests, captured = _make_fake_requests({"response": "result text"})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    plugin.generate(_request(prompt="Extract JSON", system_prompt="You are a system"))

    assert captured["json"]["prompt"] == "Extract JSON"
    assert captured["json"]["system"] == "You are a system"
    assert captured["json"]["model"] == "qwen"
    assert captured["json"]["stream"] is False


def test_qwen_model_plugin_parses_response_field(monkeypatch) -> None:
    body = {"response": '{"invoice_number": "INV-001"}'}
    fake_requests, _ = _make_fake_requests(body)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is True
    assert "INV-001" in result.text
    assert result.is_stub is False
    assert result.error_message is None


def test_qwen_model_plugin_parses_message_content_shape(monkeypatch) -> None:
    body = {"message": {"content": '{"invoice_number": "INV-001"}'}}
    fake_requests, _ = _make_fake_requests(body)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is True
    assert "INV-001" in result.text


def test_qwen_model_plugin_parses_text_shape(monkeypatch) -> None:
    body = {"text": '{"invoice_number": "INV-001"}'}
    fake_requests, _ = _make_fake_requests(body)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is True
    assert "INV-001" in result.text


def test_qwen_model_plugin_parses_choices_shape(monkeypatch) -> None:
    body = {"choices": [{"message": {"content": '{"invoice_number": "INV-001"}'}}]}
    fake_requests, _ = _make_fake_requests(body)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is True
    assert "INV-001" in result.text


def test_qwen_model_plugin_returns_failure_on_timeout(monkeypatch) -> None:
    fake_requests, _ = _make_fake_requests({}, raises=TimeoutError("timed out"))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is False
    assert result.is_stub is False
    assert result.error_message is not None
    assert len(result.error_message) > 0


def test_qwen_model_plugin_returns_failure_on_generic_exception(monkeypatch) -> None:
    fake_requests, _ = _make_fake_requests({}, raises=RuntimeError("connection refused"))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is False
    assert result.error_message is not None


def test_qwen_model_plugin_adds_authorization_header_when_api_key_present(monkeypatch) -> None:
    fake_requests, captured = _make_fake_requests({"response": "ok"})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin(api_key="secret-key")
    plugin.generate(_request())

    assert captured["headers"].get("Authorization") == "Bearer secret-key"


def test_qwen_model_plugin_no_authorization_header_when_no_api_key(monkeypatch) -> None:
    fake_requests, captured = _make_fake_requests({"response": "ok"})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin(api_key=None)
    plugin.generate(_request())

    assert "Authorization" not in captured["headers"]


def test_qwen_model_plugin_import_does_not_require_requests() -> None:
    # Verify the module is importable even if requests is absent.
    # We check that 'requests' is NOT in the module's globals at import time
    # by inspecting the source module dict rather than patching sys.modules
    # (which would break the live test environment).
    import docai_core.plugins.models.qwen_model_plugin as mod
    module_globals = vars(mod)
    assert "requests" not in module_globals, (
        "requests must not be imported at module level — use lazy import inside generate()"
    )


def test_qwen_model_plugin_returns_failure_when_requests_absent(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "requests", None)  # type: ignore[arg-type]

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.success is False
    assert result.is_stub is False
    assert result.error_message is not None


def test_qwen_model_plugin_parsed_json_populated_when_response_is_valid_json(monkeypatch) -> None:
    body = {"response": '{"invoice_number": "INV-001", "status": "Paid"}'}
    fake_requests, _ = _make_fake_requests(body)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    result = plugin.generate(_request())

    assert result.parsed_json is not None
    assert result.parsed_json.get("invoice_number") == "INV-001"


def test_qwen_model_plugin_payload_includes_temperature(monkeypatch) -> None:
    fake_requests, captured = _make_fake_requests({"response": "ok"})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin()
    plugin.generate(_request(temperature=0.5))

    assert captured["json"]["options"]["temperature"] == 0.5


def test_qwen_model_plugin_uses_configured_endpoint(monkeypatch) -> None:
    fake_requests, captured = _make_fake_requests({"response": "ok"})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)

    plugin = _plugin(endpoint_url="http://custom-host:8080/api/generate")
    plugin.generate(_request())

    assert captured["url"] == "http://custom-host:8080/api/generate"
