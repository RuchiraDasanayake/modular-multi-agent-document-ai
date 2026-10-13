from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

from product_eval.schema_only_scorer import (
    SchemaContractError,
    main,
    normalize_name,
    read_json,
    score_cohort,
)

LOCK_SHA = "a" * 64


def _inputs() -> tuple[dict, dict, dict, dict]:
    lock = {"contract_version": 1, "sources": [
        {"doc_id": f"synthetic-{index:02}", "source_sha256": f"{index:064x}"}
        for index in range(1, 13)
    ]}
    gold = {"contract_version": 1, "source_lock_sha256": LOCK_SHA, "documents": []}
    for index in range(1, 13):
        doc_id = f"synthetic-{index:02}"
        if index == 1:
            fields = [
                {"field_id": "invoice_number", "type": "identifier", "group": None},
                {"field_id": "item_name", "type": "string", "group": "items"},
                {"field_id": "item_quantity", "type": "integer", "group": "items"},
                {"field_id": "item_amount", "type": "currency", "group": "items"},
            ]
            groups = [{"group_id": "items", "kind": "array[object]"}]
        else:
            fields = [{"field_id": f"source_field_{index}", "type": "string", "group": None}]
            groups = []
        gold["documents"].append({"doc_id": doc_id, "source_sha256": f"{index:064x}", "gold_complete": True,
                                  "fields": fields, "groups": groups})
    candidate = {"contract_version": 1, "source_lock_sha256": LOCK_SHA,
                 "documents": [{"doc_id": "synthetic-01", "source_sha256": f"{1:064x}",
                                "status": "ok", "fields": [
                     {"field_id": "invoice_number", "type": "identifier", "group": None},
                     {"field_id": "itemName", "type": "string", "group": "rows"},
                     {"field_id": "qty", "type": "integer", "group": "rows"},
                     {"field_id": "line_total", "type": "currency", "group": "rows"},
                 ], "groups": [{"group_id": "rows", "kind": "array[object]"}]}]}
    aliases = {"contract_version": 1, "entries": [
        {"field_id": "item_quantity", "aliases": ["qty"]},
        {"field_id": "item_amount", "aliases": ["line_total"]},
    ]}
    return lock, gold, candidate, aliases


def _score(inputs: tuple[dict, dict, dict, dict]) -> dict:
    return score_cohort(*inputs, source_lock_sha256=LOCK_SHA)


def test_twelve_source_denominator_exact_alias_and_linked_pairs() -> None:
    report = _score(_inputs())
    assert report["scope"] == "schema_only"
    assert report["planned_sources"] == 12
    assert report["candidate_statuses"] == {"ok": 1, "missing": 11}
    assert report["summary"]["exact"]["fields"]["tp"] == 1
    assert report["summary"]["exact"]["fields"]["fn"] == 14
    assert report["summary"]["predeclared_alias"]["fields"] == {
        "tp": 4, "fp": 0, "fn": 11, "precision": 1.0, "recall": 4 / 15,
        "f1": 8 / 19, "type_correct": 4, "group_role_correct": 4,
    }
    assert report["summary"]["exact"]["linked_pairs"]["tp"] == 0
    assert report["summary"]["predeclared_alias"]["linked_pairs"]["tp"] == 3
    assert report["summary"]["predeclared_alias"]["linked_groups"] == {
        "gold": 1, "hit": 1, "coverage_hit": 1,
    }


def test_groups_must_be_same_explicit_array_of_objects() -> None:
    inputs = list(_inputs())
    record = inputs[2]["documents"][0]
    record["groups"].append({"group_id": "other_rows", "kind": "array[object]"})
    record["fields"][3]["group"] = "other_rows"
    scores = _score(tuple(inputs))["per_document"][0]["scores"]["predeclared_alias"]
    assert scores["fields"]["tp"] == 4
    assert scores["linked_pairs"]["tp"] == 1
    assert scores["linked_pairs"]["fn"] == 2
    assert scores["linked_groups"]["hit"] == 0

    record["groups"][0]["kind"] = "object"
    scores = _score(tuple(inputs))["per_document"][0]["scores"]["predeclared_alias"]
    assert scores["linked_pairs"]["tp"] == 0


def test_alias_collision_fails_closed_without_using_gold_to_choose() -> None:
    inputs = list(_inputs())
    record = inputs[2]["documents"][0]
    record["fields"].append({"field_id": "item_quantity", "type": "integer", "group": "rows"})
    scores = _score(tuple(inputs))["per_document"][0]["scores"]["predeclared_alias"]
    assert scores["alias_collisions"] == ["item_quantity"]
    assert scores["matches"]["item_quantity"] == "item_quantity"
    assert "qty" in scores["unmatched_predicted"]
    assert scores["fields"]["fp"] == 1

    inputs = list(_inputs())
    inputs[3]["entries"][0]["aliases"].append("item_qty")
    inputs[2]["documents"][0]["fields"].append(
        {"field_id": "item_qty", "type": "integer", "group": "rows"}
    )
    scores = _score(tuple(inputs))["per_document"][0]["scores"]["predeclared_alias"]
    assert scores["alias_collisions"] == ["item_quantity"]
    assert "qty" not in scores["matches"] and "item_qty" not in scores["matches"]
    assert scores["linked_pairs"]["tp"] == 1


def test_field_name_match_does_not_hide_wrong_type() -> None:
    inputs = list(_inputs())
    inputs[2]["documents"][0]["fields"][2]["type"] = "string"
    score = _score(tuple(inputs))["per_document"][0]["scores"]["predeclared_alias"]["fields"]
    assert score["tp"] == 4
    assert score["type_correct"] == 3


def test_extra_predicted_leaf_blocks_strict_group_hit() -> None:
    inputs = list(_inputs())
    inputs[2]["documents"][0]["fields"].append(
        {"field_id": "unrequested_note", "type": "string", "group": "rows"}
    )
    score = _score(tuple(inputs))["per_document"][0]["scores"]["predeclared_alias"]
    assert score["linked_groups"] == {"gold": 1, "hit": 0, "coverage_hit": 1}
    assert score["linked_pairs"]["tp"] == 3
    assert score["linked_pairs"]["fp"] == 3


def test_duplicate_or_malformed_candidate_is_failure_in_all_twelve_denominators() -> None:
    inputs = list(_inputs())
    record = inputs[2]["documents"][0]
    record["fields"].append(copy.deepcopy(record["fields"][0]))
    report = _score(tuple(inputs))
    assert report["candidate_statuses"] == {"invalid_schema": 1, "missing": 11}
    assert report["summary"]["predeclared_alias"]["fields"]["tp"] == 0
    assert report["summary"]["predeclared_alias"]["fields"]["fn"] == 15
    assert report["summary"]["predeclared_alias"]["linked_pairs"]["fn"] == 3

    inputs = list(_inputs())
    inputs[2]["documents"].append(copy.deepcopy(inputs[2]["documents"][0]))
    report = _score(tuple(inputs))
    assert report["candidate_statuses"]["invalid_duplicate_doc"] == 1
    assert report["summary"]["exact"]["fields"]["tp"] == 0

    inputs = list(_inputs())
    inputs[2]["documents"][0] = {"doc_id": "synthetic-01", "source_sha256": f"{1:064x}",
                                  "status": "malformed"}
    report = _score(tuple(inputs))
    assert report["candidate_statuses"]["malformed"] == 1
    assert report["summary"]["predeclared_alias"]["fields"]["fn"] == 15


def test_gold_and_alias_contract_are_strict() -> None:
    inputs = list(_inputs())
    inputs[1]["documents"].pop()
    with pytest.raises(SchemaContractError, match="exactly the planned 12"):
        _score(tuple(inputs))

    inputs = list(_inputs())
    inputs[3]["entries"].append({"field_id": "item_name", "aliases": ["qty"]})
    with pytest.raises(SchemaContractError, match="alias collision"):
        _score(tuple(inputs))

    inputs = list(_inputs())
    inputs[2]["documents"][0]["doc_id"] = "not-planned"
    with pytest.raises(SchemaContractError, match="unknown doc_id"):
        _score(tuple(inputs))

    inputs = list(_inputs())
    inputs[2]["documents"][0]["source_sha256"] = "f" * 64
    with pytest.raises(SchemaContractError, match="source hash differs"):
        _score(tuple(inputs))


def test_unhashable_model_shapes_fail_closed_per_document() -> None:
    for location, replacement in (("status", []), ("type", []), ("group", []), ("kind", [])):
        inputs = list(_inputs())
        record = inputs[2]["documents"][0]
        if location == "status":
            record["status"] = replacement
            expected = "invalid_status"
        elif location == "kind":
            record["groups"][0]["kind"] = replacement
            expected = "invalid_schema"
        else:
            record["fields"][0][location] = replacement
            expected = "invalid_schema"
        report = _score(tuple(inputs))
        assert report["candidate_statuses"][expected] == 1
        assert report["summary"]["exact"]["fields"]["fn"] == 15

    inputs = list(_inputs())
    inputs[1]["documents"][0]["fields"][0]["type"] = []
    with pytest.raises(SchemaContractError, match="unsupported type"):
        _score(tuple(inputs))


def test_incomplete_gold_withholds_precision_but_keeps_recall() -> None:
    inputs = list(_inputs())
    inputs[1]["documents"][1]["gold_complete"] = False
    report = _score(tuple(inputs))
    assert report["summary"]["exact"]["fields"]["precision"] is None
    assert report["summary"]["exact"]["fields"]["f1"] is None
    assert report["summary"]["exact"]["fields"]["recall"] == 1 / 15
    assert report["per_document"][0]["scores"]["exact"]["fields"]["precision"] == 0.25


def test_literal_normalization_duplicate_keys_and_nonfinite_are_rejected(tmp_path: Path) -> None:
    assert normalize_name("ItemName") == "item_name"
    assert normalize_name("Ｉｔｅｍ Quantity") == "item_quantity"
    bad = tmp_path / "bad.json"
    bad.write_text('{"contract_version":1,"contract_version":1}', encoding="utf-8")
    with pytest.raises(SchemaContractError, match="duplicate JSON key"):
        read_json(bad)
    bad.write_text('{"number": NaN}', encoding="utf-8")
    with pytest.raises(SchemaContractError, match="non-finite"):
        read_json(bad)


def test_cli_binds_file_hashes_and_refuses_report_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock, gold, candidate, aliases = _inputs()
    paths = {name: tmp_path / f"{name}.json" for name in ("lock", "gold", "candidate", "aliases")}
    paths["lock"].write_text(json.dumps(lock), encoding="utf-8")
    lock_sha = hashlib.sha256(paths["lock"].read_bytes()).hexdigest()
    gold["source_lock_sha256"] = lock_sha
    candidate["source_lock_sha256"] = lock_sha
    for name, payload in (("gold", gold), ("candidate", candidate), ("aliases", aliases)):
        paths[name].write_text(json.dumps(payload), encoding="utf-8")
    report_path = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", ["schema_only_scorer", "--source-lock", str(paths["lock"]),
                                      "--gold", str(paths["gold"]), "--candidate", str(paths["candidate"]),
                                      "--aliases", str(paths["aliases"]), "--report", str(report_path)])
    assert main() == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["input_sha256"]["source_lock"] == lock_sha
    assert report["planned_sources"] == 12
    with pytest.raises(SystemExit, match="2"):
        main()
