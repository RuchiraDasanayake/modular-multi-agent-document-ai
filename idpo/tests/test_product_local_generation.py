"""Explicit local sampling controls and receipt integrity, without model inference."""

from __future__ import annotations

import hashlib
import json
import sys
import types

import pytest
from PIL import Image

from idpo.product_auto.provider import OpenAICompatibleChat, validate_generation_settings
from idpo.product_auto.visual_input import VisualInputError, plan_visual_requests, prepare_visual_document
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot
from idpo.product_auto.confirmed_schema import load_confirmed_schema


@pytest.fixture(autouse=True)
def clean_sampler_environment(monkeypatch):
    monkeypatch.delenv("IDPO_LOCAL_TEMPERATURE", raising=False)
    monkeypatch.delenv("IDPO_LOCAL_SEED", raising=False)
    monkeypatch.delenv("IDPO_LOCAL_REASONING_EFFORT", raising=False)


def fake_client(monkeypatch, *, reply=None):
    captured = {"requests": []}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            captured["requests"].append(kwargs)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(
                message=types.SimpleNamespace(content=reply or '{"values":[]}'), finish_reason="stop")],
                usage=None, system_fingerprint="llama-b12345")

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    return captured


def test_local_sampler_is_explicit_frozen_and_never_forwards_cloud_key(monkeypatch):
    captured = fake_client(monkeypatch)
    monkeypatch.setenv("SYNTHETIC_KEY", "private-cloud-key")
    monkeypatch.setenv("IDPO_LOCAL_TEMPERATURE", "0")
    monkeypatch.setenv("IDPO_LOCAL_SEED", "42")
    monkeypatch.setenv("IDPO_LOCAL_REASONING_EFFORT", "none")
    model = OpenAICompatibleChat(base_url="http://127.0.0.1:8080/v1", model="local-model",
                                 api_key_env="SYNTHETIC_KEY")
    monkeypatch.setenv("IDPO_LOCAL_SEED", "99")
    model.generation_settings["seed"] = 123
    reply = model.complete_json(system="system", prompt="synthetic")
    assert captured["client"]["api_key"] == "local-no-auth"
    assert captured["client"]["max_retries"] == 0
    assert captured["requests"][0]["temperature"] == 0
    assert captured["requests"][0]["seed"] == 42
    assert captured["requests"][0]["reasoning_effort"] == "none"
    assert reply.system_fingerprint == "llama-b12345"
    assert model.runtime_provenance == {"contract_version": 1, "transport": "loopback_http",
        "model_id": "local-model", "generation_settings": {"temperature": 0.0, "seed": 42, "reasoning_effort": "none"},
        "reproducibility": "configuration_recorded_not_bitwise_guaranteed"}
    assert "private-cloud-key" not in str(model.runtime_provenance)


def test_cloud_and_default_local_requests_keep_historical_sampling(monkeypatch):
    captured = fake_client(monkeypatch)
    local = OpenAICompatibleChat(base_url="http://localhost:8080/v1", model="local", api_key_env="KEY")
    local.complete_json(system="system", prompt="synthetic")
    monkeypatch.setenv("KEY", "synthetic")
    monkeypatch.setenv("IDPO_LOCAL_TEMPERATURE", "bad-local-value")
    monkeypatch.setenv("IDPO_LOCAL_SEED", "bad-local-value")
    monkeypatch.setenv("IDPO_LOCAL_REASONING_EFFORT", "bad-local-value")
    cloud = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="cloud", api_key_env="KEY")
    cloud.complete_json(system="system", prompt="synthetic")
    for request in captured["requests"]:
        assert "temperature" not in request and "seed" not in request and "reasoning_effort" not in request
    with pytest.raises(ValueError, match="only for loopback"):
        OpenAICompatibleChat(base_url="https://example.invalid/v1", model="cloud", api_key_env="KEY", seed=42)


@pytest.mark.parametrize("settings", [{"temperature": True}, {"temperature": float("nan")},
    {"temperature": float("inf")}, {"temperature": -0.1}, {"temperature": 2.1},
    {"seed": True}, {"seed": -1}, {"seed": 2**31}, {"seed": 4.2}, {"top_p": 0.9},
    {"reasoning_effort": False}, {"reasoning_effort": "invalid"}, []])
def test_invalid_sampler_controls_fail_before_request(settings):
    with pytest.raises(ValueError):
        validate_generation_settings(settings)


@pytest.mark.parametrize("name,value", [("IDPO_LOCAL_TEMPERATURE", "NaN"),
    ("IDPO_LOCAL_TEMPERATURE", "invalid"), ("IDPO_LOCAL_SEED", "1.0"),
    ("IDPO_LOCAL_SEED", "-1"), ("IDPO_LOCAL_SEED", "2147483648"),
    ("IDPO_LOCAL_REASONING_EFFORT", "invalid")])
def test_invalid_local_environment_fails_at_construction(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        OpenAICompatibleChat(base_url="http://localhost:8080/v1", model="local", api_key_env="KEY")


def prepared_request(tmp_path, *, settings=None):
    source = tmp_path / "source.png"
    with Image.new("RGB", (32, 32), "white") as image:
        image.save(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    pages = prepare_visual_document(source, expected_source_sha256=source_hash,
        pages=[{"page": 1, "text": "Total 100", "ocr_lines": [], "ocr_provenance": {}}])
    return plan_visual_requests(pages, fields=[{"field_id": "total", "type": "integer"}],
        intent="Read total", model="local", max_tokens=1200, generation_settings=settings)[0]


def test_visual_sampler_is_sealed_in_actual_wire_bytes(tmp_path, monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("openai")
    request = prepared_request(tmp_path, settings={"temperature": 0, "seed": 42, "reasoning_effort": "none"})
    body = json.loads(request.body_json)
    assert {key: body[key] for key in ("temperature", "seed")} == {"temperature": 0, "seed": 42}
    assert request.receipt()["generation_settings"] == {"temperature": 0, "seed": 42, "reasoning_effort": "none"}
    assert request.receipt()["request_sha256"] == hashlib.sha256(request.body_json).hexdigest()
    seen = []
    real_client = httpx.Client

    def respond(wire):
        seen.append(wire)
        assert wire.content == request.body_json
        return httpx.Response(200, json={"id": "synthetic", "object": "chat.completion", "created": 1,
            "model": "local", "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"},
                "finish_reason": "stop"}], "system_fingerprint": "llama-b12345"})

    class GuardedClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", GuardedClient)
    model = OpenAICompatibleChat(base_url="http://localhost:8080/v1", model="local", api_key_env="KEY",
                                 temperature=0, seed=42, reasoning_effort="none")
    try:
        reply = model.complete_visual_json(request)
        assert reply.error is None and reply.system_fingerprint == "llama-b12345"
        assert len(seen) == 1
    finally:
        model.client.close()


def test_visual_changed_sampler_fails_before_transport(tmp_path, monkeypatch):
    pytest.importorskip("openai")
    request = prepared_request(tmp_path, settings={"temperature": 0, "seed": 42})
    model = OpenAICompatibleChat(base_url="http://localhost:8080/v1", model="local", api_key_env="KEY",
                                 temperature=0, seed=99)
    try:
        with pytest.raises(VisualInputError, match="visual_generation_configuration_changed"):
            model.complete_visual_json(request)
    finally:
        model.client.close()


def test_runtime_and_reported_fingerprint_persist_without_claiming_determinism(tmp_path, monkeypatch):
    fake_client(monkeypatch, reply='{"values":[{"field_id":"total","value":100,"page":1,"quote":"100"}]}')
    model = OpenAICompatibleChat(base_url="http://localhost:8080/v1", model="local", api_key_env="KEY",
                                 temperature=0, seed=42)
    source = tmp_path / "source.txt"
    source.write_text("Total: 100", encoding="utf-8")
    schema_path, schema_digest = snapshot(tmp_path, fields=[{"field_id": "total", "type": "integer",
        "description": "Total", "example_values": ["100"]}])
    schema = load_confirmed_schema(schema_path, schema_digest)
    result = process_auto(source, model=model, confirmed_schema=schema, output_root=tmp_path / "runs")
    run_dir = tmp_path / "runs" / result["run_id"]
    marker = json.loads((run_dir / "run.json").read_text())
    candidate = json.loads((run_dir / "candidates.jsonl").read_text())
    sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text())
    assert marker["model_runtime"] == sidecar["model_runtime"] == model.runtime_provenance
    assert sidecar["model_calls"][0]["system_fingerprint"] == "llama-b12345"
    assert candidate["document_status"] == "needs_review"
