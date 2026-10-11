from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_eval.oracle_schema_diagnostic import (
    MAX_MODEL_CHARS,
    _local_url,
    evaluate_document,
    readiness,
    runtime_grounding,
    selected_cohort,
    sidecar_inventory,
)


def test_oracle_prompt_exposes_only_supported_gold_ids_and_types() -> None:
    pages = [{"page": 1, "text": "Code ABC\nItem: Pencil\n"}]
    gold = {
        "doc_id": "doc-a",
        "gold_schema": [
            {"field_id": "code", "type": "string", "critical": False},
            {"field_id": "item", "type": "array[object]", "critical": False},
            {"field_id": "aliases", "type": "array[string]", "critical": False},
        ],
        "gold_values": [{"field_id": "code", "value": "SECRET_ORACLE_VALUE"}],
    }
    prompts: list[str] = []

    def complete(prompt: str) -> dict[str, object]:
        prompts.append(prompt)
        return {
            "text": json.dumps({"values": [
                {"field_id": "code", "value": "ABC", "page": 1, "quote": "ABC"},
                {"field_id": "item", "value": [{"row": 0, "value": "Pencil", "page": 1, "quote": "Pencil"}]},
            ]}),
            "finish_reason": "stop",
            "error": None,
            "latency_ms": 1,
            "prompt_tokens": 20,
            "completion_tokens": 20,
        }

    candidate, diagnostic = evaluate_document(doc_id="doc-a", pages=pages, gold_record=gold, complete=complete)

    assert len(prompts) == 1
    assert "SECRET_ORACLE_VALUE" not in prompts[0]
    assert '"field_id": "aliases"' not in prompts[0]
    assert diagnostic["unsupported_gold_field_ids"] == ["aliases"]
    values = {value["field_id"]: value for value in candidate["extracted_values"]}
    assert values["code"]["status"] == "accepted"
    assert values["code"]["evidence"] == {"page": 1, "start": 5, "end": 8, "quote": "ABC"}
    assert values["item"]["value"][0]["status"] == "accepted"
    assert values["aliases"]["status"] == "needs_review"
    assert candidate["document_status"] == "needs_review"
    assert runtime_grounding(candidate, pages) == {
        "accepted_scalars": 1,
        "grounded_scalars": 1,
        "accepted_linked_cells": 1,
        "grounded_linked_cells": 1,
    }


def test_over_limit_sidecar_never_calls_model() -> None:
    gold = {"doc_id": "doc-b", "gold_schema": [{"field_id": "title", "type": "string"}]}

    def no_call(_: str) -> dict[str, object]:
        raise AssertionError("over-limit document must not call model")

    candidate, diagnostic = evaluate_document(
        doc_id="doc-b", pages=[{"page": 1, "text": "x" * (MAX_MODEL_CHARS + 1)}],
        gold_record=gold, complete=no_call,
    )
    assert diagnostic["reason"] == "document_exceeds_auto_limit"
    assert diagnostic["model_call"] is None
    assert candidate["extracted_values"][0]["status"] == "needs_review"


def test_sha_rank_selection_and_completed_sidecar_gate(tmp_path: Path) -> None:
    rows = []
    for family_number, family in enumerate(("registration-form", "ad-buy-form")):
        for index in range(7):
            rows.append({
                "family": family,
                "doc_id": f"{family}-{index}",
                "source_sha256": f"{family_number * 100 + index:064x}",
            })
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("".join(json.dumps(row) + "\n" for row in reversed(rows)), encoding="utf-8")
    selected = selected_cohort(cohort)
    assert len(selected) == 12
    assert {item["doc_id"] for item in selected} == {
        f"{family}-{index}" for family in ("registration-form", "ad-buy-form") for index in range(6)
    }

    runs_root = tmp_path / "product_runs"
    run_dir = runs_root / "vrdu_v5_reg_00"
    doc_dir = run_dir / "docs" / selected[0]["doc_id"]
    doc_dir.mkdir(parents=True)
    (doc_dir / "result.json").write_text(json.dumps({
        "source_sha256": selected[0]["source_sha256"],
        "pages": [{"page": 1, "text": "Native OCR"}],
    }), encoding="utf-8")
    inventory = sidecar_inventory(selected, runs_root)
    assert readiness(inventory)["sidecars_present"] == 1
    assert readiness(inventory)["sidecars_with_text"] == 1
    assert not readiness(inventory)["ready"]
    (run_dir / "run.json").write_text("{}", encoding="utf-8")
    assert readiness(sidecar_inventory(selected, runs_root))["sidecars_in_completed_runs"] == 1


@pytest.mark.parametrize("url", [
    "https://example.com/v1/chat/completions",
    "http://example.com/v1/chat/completions",
    "http://127.0.0.1:18081/other",
])
def test_cloud_or_wrong_model_url_is_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="local HTTP"):
        _local_url(url)
