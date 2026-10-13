"""Synthetic safety/receipt regressions; never OCR or contact a model provider."""

from __future__ import annotations

import dataclasses
import json
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace

import pytest

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.workflow import _doc_id
from product_eval import final_gate_freeze as freezer
from product_eval import final_model_gate as gate
from product_eval.final_gate_ledger import GateStopped, Ledger, exclusive_run_lock


def schema_file(directory: Path):
    path = directory / "schema.json"
    freezer.write_new(path, {
        "contract_version": 1, "brief_id": "brief_" + "a" * 32, "revision": 2,
        "audit_event_id": "b" * 32, "state": "confirmed", "owner_user_id": "synthetic-evaluation",
        "job_id": "c" * 32, "intent": "Extract the final total", "payload_sha256": "f" * 64,
        "fields": [{"field_id": "total", "type": "integer", "description": "Final amount", "example_values": []}],
        "sample_sources": [{"file_id": "d" * 32, "source_sha256": "e" * 64}],
    })
    return path, freezer.digest_file(path)


def source_file(directory: Path, index=0, *, suffix=".png", text="Total: 42"):
    path = directory / f"original-{index}{suffix}"
    path.write_text(text, encoding="utf-8")
    sha = freezer.digest_file(path)
    return {"doc_id": _doc_id(path.name, sha, 0), "source_path": str(path), "source_sha256": sha,
            "source_size_bytes": path.stat().st_size, "family": "receipt", "dataset_id": "synthetic",
            "gate_shard": "shard_00"}


def ledger_fixture(tmp_path, count=2, max_calls=2500):
    rows = [source_file(tmp_path, index, text=f"Total {index}") for index in range(count)]
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.initialize(rows, "a" * 64, max_calls)
    return ledger, rows


def reply(**changes):
    return ModelReply(text='{"values":[{"field_id":"total","value":42,"page":1,"quote":"42"}]}',
                      latency_ms=1.5, prompt_tokens=10, completion_tokens=6, finish_reason="stop",
                      sdk_attempts=1, **changes)


def test_request_begun_is_committed_before_provider_invocation(tmp_path):
    ledger, rows = ledger_fixture(tmp_path)
    doc_id = rows[0]["doc_id"]
    assert ledger.claim(doc_id)

    class Provider:
        model, max_tokens = "innobot-luna-6", 8192

        def complete_json(self, **_):
            state = Ledger(tmp_path / "ledger.sqlite3").snapshot()
            assert state["attempts"][0]["state"] == "request_begun"
            assert (tmp_path / "requests" / f"{state['attempts'][0]['request_sha256']}.json").exists()
            return reply()

    model = gate.RecordedModel(Provider(), tmp_path, doc_id)
    result = model.complete_json(system="s", prompt="p", response_format={"type": "json_schema"})
    assert result.text == reply().text
    state = ledger.snapshot()
    assert len(state["attempts"]) == 1 and state["attempts"][0]["state"] == "replied"
    assert state["attempts"][0]["prompt_tokens"] == 10


def test_failure_to_commit_marker_never_calls_provider(tmp_path, monkeypatch):
    ledger, rows = ledger_fixture(tmp_path)
    ledger.claim(rows[0]["doc_id"])
    calls = []
    provider = SimpleNamespace(model="innobot-luna-6", max_tokens=8192,
                               complete_json=lambda **_: calls.append(1))
    def failed(*_):
        raise OSError("disk full")
    monkeypatch.setattr(Ledger, "begin_attempt", failed)
    with pytest.raises(OSError):
        gate.RecordedModel(provider, tmp_path, rows[0]["doc_id"]).complete_json(
            system="s", prompt="p", response_format={"type": "json_schema"})
    assert calls == []


def test_interrupted_attempt_and_source_are_never_reclaimed(tmp_path):
    ledger, rows = ledger_fixture(tmp_path)
    assert ledger.claim(rows[0]["doc_id"])
    ledger.begin_attempt(rows[0]["doc_id"], "b" * 64)
    assert ledger.recover_interrupted() == 1
    assert not ledger.claim(rows[0]["doc_id"])
    assert ledger.claim(rows[1]["doc_id"])
    assert ledger.snapshot()["attempts"][0]["state"] == "uncertain"


@pytest.mark.parametrize("limit, per_source", [(2, False), (2500, True)])
def test_global_and_per_source_limits_fail_before_an_extra_request(tmp_path, limit, per_source):
    ledger, rows = ledger_fixture(tmp_path, max_calls=limit)
    ledger.claim(rows[0]["doc_id"])
    count = 4 if per_source else 2
    for _ in range(count):
        attempt, _ = ledger.begin_attempt(rows[0]["doc_id"], "b" * 64)
        ledger.finish_attempt(attempt, "c" * 64, dataclasses.asdict(reply()))
    with pytest.raises(GateStopped, match="call_budget_exhausted"):
        ledger.begin_attempt(rows[0]["doc_id"], "b" * 64)
    assert len(ledger.snapshot()["attempts"]) == count


@pytest.mark.parametrize("category,error,expected", [
    ("authentication", "http_401", "authentication"),
    ("request_rejected", "http_403", "authentication"),
    ("rate_limit", "http_429", "rate_limit"),
    ("request_rejected", "http_400", "request_rejected"),
])
def test_auth_and_non_retryable_provider_errors_stop_dispatch(tmp_path, category, error, expected):
    ledger, rows = ledger_fixture(tmp_path)
    ledger.claim(rows[0]["doc_id"])
    attempt, _ = ledger.begin_attempt(rows[0]["doc_id"], "b" * 64)
    ledger.finish_attempt(attempt, "c" * 64, dataclasses.asdict(reply(error=error, error_category=category)))
    assert ledger.snapshot()["settings"]["stop_reason"] == expected
    assert not ledger.claim(rows[1]["doc_id"])


def test_repeated_transport_failure_is_uncertain_and_stops_after_two(tmp_path):
    ledger, rows = ledger_fixture(tmp_path)
    for row in rows:
        assert ledger.claim(row["doc_id"])
        attempt, _ = ledger.begin_attempt(row["doc_id"], "b" * 64)
        ledger.finish_attempt(attempt, "c" * 64, dataclasses.asdict(reply(error="APITimeoutError", error_category="transport_timeout")))
    state = ledger.snapshot()
    assert state["settings"]["stop_reason"] == "repeated_transport_failure"
    assert all(item["state"] == "uncertain" for item in state["attempts"])


def test_explicit_provider_resume_preserves_all_attempts_and_never_retries_source(tmp_path):
    ledger, rows = ledger_fixture(tmp_path)
    ledger.claim(rows[0]["doc_id"])
    attempt, _ = ledger.begin_attempt(rows[0]["doc_id"], "b" * 64)
    ledger.finish_attempt(attempt, "c" * 64, dataclasses.asdict(reply(error="http_401", error_category="authentication")))
    ledger.recover_interrupted()
    with pytest.raises(GateStopped):
        ledger.acknowledge_stop("rate_limit")
    ledger.acknowledge_stop("authentication")
    assert not ledger.claim(rows[0]["doc_id"])
    assert ledger.claim(rows[1]["doc_id"])
    state = ledger.snapshot()
    assert len(state["attempts"]) == 1
    assert state["controls"][0]["reason"] == "authentication"


def test_simultaneous_reservations_cannot_exceed_global_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    # Threads exercise independent SQLite connections only, never OCR/runtime.
    ledger, rows = ledger_fixture(tmp_path, max_calls=1)
    for row in rows:
        ledger.claim(row["doc_id"])
    def reserve(row):
        try:
            return Ledger(ledger.path).begin_attempt(row["doc_id"], "b" * 64)
        except GateStopped:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, rows))
    assert sum(result is not None for result in results) == 1
    assert len(ledger.snapshot()["attempts"]) == 1


def test_exclusive_lock_releases_without_deleting_lock_file(tmp_path):
    path = tmp_path / "run.lock"
    with exclusive_run_lock(path), pytest.raises(GateStopped, match="already_running"), exclusive_run_lock(path):
        pytest.fail("Second owner acquired lock")
    assert path.exists()
    with exclusive_run_lock(path):
        pass


def test_profile_rejects_unready_vision_and_unvalidated_parallelism():
    assert freezer.validate_profile(freezer.DEFAULT_PROFILE)["workers"] == 1
    with pytest.raises(ValueError, match="visual_document_profile"):
        freezer.validate_profile({**freezer.DEFAULT_PROFILE, "visual_document_profile": "bounded_visual_v1"})
    with pytest.raises(ValueError, match="Parallel OCR"):
        freezer.validate_profile({**freezer.DEFAULT_PROFILE, "workers": 4})
    with pytest.raises(ValueError, match="max_calls"):
        freezer.validate_profile({**freezer.DEFAULT_PROFILE, "max_calls": 3000})


def test_parallel_receipt_must_match_exact_runtime_code_and_profile():
    code, runtime = {"commit": "test"}, {"test": "runtime"}
    profile = {**freezer.DEFAULT_PROFILE, "workers": 2}
    receipt = {"status": "passed", "workers": 2, "code_commit": "test",
               "runtime_sha256": freezer.digest_json(runtime), "profile_sha256": freezer.digest_json(profile),
               "peak_tree_rss_bytes": 1024, "minimum_available_memory_bytes": 2 * 1024 ** 3,
               "completed_sources": 2, "evidence_sha256": "a" * 64}
    profile["parallel_validation"] = receipt
    freezer.verify_parallel(profile, code, runtime)
    with pytest.raises(ValueError, match="resource validation"):
        freezer.verify_parallel(profile, code, {"test": "changed"})


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(freezer, "TARGET_SOURCES", 2)
    monkeypatch.setattr(freezer, "FAMILY_COUNTS", {"receipt": 2})
    monkeypatch.setattr(freezer, "code_receipt", lambda: {"commit": "test"})
    monkeypatch.setattr(freezer, "runtime_receipt", lambda: {"synthetic": "no OCR"})
    rows = [source_file(tmp_path, index, text=f"Total {index}") for index in range(2)]
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("\n".join(json.dumps({**row, "gold_path": "NEVER_OPEN_THIS"}) for row in rows), encoding="utf-8")
    path, sha = schema_file(tmp_path)
    protocol = tmp_path / "schema-protocol.json"
    freezer.write_new(protocol, {"schemas": {"receipt": {"path": str(path), "sha256": sha}}})
    profile = tmp_path / "profile.json"
    freezer.write_new(profile, freezer.DEFAULT_PROFILE)
    output = tmp_path / "gate"
    digest = freezer.freeze(cohort, protocol, profile, output)
    return output, digest, rows


def test_freeze_rehashes_all_distinct_originals_and_omits_label_paths(frozen):
    output, sha, _ = frozen
    protocol = freezer.verify_freeze(output, sha)
    assert len(protocol["sources"]) == 2
    assert "gold_path" not in (output / "protocol.json").read_text()
    assert protocol["labels_opened"] is False
    assert Ledger(output / "ledger.sqlite3").snapshot()["attempts"] == []


def test_changed_original_or_runtime_fails_before_run(frozen, monkeypatch):
    output, sha, rows = frozen
    monkeypatch.setattr(freezer, "runtime_receipt", lambda: {"changed": True})
    with pytest.raises(ValueError, match="runtime changed"):
        freezer.verify_freeze(output, sha)
    monkeypatch.setattr(freezer, "runtime_receipt", lambda: {"synthetic": "no OCR"})
    Path(rows[1]["source_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="source bytes"):
        freezer.verify_freeze(output, sha)
    assert Ledger(output / "ledger.sqlite3").snapshot()["attempts"] == []


def test_duplicate_source_content_is_rejected_even_with_other_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(freezer, "TARGET_SOURCES", 2)
    monkeypatch.setattr(freezer, "FAMILY_COUNTS", {"receipt": 2})
    rows = [source_file(tmp_path, index) for index in range(2)]
    with pytest.raises(ValueError, match="repeated original"):
        freezer.verify_sources(rows)


def test_changed_schema_cannot_resume(frozen):
    output, sha, _ = frozen
    (output / "schemas/receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="digest mismatch"):
        freezer.verify_freeze(output, sha)


def test_missing_product_interface_fails_freeze(monkeypatch):
    from idpo.product_auto import workflow
    monkeypatch.setattr(workflow, "process_auto", lambda input_path: None)
    with pytest.raises(ValueError, match="not implemented"):
        freezer.require_interfaces()


def sidecar_fixture():
    return {"pages": [{"page": 1, "text": "Total: 42"}], "reason": "confirmed_schema_requires_review",
            "document_status": "needs_review", "candidate": {"extracted_values": [
                {"field_id": "total", "value": 42, "status": "accepted"}]}}


@pytest.mark.parametrize("change", ["invalid_json", "length", "refusal", "no_call"])
def test_http_success_or_review_status_does_not_imply_valid_extraction(tmp_path, change):
    path, sha = schema_file(tmp_path)
    schema = load_confirmed_schema(path, sha)
    raw = dataclasses.asdict(reply())
    replies = [raw]
    if change == "invalid_json":
        raw["text"] = "not JSON"
    elif change == "length":
        raw["finish_reason"] = "length"
    elif change == "refusal":
        raw["refusal"] = True
    else:
        replies = []
    metric = gate.source_metrics(sidecar_fixture(), replies, schema)
    assert not metric["valid_full_coverage"]
    assert metric["requires_human_review"]


def test_valid_all_null_is_separate_from_nonempty_extraction(tmp_path):
    path, sha = schema_file(tmp_path)
    raw = dataclasses.asdict(reply())
    raw["text"] = '{"values":[{"field_id":"total","value":null,"page":null,"quote":null}]}'
    sidecar = sidecar_fixture()
    sidecar["candidate"]["extracted_values"][0].update(value=None, status="missing")
    metric = gate.source_metrics(sidecar, [raw], load_confirmed_schema(path, sha))
    assert metric["valid_full_coverage"] and metric["all_null"]
    assert metric["non_null_fields"] == 0


@pytest.mark.parametrize("complete", [False, True])
def test_segmented_coverage_counters_are_required_and_conflicts_separate(tmp_path, complete):
    path, sha = schema_file(tmp_path)
    sidecar = sidecar_fixture()
    sidecar.update(reason="long_document_scalar_conflict", long_document_plan={"plan_sha256": "a" * 64},
                   long_document_coverage={"source_char_count": 9, "planned_char_count": 9,
                       "completed_char_count": 9 if complete else 4, "planned_segments": 2,
                       "attempted_segments": 2, "completed_segments": 2 if complete else 1,
                       "full_source_covered": complete})
    metrics = gate.source_metrics(sidecar, [dataclasses.asdict(reply())] * 2, load_confirmed_schema(path, sha))
    assert metrics["valid_full_coverage"] is complete
    assert metrics["scalar_conflict"]


def test_raw_error_messages_are_redacted():
    payload = gate.sanitized_reply(reply(error="Bearer secret: sensitive payload", error_category="raw sensitive data"))
    assert payload["error"] == "provider_error" and payload["error_category"] == "provider_unknown"
    assert "secret" not in json.dumps(payload)


@pytest.mark.parametrize("text", ["Total: 42", ("Total: 42\n\n" + "padding words " * 1000 + "\n\n") * 3], ids=["short", "segmented"])
def test_actual_product_intake_writes_verified_receipts_with_mock_model_only(tmp_path, monkeypatch, text):
    # TXT avoids OCR entirely; the real product workflow and strict parser run.
    row = source_file(tmp_path, suffix=".txt", text=text)
    _path, sha = schema_file(tmp_path)
    protocol = {"profile": dict(freezer.DEFAULT_PROFILE), "schemas": {"receipt": {"path": "schema.json", "sha256": sha}}}
    ledger = Ledger(tmp_path / "ledger.sqlite3")
    ledger.initialize([row], "a" * 64, 2500)
    ledger.claim(row["doc_id"])

    class MockProvider:
        def __init__(self, **_):
            self.model, self.max_tokens = "innobot-luna-6", 8192
            self.client = SimpleNamespace(max_retries=0, close=lambda: None)

        def complete_json(self, **_):
            assert ledger.snapshot()["attempts"][-1]["state"] == "request_begun"
            return ModelReply(text='{"values":[{"field_id":"total","value":null,"page":null,"quote":null}]}',
                              latency_ms=1, finish_reason="stop", sdk_attempts=1, prompt_tokens=5, completion_tokens=5)

    monkeypatch.setattr(gate, "OpenAICompatibleChat", MockProvider)
    gate._run_source(str(tmp_path), row, protocol, "UNUSED_TEST_KEY")
    state = ledger.snapshot()
    assert state["sources"][0]["state"] == "sealed"
    assert 1 <= len(state["attempts"]) <= 4
    outcome = freezer.read_json(tmp_path / "outcomes" / f"{row['doc_id']}.json")
    assert outcome["metrics"]["valid_full_coverage"]
    assert outcome["metrics"]["all_null"]
    assert outcome["source_sha256"] == row["source_sha256"]


def test_resume_only_dispatches_unstarted_and_preserves_uncertain_denominator(frozen, monkeypatch):
    output, sha, rows = frozen
    ledger = Ledger(output / "ledger.sqlite3")
    ledger.claim(rows[0]["doc_id"])
    calls = []
    monkeypatch.setenv("SYNTHETIC_KEY", "unused")

    class Pool:
        def __init__(self, **kwargs):
            assert kwargs["max_workers"] == 1 and kwargs["mp_context"].get_start_method() == "spawn"
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def submit(self, function, output_s, row, protocol, key):
            calls.append(row["doc_id"])
            receipt = {"metrics": None, "output_files": {}}
            (output / "outcomes").mkdir(exist_ok=True)
            digest = freezer.write_new(output / "outcomes" / f"{row['doc_id']}.json", receipt)
            ledger.seal_source(row["doc_id"], digest, "synthetic_no_model")
            future = Future()
            future.set_result(row["doc_id"])
            return future

    monkeypatch.setattr(gate, "ProcessPoolExecutor", Pool)
    report = gate.run_gate(output, sha, api_key_env="SYNTHETIC_KEY", resume=True)
    assert calls == [rows[1]["doc_id"]]
    assert report["selected_originals"] == 2
    assert report["source_states"] == {"uncertain": 1, "sealed": 1}
    assert not report["operational_gate_passed"]
    assert report["originals_with_request_begun"] == 0
    assert list((output / "checkpoints").glob("*-batch-*.json"))


def test_modified_reply_receipt_blocks_resume(frozen):
    output, sha, rows = frozen
    protocol = freezer.read_json(output / "protocol.json")
    ledger = Ledger(output / "ledger.sqlite3")
    ledger.claim(rows[0]["doc_id"])
    (output / "requests").mkdir()
    request_sha = freezer.write_new(output / "requests" / "temporary.json", {"synthetic": True})
    (output / "requests/temporary.json").rename(output / "requests" / f"{request_sha}.json")
    attempt, _ = ledger.begin_attempt(rows[0]["doc_id"], request_sha)
    (output / "replies").mkdir()
    response_path = output / "replies/000001.json"
    response_sha = freezer.write_new(response_path, dataclasses.asdict(reply()))
    ledger.finish_attempt(attempt, response_sha, dataclasses.asdict(reply()))
    response_path.write_text("changed")
    with pytest.raises(ValueError, match="reply changed"):
        gate._verify_existing(output, ledger.snapshot(), protocol, sha)
