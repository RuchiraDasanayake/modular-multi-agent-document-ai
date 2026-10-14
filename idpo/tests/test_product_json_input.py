"""Authored JSON sources cannot bypass product shape or logical-work limits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from idpo.product_auto import json_input
from idpo.product_auto.brief_draft import _sample_text
from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot


def entry(doc_id: str = "synthetic") -> dict:
    return {"doc_id": doc_id, "pages": [{"number": 1, "text": "Name: Alpha"}]}


def confirmed(tmp_path: Path):
    directory = tmp_path / "schema"
    directory.mkdir()
    path, digest = snapshot(directory, fields=[
        {"field_id": "name", "type": "string", "description": "Name", "example_values": []},
    ])
    return load_confirmed_schema(path, digest)


class Model:
    model = "synthetic-no-network"

    def __init__(self, *, forbidden: bool = False):
        self.calls = 0
        self.forbidden = forbidden

    def complete_json(self, **kwargs):
        self.calls += 1
        if self.forbidden:
            pytest.fail("An inadmissible JSON source reached model execution")
        return ModelReply(text='{"values":{"name":{"value":"Alpha","page":1,"quote":"Alpha"}}}',
                          latency_ms=1, finish_reason="stop", sdk_attempts=1)


def results(run: dict) -> tuple[list[dict], list[dict], list[dict]]:
    root = Path(run["run_dir"])
    candidates = [json.loads(line) for line in (root / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    manifest = [json.loads(line) for line in (root / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    sidecars = [json.loads((root / "docs" / c["doc_id"] / "result.json").read_text(encoding="utf-8"))
                for c in candidates]
    assert json.loads((root / "run.json").read_text(encoding="utf-8"))["doc_count"] == len(candidates)
    return candidates, sidecars, manifest


@pytest.mark.parametrize("page_patch", [
    {"text": None}, {"text": []}, {"text": 7}, {"raw_text": {"value": "Alpha"}},
    {"number": None}, {"number": "1"}, {"number": True}, {"number": 0},
    {"number": 2**53},
], ids=["null-text", "array-text", "number-text", "object-raw-text", "null-page",
        "string-page", "boolean-page", "zero-page", "unsafe-page"])
def test_malformed_json_is_a_parse_failure_and_next_original_completes(
    tmp_path: Path, page_patch: dict,
) -> None:
    schema = confirmed(tmp_path)
    sources = tmp_path / "sources"
    sources.mkdir()
    payload = entry()
    payload["pages"][0].update(page_patch)
    (sources / "00.json").write_text(json.dumps(payload), encoding="utf-8")
    (sources / "01.txt").write_text("Name: Alpha", encoding="utf-8")
    model = Model()

    run = process_auto(sources, model=model, confirmed_schema=schema,
                       response_format_profile="strict_confirmed_values_v2", output_root=tmp_path / "runs")
    candidates, sidecars, _ = results(run)

    assert model.calls == 1
    assert [c["document_status"] for c in candidates] == ["failed", "needs_review"]
    assert sidecars[0]["reason"] == "parse_failed"
    assert candidates[1]["extracted_values"][0]["value"] == "Alpha"


def test_two_json_documents_and_text_keep_source_indices_and_entry_hashes(tmp_path: Path) -> None:
    schema = confirmed(tmp_path)
    sources = tmp_path / "sources"
    sources.mkdir()
    entries = [entry("first"), entry("second")]
    entries[0]["pages"][0].update(image_path="C:/not-a-source.png", metadata={"ignored": True})
    source = sources / "00.json"
    source.write_text(json.dumps(entries), encoding="utf-8")
    (sources / "01.txt").write_text("Name: Alpha", encoding="utf-8")
    model = Model()

    run = process_auto(sources, model=model, confirmed_schema=schema,
                       response_format_profile="strict_confirmed_values_v2", output_root=tmp_path / "runs")
    candidates, sidecars, manifest = results(run)

    assert model.calls == len(candidates) == 3
    assert [r["source_index"] for r in manifest] == [0, 1, 0]
    for index, payload in enumerate(entries):
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        assert manifest[index]["source_sha256"] == hashlib.sha256(raw).hexdigest()
        assert manifest[index]["source_size_bytes"] == len(raw)
        assert manifest[index]["source_hash_kind"] == "canonical_json_entry"
        expected_id = hashlib.sha256(
            f"00.json\0{hashlib.sha256(raw).hexdigest()}\0{index}".encode()
        ).hexdigest()[:32]
        assert candidates[index]["doc_id"] == expected_id
    assert sidecars[0]["pages"] == [{"page": 1, "text": "Name: Alpha"}]


def test_container_entry_limit_records_one_unsupported_original_without_model(tmp_path: Path) -> None:
    schema = confirmed(tmp_path)
    source = tmp_path / "many.json"
    source.write_text(json.dumps([entry(str(i)) for i in range(5001)]), encoding="utf-8")
    model = Model(forbidden=True)

    run = process_auto(source, model=model, confirmed_schema=schema,
                       response_format_profile="strict_confirmed_values_v2", output_root=tmp_path / "runs")
    candidates, sidecars, _ = results(run)

    assert model.calls == 0
    assert len(candidates) == 1 and candidates[0]["document_status"] == "unsupported"
    assert sidecars[0]["reason"] == "json_document_limit_exceeded"


def test_whole_run_logical_limit_is_checked_before_any_model_or_run_directory(tmp_path: Path) -> None:
    schema = confirmed(tmp_path)
    sources = tmp_path / "sources"
    sources.mkdir()
    for name, count in [("00.json", 2500), ("01.json", 2501)]:
        (sources / name).write_text(json.dumps([entry(str(i)) for i in range(count)]), encoding="utf-8")
    model = Model(forbidden=True)

    with pytest.raises(ValueError, match="5000 logical"):
        process_auto(sources, model=model, confirmed_schema=schema,
                     response_format_profile="strict_confirmed_values_v2", output_root=tmp_path / "runs")
    assert model.calls == 0
    assert not (tmp_path / "runs").exists()


def test_json_sample_uses_the_same_container_entry_limit(tmp_path: Path) -> None:
    source = tmp_path / "many.json"
    source.write_text(json.dumps([entry(str(i)) for i in range(5001)]), encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="json_document_limit_exceeded"):
        _sample_text(source, digest)


@pytest.mark.parametrize("payload,reason", [
    ([entry("valid"), {"doc_id": "bad", "pages": [{"number": 1, "text": None}]}], "text must be a string"),
    ([entry(str(i)) for i in range(5001)], "json_document_limit_exceeded"),
    ({"doc_id": "many", "pages": [{"number": i + 1, "text": "Alpha"} for i in range(51)]}, "too_many_pages"),
], ids=["late-malformed-entry", "logical-count", "page-count"])
def test_complete_container_validation_precedes_page_or_document_allocation(
    tmp_path: Path, monkeypatch, payload: object, reason: str,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    allocations = []

    def forbidden(*args, **kwargs):
        allocations.append(True)
        raise AssertionError("Invalid container allocated product documents")

    monkeypatch.setattr(json_input, "Page", forbidden)
    monkeypatch.setattr(json_input, "Document", forbidden)
    with pytest.raises(ValueError, match=reason):
        json_input.load_product_json(source, expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    assert allocations == []


@pytest.mark.parametrize("raw", [
    '{"doc_id":"x","pages":[{"text":"Alpha"}],"extra":NaN}',
    '[{"doc_id":"x","pages":[{"text":"Alpha"}],"extra":Infinity}]',
    '{"doc_id":"x","pages":[{"text":"Alpha"}],"extra":-Infinity}',
    '{"doc_id":"x","pages":[{"text":"Alpha"}],"extra":1e400}',
    '{"doc_id":"x","doc_id":"y","pages":[{"text":"Alpha"}]}',
    '{"doc_id":"x","pages":[{"text":"\\ud800"}]}',
    '{"doc_id":"x","pages":[{"number":1,"text":"Alpha"},{"number":1,"text":"Beta"}]}',
    '{"doc_id":[],"pages":[{"text":"Alpha"}]}',
    '[]', 'null', '{"doc_id":"x","pages":[]}',
], ids=["nan", "infinity", "negative-infinity", "overflow", "duplicate-property",
        "surrogate", "duplicate-pages", "nonstring-id", "empty-array", "null-root", "empty-pages"])
def test_invalid_standard_json_or_shape_is_one_preflight_failure_unit(
    tmp_path: Path, monkeypatch, raw: str,
) -> None:
    source = tmp_path / "source.json"
    source.write_text(raw, encoding="utf-8")
    monkeypatch.setattr(json_input, "Document", lambda **kwargs: pytest.fail("Preflight allocated a document"))
    result = json_input.preflight_json_input(source)
    assert result.logical_count == 1
    assert result.reason == "parse_failed"


def test_safe_nonconsecutive_page_ids_and_ignored_metadata_are_preserved(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    payload = {"doc_id": "stable-id", "metadata": {"ignored": True}, "pages": [
        {"number": 2, "text": "Alpha", "raw_text": None, "image_path": "C:/private.png", "metadata": {"x": 1}},
        {"number": 9, "text": "Beta", "raw_text": "Beta"},
    ]}
    source.write_text(json.dumps(payload), encoding="utf-8")
    documents, receipts = json_input.load_product_json(
        source, expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    assert documents[0].doc_id == "stable-id"
    assert [page.number for page in documents[0].pages] == [2, 9]
    assert all(page.image_path is None and page.metadata == {} for page in documents[0].pages)
    assert documents[0].metadata == {}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    assert receipts == [(hashlib.sha256(raw).hexdigest(), len(raw), "canonical_json_entry")]


def test_preflight_accepts_5000_units_without_building_any_documents(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps([entry(str(i)) for i in range(5000)]), encoding="utf-8")
    monkeypatch.setattr(json_input, "Document", lambda **kwargs: pytest.fail("Preflight allocated a document"))
    result = json_input.preflight_json_input(source)
    assert result.logical_count == 5000 and result.reason is None


def test_source_change_is_rejected_before_document_construction(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps(entry("first")), encoding="utf-8")
    admitted = json_input.preflight_json_input(source)
    source.write_text(json.dumps([entry("first"), entry("new")]), encoding="utf-8")
    monkeypatch.setattr(json_input, "Document", lambda **kwargs: pytest.fail("Changed source allocated a document"))
    with pytest.raises(ValueError, match="changed after admission"):
        json_input.load_product_json(source, expected_source_sha256=admitted.source_sha256)


def test_sample_constructs_only_two_after_validating_the_entire_container(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.json"
    source.write_text(json.dumps([entry(str(i)) for i in range(3)]), encoding="utf-8")
    original = json_input.Document
    allocations = []

    def counted(**kwargs):
        allocations.append(kwargs["doc_id"])
        return original(**kwargs)

    monkeypatch.setattr(json_input, "Document", counted)
    text, parser = _sample_text(source, hashlib.sha256(source.read_bytes()).hexdigest())
    assert text == "Name: Alpha\nName: Alpha" and parser == "json-pages"
    assert allocations == ["0", "1"]


def test_over_page_limit_in_a_later_entry_abstains_for_the_whole_original(tmp_path: Path) -> None:
    schema = confirmed(tmp_path)
    source = tmp_path / "source.json"
    source.write_text(json.dumps([entry("first"), {
        "doc_id": "second", "pages": [{"number": i + 1, "text": "Alpha"} for i in range(51)],
    }]), encoding="utf-8")
    model = Model(forbidden=True)
    run = process_auto(source, model=model, confirmed_schema=schema,
                       response_format_profile="strict_confirmed_values_v2", output_root=tmp_path / "runs")
    candidates, sidecars, _ = results(run)
    assert model.calls == 0 and len(candidates) == 1
    assert candidates[0]["document_status"] == "unsupported"
    assert sidecars[0]["reason"] == "too_many_pages"
