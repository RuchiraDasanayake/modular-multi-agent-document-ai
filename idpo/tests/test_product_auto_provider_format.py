from __future__ import annotations

import sys
import types

import pytest

from idpo.product_auto.provider import OpenAICompatibleChat


def strict_values_format() -> dict[str, object]:
    return {"type": "json_schema", "json_schema": {"name": "synthetic_values_v1", "strict": True,
        "schema": {"type": "object", "properties": {"values": {"type": "array", "items": {
            "type": "object", "properties": {
                "field_id": {"type": "string", "enum": ["invoice_number"]},
                "value": {"type": ["string", "null"]},
            }, "required": ["field_id", "value"], "additionalProperties": False,
        }}}, "required": ["values"], "additionalProperties": False}}}


def test_strict_values_format_is_sent_only_when_explicitly_selected(monkeypatch) -> None:
    captured: dict[str, object] = {"requests": []}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured["client"] = kwargs
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, **kwargs: object) -> types.SimpleNamespace:
            captured["requests"].append(kwargs)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content='{"values":[]}'), finish_reason="stop")],
                usage=types.SimpleNamespace(prompt_tokens=9, completion_tokens=5))

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("PRODUCT_TEST_KEY", "synthetic-secret")
    model = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="example-model",
                                 api_key_env="PRODUCT_TEST_KEY")
    assert model.complete_json(system="system", prompt="plain").error is None
    assert "response_format" not in captured["requests"][0]
    response_format = strict_values_format()
    assert model.complete_json(system="system", prompt="strict", response_format=response_format).error is None
    assert captured["requests"][1] == {
        "model": "example-model",
        "messages": [{"role": "system", "content": "system"}, {"role": "user", "content": "strict"}],
        "max_tokens": 1200, "response_format": response_format,
    }
    assert captured["client"]["max_retries"] == 0
    response_format["json_schema"]["name"] = "changed_after_call"
    assert captured["requests"][1]["response_format"]["json_schema"]["name"] == "synthetic_values_v1"


def test_strict_format_rejection_does_not_retry_or_drop_the_format(monkeypatch) -> None:
    requests: list[dict[str, object]] = []

    class Rejected(Exception):
        status_code = 400

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, **kwargs: object) -> None:
            requests.append(kwargs)
            raise Rejected("private request text")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("PRODUCT_TEST_KEY", "synthetic-secret")
    model = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="example-model",
                                 api_key_env="PRODUCT_TEST_KEY")
    reply = model.complete_json(system="system", prompt="synthetic", response_format=strict_values_format())
    assert len(requests) == 1
    assert requests[0]["response_format"] == strict_values_format()
    assert (reply.error, reply.error_category, reply.sdk_attempts) == ("http_400", "request_rejected", 1)
    assert "private request text" not in str(reply)


def test_strict_format_requires_a_bounded_explicit_schema(monkeypatch) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **_: None))

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("PRODUCT_TEST_KEY", "synthetic-secret")
    model = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="example-model",
                                 api_key_env="PRODUCT_TEST_KEY")
    with pytest.raises(ValueError, match="explicit strict JSON Schema"):
        model.complete_json(system="system", prompt="synthetic", response_format={"type": "json_object"})
    with pytest.raises(ValueError, match="explicit strict JSON Schema"):
        model.complete_json(system="system", prompt="synthetic", response_format={
            "type": "json_schema", "json_schema": {"name": "weak", "strict": False, "schema": {}},
        })
    oversized = strict_values_format()
    oversized["json_schema"]["schema"]["description"] = "x" * 33_000
    with pytest.raises(ValueError, match="32 KiB"):
        model.complete_json(system="system", prompt="synthetic", response_format=oversized)
