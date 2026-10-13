"""Source-free response validation for candidate-bound schema naming."""

from __future__ import annotations

import json

import pytest

from product_eval.s1_schema_reply import (
    CandidateRef,
    SchemaReplyError,
    parse_reply,
    response_schema,
)

CATALOG = (
    CandidateRef("column_123", "column", ("header_1", "cell_1", "cell_2"), "table_1"),
    CandidateRef("scalar_456", "scalar", ("label_1", "value_1")),
)


def _reply(fields):
    return json.dumps({"schema_version": 1, "fields": fields})


def test_only_enumerated_candidates_can_be_named_and_all_remain_review_only():
    fields = parse_reply(_reply([
        {"candidate_id": "scalar_456", "field_id": "total_amount",
         "type": "decimal", "decision": "propose"},
        {"candidate_id": "column_123", "field_id": "item_name",
         "type": "array[object]", "decision": "propose"},
    ]), CATALOG)
    assert [field["field_id"] for field in fields] == ["total_amount", "item_name"]
    assert fields[1]["group"] == "table_1"
    assert fields[1]["source_node_ids"] == ["header_1", "cell_1", "cell_2"]
    assert all(field["status"] == "needs_review" for field in fields)


def test_explicit_abstention_covers_a_candidate_without_inventing_a_field():
    fields = parse_reply(_reply([
        {"candidate_id": "column_123", "field_id": None,
         "type": None, "decision": "abstain"},
        {"candidate_id": "scalar_456", "field_id": "total_amount",
         "type": "decimal", "decision": "propose"},
    ]), CATALOG)
    assert len(fields) == 1 and fields[0]["field_id"] == "total_amount"


@pytest.mark.parametrize("fields,reason", [
    ([{"candidate_id": "unknown_999", "field_id": "total_amount",
       "type": "decimal", "decision": "propose"},
      {"candidate_id": "scalar_456", "field_id": None,
       "type": None, "decision": "abstain"}], "unknown_or_duplicate_candidate"),
    ([{"candidate_id": "column_123", "field_id": "item_name",
       "type": "string", "decision": "propose"},
      {"candidate_id": "scalar_456", "field_id": None,
       "type": None, "decision": "abstain"}], "field_type_mismatch"),
    ([{"candidate_id": "column_123", "field_id": "item_name",
       "type": ["array[object]"], "decision": "propose"},
      {"candidate_id": "scalar_456", "field_id": None,
       "type": None, "decision": "abstain"}], "field_type_mismatch"),
    ([{"candidate_id": "column_123", "field_id": "item_name",
       "type": "array[object]", "decision": "propose", "value": "fabricated"},
      {"candidate_id": "scalar_456", "field_id": None,
       "type": None, "decision": "abstain"}], "invalid_field_shape"),
    ([{"candidate_id": "column_123", "field_id": "item_name",
       "type": "array[object]", "decision": "propose"},
      {"candidate_id": "scalar_456", "field_id": "item_name",
       "type": "string", "decision": "propose"}], "invalid_or_duplicate_field_id"),
])
def test_invalid_fields_fail_the_whole_reply(fields, reason):
    with pytest.raises(SchemaReplyError, match=reason):
        parse_reply(_reply(fields), CATALOG)


def test_duplicate_keys_and_missing_candidate_fail_closed():
    with pytest.raises(SchemaReplyError, match="invalid_json"):
        parse_reply('{"schema_version":1,"schema_version":1,"fields":[]}', CATALOG)
    with pytest.raises(SchemaReplyError, match="candidate_coverage_mismatch"):
        parse_reply(_reply([]), CATALOG)


def test_response_schema_enumerates_only_source_candidates():
    schema = response_schema(CATALOG)
    items = schema["properties"]["fields"]["items"]
    assert items["properties"]["candidate_id"]["enum"] == ["column_123", "scalar_456"]
    assert items["additionalProperties"] is False


def test_candidate_kind_cannot_claim_invented_source_group():
    with pytest.raises(SchemaReplyError, match="column_requires_source_group"):
        CandidateRef("column_123", "column", ("header_1",))
    with pytest.raises(SchemaReplyError, match="scalar_cannot_claim_source_row_group"):
        CandidateRef("scalar_456", "scalar", ("value_1",), "table_1")
