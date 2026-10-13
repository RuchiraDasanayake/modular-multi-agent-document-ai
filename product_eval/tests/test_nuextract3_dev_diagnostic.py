from __future__ import annotations

import pytest

from product_eval import nuextract3_dev_diagnostic as diagnostic
from product_eval.contracts import ContractError
from product_eval.graph_schema_diagnostic import project_fields
from product_eval.nuextract3_dev_diagnostic import (
    reference_template,
    score_values,
    template_to_graph_spec,
)


def test_template_projection_preserves_repeated_object_linkage() -> None:
    spec = template_to_graph_spec({
        "file_date": "date-time",
        "addresses": ["verbatim-string"],
        "items": [{"item_name": "verbatim-string", "item_price": "number"}],
    })
    fields = {field["name"]: field for field in project_fields(spec)}
    assert fields["file_date"]["shape"] == "scalar"
    assert fields["addresses"]["shape"] == "scalar_list"
    assert fields["item_name"]["shape"] == "linked"
    assert fields["item_name"]["group"] == fields["item_price"]["group"]


def test_deeply_nested_template_uses_unique_model_names() -> None:
    spec = template_to_graph_spec({"parties": [{"person": {"name": "verbatim-string"}}],
                                   "summary": {"text": "verbatim-string"}})
    assert len({model["name"] for model in spec["models"]}) == len(spec["models"])
    fields = {field["name"]: field for field in project_fields(spec)}
    assert fields["name"]["shape"] == "linked"
    assert fields["text"]["shape"] == "scalar"


def test_reference_template_uses_names_and_shapes_only() -> None:
    schema = [{"field_id": "total_amount", "type": "string"},
              {"field_id": "item_name", "type": "array[object]"},
              {"field_id": "item_price", "type": "array[object]"}]
    assert reference_template(schema) == {
        "total_amount": "verbatim-string",
        "line_items": [{"item_name": "verbatim-string", "item_price": "verbatim-string"}],
    }


def test_value_score_counts_exact_scalars_and_order_independent_rows() -> None:
    gold = {
        "gold_schema": [{"field_id": "total_amount", "type": "string"},
                        {"field_id": "item_name", "type": "array[object]"},
                        {"field_id": "item_price", "type": "array[object]"}],
        "gold_values": [{"field_id": "total_amount", "value": "9.00"},
                        {"field_id": "item_name", "value": [{"row": 0, "value": "Tea"},
                                                             {"row": 1, "value": "Cake"}]},
                        {"field_id": "item_price", "value": [{"row": 0, "value": "4.00"},
                                                              {"row": 1, "value": "5.00"}]}],
        "pages": [{"page": 1, "text": "Tea 4.00 Cake 5.00 Total 9.00"}],
    }
    reply = {"total_amount": "9.00", "line_items": [
        {"item_name": "Cake", "item_price": "5.00"},
        {"item_name": "Tea", "item_price": "4.00"},
    ]}
    result = score_values(reply, gold)
    assert result["exact_scalar_positive"] == 1
    assert result["ordinal_exact_linked_cells"] == 0
    assert result["order_independent_raw_complete_rows"] == 2
    assert result["machine_auto_accepted_values"] == 0


def test_missing_reply_keeps_all_positive_denominators() -> None:
    gold = {"gold_schema": [{"field_id": "a", "type": "string"},
                             {"field_id": "b", "type": "array[object]"}],
            "gold_values": [{"field_id": "a", "value": "present"},
                            {"field_id": "b", "value": [{"row": 0, "value": "cell"}]}],
            "pages": [{"page": 1, "text": "present cell"}]}
    result = score_values(None, gold)
    assert result["gold_scalar_positive"] == 1
    assert result.get("exact_scalar_positive", 0) == 0
    assert result["gold_linked_cells"] == 1
    assert result["ordinal_exact_linked_cells"] == 0


def test_template_preflight_rejects_ignored_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostic, "_apply_template", lambda base, kwargs: "same prompt")
    with pytest.raises(ContractError, match="ignored"):
        diagnostic._verify_template_modes("http://127.0.0.1:18127")


def test_template_preflight_requires_both_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    def format_prompt(base: str, kwargs: dict[str, object]) -> str:
        if "template" in kwargs:
            return str(kwargs["template"])
        return "schema mode" if kwargs.get("mode") == "template-generation" else "baseline"

    monkeypatch.setattr(diagnostic, "_apply_template", format_prompt)
    result = diagnostic._verify_template_modes("http://127.0.0.1:18127")
    assert len(set(result.values())) == 3
