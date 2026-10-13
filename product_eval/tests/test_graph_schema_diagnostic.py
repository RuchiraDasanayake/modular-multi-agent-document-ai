from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_eval.contracts import ContractError
from product_eval.graph_schema_diagnostic import (
    ALIAS_PATH,
    LOCK_PATH,
    MAX_CALLS,
    BoundedLocalCalls,
    _loopback_base,
    load_aliases,
    project_fields,
    score_schema,
    summarize_scores,
)


def _spec(*, separate_groups: bool = False) -> dict:
    return {
        "root": "Receipt",
        "models": [
            {"name": "Receipt", "fields": [
                {"name": "total_price", "type": "str", "normalizer": "currency"},
                {"name": "items", "type": "Item", "is_list": True},
                *([{"name": "charges", "type": "Charge", "is_list": True}] if separate_groups else []),
            ]},
            {"name": "Item", "fields": [
                {"name": "item_name", "type": "str"},
                *([] if separate_groups else [{"name": "item_price", "type": "str", "normalizer": "currency"}]),
            ]},
            *([{"name": "Charge", "fields": [{"name": "item_price", "type": "str"}]}] if separate_groups else []),
        ],
    }


def test_source_fixture_roles_are_disjoint_and_development_only() -> None:
    rows = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["sources"]
    assert len(rows) == len({row["doc_id"] for row in rows}) == len({row["source_sha256"] for row in rows}) == 12
    for family in ("registration-form", "ad-buy-form", "receipt"):
        subset = [row for row in rows if row["family"] == family]
        assert [row["role"] for row in subset] == ["example", "example", "scored", "scored"]
        assert len({row["source_sha256"] for row in subset}) == 4
    assert all(row["run_id"] == "cord_v2_development_v1" for row in rows if row["family"] == "receipt")


def test_alias_map_is_predeclared_collision_free_and_does_not_relabel_unrelated_fields() -> None:
    definitions = load_aliases(ALIAS_PATH)
    assert definitions["receipt"]["total_amount"]["aliases"] == ["total_price", "grand_total", "total_due"]
    assert "price" not in {a for d in definitions["receipt"].values() for a in d["aliases"]}


def test_alias_collision_is_rejected(tmp_path: Path) -> None:
    definitions = load_aliases()
    definitions["receipt"]["cash_amount"]["aliases"].append("total_price")
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps(definitions), encoding="utf-8")
    with pytest.raises(ContractError, match="collision"):
        load_aliases(path)


def test_nested_repeated_object_group_and_positive_only_cord_scoring() -> None:
    fields = project_fields(_spec())
    assert {(field["name"], field["shape"], field["group"]) for field in fields} == {
        ("total_price", "scalar", None),
        ("item_name", "linked", "Receipt.items"),
        ("item_price", "linked", "Receipt.items"),
    }
    gold = [{"field_id": "total_amount", "type": "string"},
            {"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_price", "type": "array[object]"}]
    definitions = load_aliases()["receipt"]
    exact = score_schema(_spec(), gold, family="receipt", definitions=definitions, allow_aliases=False)
    alias = score_schema(_spec(), gold, family="receipt", definitions=definitions, allow_aliases=True)
    assert exact["matched"] == 2
    assert alias["matched"] == 3
    assert alias["linked_pair_hits"] == alias["linked_pair_total"] == 1
    assert "reference_ontology_false_positives" not in alias
    summarized = summarize_scores([{"arm": "per_document", "match_mode": "predeclared_alias", **alias}])[0]
    assert summarized["recall"] == 1.0 and summarized["precision"] is None and summarized["f1"] is None


def test_two_different_repeated_groups_do_not_link_rows() -> None:
    gold = [{"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_price", "type": "array[object]"}]
    score = score_schema(_spec(separate_groups=True), gold, family="receipt",
                         definitions=load_aliases()["receipt"], allow_aliases=True)
    assert score["matched"] == 2
    assert score["shape_hits"] == 2
    assert score["linked_pair_hits"] == 0


def test_vrdu_reference_ontology_precision_and_type_checks() -> None:
    spec = {"root": "Form", "models": [{"name": "Form", "fields": [
        {"name": "registration_number", "type": "str"},
        {"name": "date_filed", "type": "date"},
        {"name": "extra_unjudged", "type": "str"},
    ]}]}
    gold = [{"field_id": "registration_num", "type": "string"},
            {"field_id": "file_date", "type": "string"}]
    score = score_schema(spec, gold, family="registration-form",
                         definitions=load_aliases()["registration-form"], allow_aliases=True)
    assert score["matched"] == 2
    assert score["reference_ontology_false_positives"] == 1
    assert score["type_raw_string_hits"] == 1
    assert score["semantic_type_hits"] == 2
    summary = summarize_scores([{"arm": "family_template", "match_mode": "predeclared_alias", **score}])[0]
    assert summary["precision"] == pytest.approx(2 / 3)
    assert summary["recall"] == 1.0
    assert summary["f1"] == pytest.approx(0.8)


def test_loopback_is_required_and_http_calls_are_bounded(tmp_path: Path) -> None:
    for url in ("https://127.0.0.1:1/v1/chat/completions", "http://example.com:1/v1/chat/completions",
                "http://127.0.0.1:1/other", "http://127.0.0.1:1/v1/chat/completions?x=1"):
        with pytest.raises(ContractError):
            _loopback_base(url)
    callback = BoundedLocalCalls("http://127.0.0.1:18081/v1/chat/completions", tmp_path)
    callback.calls = MAX_CALLS
    with pytest.raises(ContractError, match="cap"):
        callback(prompt={"system": "s", "user": "u"}, schema_json="{}", context="probe")
    assert not (tmp_path / "calls.jsonl").exists()
