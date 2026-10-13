from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product_eval.constrained_output_diagnostic import (
    ARMS,
    CONTEXT_TOKENS,
    LOCK_PATH,
    check_inventory_lock,
    check_server_properties,
    evaluate_pairs,
    load_source_lock,
    request_body,
    response_format,
    response_shape_status,
    run_conformance_probe,
    verify_inputs,
)
from product_eval.contracts import ContractError, load_jsonl
from product_eval.oracle_schema_diagnostic import oracle_values_prompt, sha256_file


def test_response_format_is_minimal_and_phase_specific() -> None:
    ids = ["item_name", "item_price"]
    assert response_format("json_object", ids) == {"type": "json_object"}
    constrained = response_format("json_schema", ids)
    schema = constrained["schema"]
    item = schema["properties"]["values"]["items"]
    assert schema["required"] == ["values"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["values"]["maxItems"] == 2
    assert item["required"] == ["field_id", "value"]
    assert item["properties"]["field_id"]["enum"] == ids
    assert item["additionalProperties"] is False
    assert request_body("prompt", constrained)["response_format"] == constrained
    with pytest.raises(ValueError):
        response_format("json_schema", ["item_name", "item_name"])


@pytest.mark.parametrize(("reply", "expected"), [
    ('{"values":[{"field_id":"a","value":1}]}', "valid"),
    ('{"values":[{"field_id":"a","value":1,"value":2}]}', "duplicate_json_key"),
    ('{"values":[{"field_id":"a"}]}', "missing_value"),
    ('{"values":[{"field_id":"other","value":1}]}', "unknown_field_id"),
    ('{"values":[{"field_id":"a","value":1},{"field_id":"a","value":2}]}', "duplicate_field_id"),
    ('{"values":[{"field_id":"a","value":1,"extra":2}]}', "invalid_envelope"),
    ('{"values":[{"field_id":"a","value":NaN}]}', "invalid_json"),
    ('{"values":[{"field_id":"a","value":1e400}]}', "nonfinite_number"),
])
def test_local_shape_validator_fails_closed(reply: str, expected: str) -> None:
    assert response_shape_status(reply, ["a", "b"]) == expected


def test_source_lock_rejects_changed_cohort_before_inference(tmp_path: Path) -> None:
    assert len(load_source_lock(LOCK_PATH)["sources"]) == 12
    cohort = tmp_path / "cohort.jsonl"
    gold = tmp_path / "gold.jsonl"
    cohort.write_text("{}\n", encoding="utf-8")
    gold.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ContractError, match="SHA256"):
        verify_inputs(cohort_path=cohort, gold_path=gold, runs_root=tmp_path)


def test_sidecar_and_prompt_lock_reject_changes(tmp_path: Path) -> None:
    inventory = []
    locked = []
    gold = {}
    for index in range(12):
        doc_id = f"doc-{index:02d}"
        family = "registration-form" if index < 6 else "ad-buy-form"
        source_sha = f"{index:064x}"
        run_dir = tmp_path / "vrdu_v5_00"
        sidecar_path = run_dir / "docs" / doc_id / "result.json"
        sidecar_path.parent.mkdir(parents=True)
        pages = [{"page": 1, "text": f"Code {index}"}]
        sidecar_path.write_text(json.dumps({"pages": pages}), encoding="utf-8")
        gold[doc_id] = {"doc_id": doc_id, "gold_schema": [{"field_id": "code", "type": "string"}]}
        prompt = oracle_values_prompt(pages, [{"field_id": "code", "type": "string"}])
        locked.append({
            "doc_id": doc_id, "family": family, "source_sha256": source_sha,
            "v5_run_id": run_dir.name, "sidecar_sha256": sha256_file(sidecar_path),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        })
        inventory.append({
            "cohort": {"doc_id": doc_id, "family": family, "source_sha256": source_sha},
            "run_dir": run_dir, "sidecar_path": sidecar_path,
            "sidecar": {"pages": pages}, "ocr_chars": len(pages[0]["text"]),
        })
    check_inventory_lock(inventory, locked, gold)
    inventory[0]["sidecar_path"].write_text('{"pages":[]}', encoding="utf-8")
    with pytest.raises(ContractError, match="OCR sidecar"):
        check_inventory_lock(inventory, locked, gold)


def test_server_properties_require_pinned_build_model_and_context(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"fixture")
    props = {"build_info": "b11425-e117148a4", "model_path": str(model),
             "total_slots": 1, "default_generation_settings": {"n_ctx": CONTEXT_TOKENS}}
    check_server_properties(props, model)
    props["total_slots"] = 2
    with pytest.raises(ContractError, match="context/slot"):
        check_server_properties(props, model)
    props["total_slots"] = 1
    props["build_info"] = "different-build"
    with pytest.raises(ContractError, match="server build"):
        check_server_properties(props, model)


def test_conformance_probe_checks_for_enforced_enum() -> None:
    def good(_prompt: str, output_format: dict, arm: str) -> dict:
        assert arm == "probe"
        assert output_format == response_format("json_schema", ["probe_field"])
        return {"text": '{"values":[{"field_id":"probe_field","value":"test"}]}',
                "finish_reason": "stop", "error": None}

    assert run_conformance_probe(complete=good)["status"] == "passed"
    with pytest.raises(ContractError, match="conformance"):
        run_conformance_probe(complete=lambda _p, _f, _a: {
            "text": '{"values":[{"field_id":"wrong_field","value":"test"}]}',
            "finish_reason": "stop", "error": None,
        })


def test_paired_scoring_keeps_failed_and_truncated_docs_in_both_arms(tmp_path: Path) -> None:
    gold = load_jsonl(Path(__file__).resolve().parents[1] / "fixtures" / "gold.jsonl", kind="gold")
    inventory = []
    for index, doc_id in enumerate(gold):
        sidecar = {"pages": gold[doc_id]["pages"]}
        sidecar_path = tmp_path / f"{doc_id}.json"
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
        inventory.append({
            "cohort": {"doc_id": doc_id, "family": "fixture", "source_sha256": f"{index:064x}"},
            "sidecar": sidecar, "sidecar_path": sidecar_path,
            "run_dir": tmp_path / "vrdu_v5_fixture", "ocr_chars": len(sidecar["pages"][0]["text"]),
        })
    for arm in ARMS:
        (tmp_path / "paired" / arm / "replies").mkdir(parents=True)
    calls = []

    def complete(prompt: str, _format: dict, arm: str) -> dict:
        calls.append((arm, prompt))
        if "Service request" in prompt and arm == "json_object":
            return {"text": "{", "finish_reason": "length", "error": None,
                    "latency_ms": 2, "prompt_tokens": 20, "completion_tokens": 3}
        if "Service request" in prompt and arm == "json_schema":
            return {"text": '{"values":[{"field_id":"account_id","value":"A-9","page":1,"quote":"A-9"}]}',
                    "finish_reason": "stop", "error": None,
                    "latency_ms": 2, "prompt_tokens": 20, "completion_tokens": 20}
        return {"text": '{"values":[{"field_id":"invoice_number","value":"INV-7","page":1,"quote":"INV-7"}]}',
                "finish_reason": "stop", "error": None,
                "latency_ms": 2, "prompt_tokens": 20, "completion_tokens": 20}

    token_counts = []

    def count_tokens(prompt: str) -> int:
        token_counts.append(prompt)
        return 100

    reports = evaluate_pairs(inventory=inventory, gold=gold, output_dir=tmp_path / "paired",
                             complete=complete, count_tokens=count_tokens)
    assert len(calls) == 4
    assert len(token_counts) == 2  # shared prompt preflight, not one per arm
    assert [row[0] for row in calls] == ["json_object", "json_schema", "json_schema", "json_object"]
    for arm in ARMS:
        candidates = load_jsonl(tmp_path / "paired" / arm / "candidates.jsonl", kind="candidate")
        assert set(candidates) == set(gold)
        assert reports[arm]["score"]["documents"]["gold"] == 2
        assert reports[arm]["score"]["documents"]["candidate"] == 2
    assert reports["json_object"]["reasons"]["truncated_model_response"] == 1
    assert reports["json_schema"]["score"]["values"]["tp"] > reports["json_object"]["score"]["values"]["tp"]
    assert reports["json_object"]["by_family"]["fixture"]["documents"]["candidate"] == 2
    assert reports["json_schema"]["latency_ms_sum"] == 4


def test_context_rejection_still_scores_every_doc(tmp_path: Path) -> None:
    gold = load_jsonl(Path(__file__).resolve().parents[1] / "fixtures" / "gold.jsonl", kind="gold")
    doc_id = "synthetic-request-1"
    sidecar = {"pages": gold[doc_id]["pages"]}
    path = tmp_path / "sidecar.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    inventory = [{"cohort": {"doc_id": doc_id, "family": "fixture", "source_sha256": "a" * 64},
                  "sidecar": sidecar, "sidecar_path": path, "run_dir": tmp_path / "vrdu_v5_fixture",
                  "ocr_chars": len(sidecar["pages"][0]["text"])}]
    for arm in ARMS:
        (tmp_path / "paired" / arm / "replies").mkdir(parents=True)
    reports = evaluate_pairs(inventory=inventory, gold={doc_id: gold[doc_id]}, output_dir=tmp_path / "paired",
                             complete=lambda *_args: pytest.fail("context rejection must not call model"),
                             count_tokens=lambda _prompt: CONTEXT_TOKENS)
    for arm in ARMS:
        assert reports[arm]["model_calls"] == 0
        assert reports[arm]["score"]["documents"]["candidate"] == 1
        assert reports[arm]["reasons"]["local_model_error"] == 1


def test_tokenizer_and_adapter_errors_remain_in_denominator(tmp_path: Path) -> None:
    gold = load_jsonl(Path(__file__).resolve().parents[1] / "fixtures" / "gold.jsonl", kind="gold")
    doc_id = "synthetic-request-1"
    sidecar = {"pages": gold[doc_id]["pages"]}
    path = tmp_path / "sidecar.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    inventory = [{"cohort": {"doc_id": doc_id, "family": "fixture", "source_sha256": "a" * 64},
                  "sidecar": sidecar, "sidecar_path": path, "run_dir": tmp_path / "vrdu_v5_fixture",
                  "ocr_chars": len(sidecar["pages"][0]["text"])}]

    def fail_tokens(_prompt: str) -> int:
        raise TimeoutError("source text must not appear in a diagnostic")

    def fail_model(_prompt: str, _format: dict, _arm: str) -> dict:
        raise OSError("source text must not appear in a diagnostic")

    for label, counter, completion, expected_calls in (
        ("tokenizer", fail_tokens, fail_model, 0),
        ("adapter", lambda _prompt: 100, fail_model, 1),
    ):
        output = tmp_path / label
        for arm in ARMS:
            (output / arm / "replies").mkdir(parents=True)
        reports = evaluate_pairs(inventory=inventory, gold={doc_id: gold[doc_id]}, output_dir=output,
                                 complete=completion, count_tokens=counter)
        for arm in ARMS:
            assert reports[arm]["model_calls"] == expected_calls
            assert reports[arm]["score"]["documents"]["candidate"] == 1
            diagnostics = [json.loads(line) for line in (output / arm / "diagnostics.jsonl").read_text().splitlines()]
            assert diagnostics[0]["reason"] == "local_model_error"
            assert "source text" not in json.dumps(diagnostics)
