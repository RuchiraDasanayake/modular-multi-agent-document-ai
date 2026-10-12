from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from product_eval import nuextract3_group_leaf_pilot as pilot
from product_eval.contracts import ContractError


def test_frozen_source_rule_profile_hashes_load() -> None:
    manifest, profile, rule = pilot.load_frozen_assets()
    assert len(manifest["sources"]) == 12
    assert manifest["rule_canonical_sha256"] == pilot.RULE_SHA256
    assert manifest["run_profile_canonical_sha256"] == pilot.PROFILE_SHA256
    assert profile["chat"]["max_output_tokens_per_call"] == 3072
    assert "quantity" in rule["slots"]


def test_schema_template_validation_rejects_unbounded_shapes() -> None:
    assert pilot._valid_template({"items": [{"quantity": "integer"}]})
    assert not pilot._valid_template({"items": []})
    assert not pilot._valid_template({"items": [{"quantity": "integer"}, {"quantity": "integer"}]})
    assert not pilot._valid_template({"items": [{"quantity": 2}]})
    assert not pilot._valid_template({"items.with.dot": [{"quantity": "integer"}]})
    assert not pilot._valid_template({"items": [[{"quantity": "integer"}]]})


def test_duplicate_reply_keys_are_rejected() -> None:
    with pytest.raises(ContractError, match="duplicate JSON key"):
        pilot._parse_reply_object('{"items": {"quantity": "integer", "quantity": "number"}}')


class FakeCalls:
    def __init__(self, *, invalid_first: bool = False):
        self.labels: list[str] = []
        self.bodies: list[dict[str, Any]] = []
        self.invalid_first = invalid_first

    def complete(self, label: str, body: dict[str, Any]) -> dict[str, Any]:
        self.labels.append(label)
        self.bodies.append(body)
        if label.startswith("schema-"):
            if self.invalid_first and label == "schema-a":
                return {"status": "complete", "value": {"items": []}}
            return {"status": "complete", "value": {"items": [{"quantity": "integer"}]}}
        return {"status": "complete", "value": {"items": [{"quantity": "2"}]}}


def _inventory(tmp_path: Path) -> list[dict[str, Any]]:
    return [{"doc_id": doc_id, "source_path": tmp_path / f"{doc_id}.pdf", "source_sha256": doc_id,
             "ocr_text": "Test quantity 2"}
            for doc_id in ("a", "b")]


def test_execute_arms_seals_schema_stage_before_value_stage(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pilot, "_render_images", lambda source, output: [])
    monkeypatch.setattr(pilot, "_image_input_guard", lambda source: None)
    monkeypatch.setattr(pilot, "_resource_guard", lambda: {})
    calls = FakeCalls()
    _, profile, _ = pilot.load_frozen_assets()
    outcomes, abort_reason = pilot.execute_arms(_inventory(tmp_path), profile, tmp_path, calls)
    assert abort_reason is None
    assert calls.labels == ["schema-a", "schema-b", "value-a", "value-b"]
    assert all(outcomes[doc_id]["value"]["status"] == "complete" for doc_id in ("a", "b"))
    assert all("gold" not in str(body).lower() for body in calls.bodies)
    assert calls.bodies[2]["chat_template_kwargs"]["template"] == '{"items": [{"quantity": "integer"}]}'
    receipt = json.loads((tmp_path / "preflight.json").read_text(encoding="utf-8"))
    assert len(receipt["sources"]) == 2


def test_invalid_self_template_skips_only_its_value_call(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pilot, "_render_images", lambda source, output: [])
    monkeypatch.setattr(pilot, "_image_input_guard", lambda source: None)
    monkeypatch.setattr(pilot, "_resource_guard", lambda: {})
    calls = FakeCalls(invalid_first=True)
    _, profile, _ = pilot.load_frozen_assets()
    outcomes, abort_reason = pilot.execute_arms(_inventory(tmp_path), profile, tmp_path, calls)
    assert abort_reason is None
    assert calls.labels == ["schema-a", "schema-b", "value-b"]
    assert outcomes["a"]["schema"]["status"] == "invalid_template"
    assert outcomes["a"]["value"]["status"] == "not_attempted"


def test_flag_reader_accepts_split_and_equals_forms() -> None:
    assert pilot._flag_value(["server", "--port", "18127"], "--port") == "18127"
    assert pilot._flag_value(["server", "--mmproj=model.gguf"], "--mmproj") == "model.gguf"
    assert pilot._flag_value(["server"], "--reasoning") is None
    assert pilot._flag_value(["server", "--reasoning", "off", "--reasoning", "on"], "--reasoning") is None


def test_server_process_must_own_listener_and_have_unique_flags(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import psutil

    executable = tmp_path / "server.exe"
    projector = tmp_path / "projector.gguf"
    arguments = [str(executable), "--port", "18127", "--host", "127.0.0.1", "--mmproj",
                 str(projector), "--jinja", "--reasoning", "off", "--image-min-tokens",
                 "1024", "--image-max-tokens", "1024"]
    process = SimpleNamespace(pid=11, info={"exe": str(executable), "cmdline": arguments})
    monkeypatch.setattr(psutil, "process_iter", lambda fields: [process])
    listener = lambda pid: SimpleNamespace(status=psutil.CONN_LISTEN,
                                           laddr=SimpleNamespace(ip="127.0.0.1", port=18127), pid=pid)
    _, profile, _ = pilot.load_frozen_assets()
    monkeypatch.setattr(psutil, "net_connections", lambda kind: [listener(12)])
    with pytest.raises(ContractError, match="owns the loopback listener"):
        pilot.verify_server_command("http://127.0.0.1:18127", executable, projector, profile)
    monkeypatch.setattr(psutil, "net_connections", lambda kind: [listener(11)])
    assert pilot.verify_server_command("http://127.0.0.1:18127", executable, projector, profile)["pid"] == 11
    arguments.extend(["--reasoning", "on"])
    with pytest.raises(ContractError, match="required vision flags"):
        pilot.verify_server_command("http://127.0.0.1:18127", executable, projector, profile)


def test_guarded_call_reserves_tokens_for_timeout_without_retry(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pilot, "_resource_guard", lambda: {})
    attempts = []

    def fail_once(base: str, raw: bytes) -> bytes:
        attempts.append(raw)
        raise TimeoutError("model call exceeded wall-clock deadline")

    monkeypatch.setattr(pilot, "_post_json_with_deadline", fail_once)
    call = pilot.GuardedCalls("http://127.0.0.1:18127", tmp_path)
    result = call.complete("schema-a", {"messages": []})
    assert result["status"] == "failed"
    assert call.calls == len(attempts) == 1
    assert call.accounted_tokens == pilot.CONTEXT_TOKENS
    assert (tmp_path / "request-01-schema-a.json").is_file()


def test_http_transport_enforces_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    released = threading.Event()

    class FakeConnection:
        def __init__(self, host: str, port: int, timeout: float):
            pass

        def request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> None:
            released.wait(1)

        def close(self) -> None:
            released.set()

    monkeypatch.setattr(pilot.http.client, "HTTPConnection", FakeConnection)
    started = time.perf_counter()
    with pytest.raises(TimeoutError, match="wall-clock"):
        pilot._post_json_with_deadline("http://127.0.0.1:18127", b"{}", timeout_seconds=0.02)
    assert time.perf_counter() - started < 0.5
    assert released.is_set()
