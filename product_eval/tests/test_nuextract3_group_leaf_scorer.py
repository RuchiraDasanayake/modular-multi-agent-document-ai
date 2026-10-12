from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_eval.contracts import ContractError
from product_eval.nuextract3_dev_diagnostic import template_to_graph_spec
from product_eval.nuextract3_group_leaf_scorer import (
    canonical_sha256,
    load_rule,
    normalize_name,
    score_grouped_leaf,
    score_self_template_values,
)

RULE_PATH = Path(__file__).resolve().parents[2] / "docs/evaluations/nuextract3_group_leaf_alias_v1.json"
RULE_SHA256 = "343e6c2403d97c27d4cdf4207e005eb6d800397ff19d426474d6970d3b51d95b"


@pytest.fixture
def rule() -> dict:
    return load_rule(RULE_PATH, RULE_SHA256)


def test_rule_hash_and_name_normalization(rule: dict) -> None:
    assert canonical_sha256(rule) == RULE_SHA256
    assert normalize_name("UnitPrice") == "unit_price"
    assert normalize_name("Ｉｔｅｍ  Quantity") == "item_quantity"


def test_rule_rejects_changed_or_duplicate_json(tmp_path: Path) -> None:
    changed = tmp_path / "changed.json"
    changed.write_text(RULE_PATH.read_text(encoding="utf-8").replace("unit_price", "per_price", 1), encoding="utf-8")
    with pytest.raises(ContractError, match="SHA256"):
        load_rule(changed, RULE_SHA256)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"version":1,"version":1}', encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate JSON key"):
        load_rule(duplicate, RULE_SHA256)


def test_grouped_aliases_recover_quantity_and_description_pair(rule: dict) -> None:
    spec = template_to_graph_spec({"receipt": {"line_items": [{
        "item_name": "verbatim-string", "quantity": "integer", "unit_price": "currency",
    }]}})
    gold = [{"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_quantity", "type": "array[object]"},
            {"field_id": "unit_price", "type": "array[object]"}]
    score = score_grouped_leaf(spec, gold, rule)
    assert score["matched"] == 3
    assert score["linked_pair_hits"] == score["linked_pair_total"] == 3
    assert score["shape_hits"] == 3
    assert {m["predicted_group"] for m in score["matches"]} == {"Document.receipt.line_items"}


def test_unit_price_does_not_match_unspecified_item_price(rule: dict) -> None:
    spec = template_to_graph_spec({"items": [{"item_name": "verbatim-string", "unit_price": "currency"}]})
    gold = [{"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_price", "type": "array[object]"}]
    score = score_grouped_leaf(spec, gold, rule)
    assert score["matched_linked_fields"] == 1
    assert score["linked_pair_hits"] == 0
    assert score["linked_pair_total"] == 1
    assert score["unmatched_reference_ids"] == ["item_price"]


def test_scalar_alias_is_ineligible_for_linked_field(rule: dict) -> None:
    spec = template_to_graph_spec({"quantity": "integer"})
    gold = [{"field_id": "item_quantity", "type": "array[object]"}]
    assert score_grouped_leaf(spec, gold, rule)["matched"] == 0


def test_pair_cannot_cross_predicted_groups(rule: dict) -> None:
    spec = template_to_graph_spec({"items": [{"item_name": "verbatim-string"}],
                                   "other_items": [{"quantity": "integer"}]})
    gold = [{"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_quantity", "type": "array[object]"}]
    score = score_grouped_leaf(spec, gold, rule)
    assert score["matched"] == 2
    assert score["linked_pair_hits"] == 0
    assert score["linked_pair_total"] == 1


def test_nested_repeated_groups_use_nearest_parent(rule: dict) -> None:
    spec = template_to_graph_spec({"orders": [{"quantity": "integer",
                                               "items": [{"item_name": "verbatim-string"}]}]})
    gold = [{"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_quantity", "type": "array[object]"}]
    score = score_grouped_leaf(spec, gold, rule)
    assert score["matched_linked_fields"] == 2
    assert score["linked_pair_hits"] == 0
    assert {m["predicted_group"] for m in score["matches"]} == {"Document.orders", "Document.orders.items"}


def test_nested_repeated_value_rows_flatten_in_document_order(rule: dict) -> None:
    gold = {"gold_schema": [{"field_id": "item_name", "type": "array[object]"},
                            {"field_id": "item_quantity", "type": "array[object]"}],
            "gold_values": [{"field_id": "item_name", "value": [{"row": 0, "value": "Tea"},
                                                                  {"row": 1, "value": "Cake"}]},
                            {"field_id": "item_quantity", "value": [{"row": 0, "value": "2"},
                                                                      {"row": 1, "value": "1"}]}],
            "pages": [{"page": 1, "text": "Tea 2 Cake 1"}]}
    spec = template_to_graph_spec({"orders": [{"items": [{"item_name": "verbatim-string",
                                                        "quantity": "integer"}]}]})
    score = score_grouped_leaf(spec, gold["gold_schema"], rule)
    reply = {"orders": [{"items": [{"item_name": "Tea", "quantity": "2"}]},
                        {"items": [{"item_name": "Cake", "quantity": "1"}]}]}
    values = score_self_template_values(reply, gold, score)
    assert values["ordinal_exact_linked_cells"] == 4
    assert values["order_independent_raw_complete_rows"] == 2


def test_colliding_aliases_are_unmatched(rule: dict) -> None:
    spec = template_to_graph_spec({"items": [{"quantity": "integer", "item_quantity": "integer"}]})
    gold = [{"field_id": "item_quantity", "type": "array[object]"}]
    score = score_grouped_leaf(spec, gold, rule)
    assert score["matched"] == 0
    assert len(score["collisions"]) == 1
    assert score["collisions"][0]["slot"] == "quantity"


def test_no_repeated_object_returns_zero_pairs_without_failure(rule: dict) -> None:
    gold = [{"field_id": "item_name", "type": "array[object]"},
            {"field_id": "item_quantity", "type": "array[object]"}]
    score = score_grouped_leaf(None, gold, rule)
    assert score["matched"] == 0
    assert score["linked_pair_hits"] == 0
    assert score["linked_pair_total"] == 1


def _gold() -> dict:
    return {"gold_schema": [{"field_id": "total_amount", "type": "string"},
                            {"field_id": "item_name", "type": "array[object]"},
                            {"field_id": "item_quantity", "type": "array[object]"}],
            "gold_values": [{"field_id": "total_amount", "value": "9.00"},
                            {"field_id": "item_name", "value": [{"row": 0, "value": "Tea"}]},
                            {"field_id": "item_quantity", "value": [{"row": 0, "value": "2"}]}],
            "pages": [{"page": 1, "text": "Tea 2 9.00"}]}


def test_self_template_value_scoring_uses_nested_paths(rule: dict) -> None:
    template = {"total_amount": "currency", "receipt": {"line_items": [{
        "item_name": "verbatim-string", "quantity": "integer",
    }]}}
    score = score_grouped_leaf(template_to_graph_spec(template), _gold()["gold_schema"], rule)
    reply = {"total_amount": "9.00", "receipt": {"line_items": [{"item_name": "Tea", "quantity": "2"}]}}
    values = score_self_template_values(reply, _gold(), score)
    assert values["exact_scalar_positive"] == 1
    assert values["ordinal_exact_linked_cells"] == 2
    assert values["order_independent_raw_complete_rows"] == 1
    assert values["row_group_complete"] is True
    assert values["machine_auto_accepted_values"] == 0


def test_self_template_missing_field_fails_full_row(rule: dict) -> None:
    template = {"items": [{"item_name": "verbatim-string"}]}
    score = score_grouped_leaf(template_to_graph_spec(template), _gold()["gold_schema"], rule)
    values = score_self_template_values({"items": [{"item_name": "Tea"}]}, _gold(), score)
    assert values["gold_complete_rows"] == 1
    assert values["ordinal_exact_linked_cells"] == 1
    assert values["order_independent_raw_complete_rows"] == 0
    assert values["row_group_complete"] is False


def test_sparse_rows_do_not_receive_complete_row_credit(rule: dict) -> None:
    gold = _gold()
    gold["gold_values"][2]["value"] = []
    spec = template_to_graph_spec({"items": [{"item_name": "verbatim-string", "quantity": "integer"}]})
    score = score_grouped_leaf(spec, gold["gold_schema"], rule)
    values = score_self_template_values({"items": [{"item_name": "Tea"}]}, gold, score)
    assert values["gold_linked_rows"] == 1
    assert values["gold_sparse_rows"] == 1
    assert values["gold_complete_rows"] == 0
    assert values["order_independent_raw_complete_rows"] == 0


def test_mixed_explicit_and_implicit_reference_groups_are_unscored(rule: dict) -> None:
    spec = template_to_graph_spec({"items": [{"item_name": "verbatim-string", "quantity": "integer"}]})
    gold = [{"field_id": "item_name", "type": "array[object]", "row_group": "items"},
            {"field_id": "item_quantity", "type": "array[object]"}]
    score = score_grouped_leaf(spec, gold, rule)
    assert score["linked_pair_unavailable"] is True
    assert score["linked_pair_total"] is None
    assert score["linked_pair_opportunities"] == 1
