from __future__ import annotations

from docai_core.extraction import canonicalize_entities, merge_by_key


def _ent(
    key: str,
    value: str = "V",
    confidence: float = 0.8,
    metadata: dict | None = None,
) -> dict:
    return {"key": key, "value": value, "confidence": confidence, "metadata": metadata or {}}


def test_canonicalize_exact_key_match() -> None:
    result = canonicalize_entities([_ent("invoice_number")], schema_fields=["invoice_number"])
    assert len(result) == 1
    assert result[0]["key"] == "invoice_number"
    # Exact match: key did not change, so no raw_key injected into metadata.
    assert "raw_key" not in result[0]["metadata"]


def test_canonicalize_human_label_to_schema_key() -> None:
    # "Invoice Number" normalizes to "invoice_number" → exact match against schema field.
    result = canonicalize_entities([_ent("Invoice Number")], schema_fields=["invoice_number"])
    assert result[0]["key"] == "invoice_number"


def test_canonicalize_uses_description_tokens_if_legacy_does() -> None:
    # "amount_payable" + description "amount payable" for schema field "total_amount":
    # description expands target tokens to include "payable", giving containment 2/3 ≈ 0.67
    # plus high-value "amount" bonus → score 0.75 ≥ 0.62 threshold → maps to "total_amount".
    result = canonicalize_entities(
        [_ent("amount_payable")],
        schema_fields=["total_amount"],
        field_descriptions={"total_amount": "amount payable"},
    )
    assert result[0]["key"] == "total_amount"


def test_canonicalize_preserves_raw_key_in_metadata() -> None:
    # "invoice_num" substring-matches "invoice_number" (score 0.7 ≥ 0.62).
    # Because the key changes, the pre-canonical normalized key is stored as raw_key.
    result = canonicalize_entities([_ent("invoice_num")], schema_fields=["invoice_number"])
    assert result[0]["key"] == "invoice_number"
    assert result[0]["metadata"]["raw_key"] == "invoice_num"


def test_canonicalize_preserves_value_and_confidence() -> None:
    result = canonicalize_entities(
        [_ent("invoice_number", value="INV-999", confidence=0.95)],
        schema_fields=["invoice_number"],
    )
    assert result[0]["value"] == "INV-999"
    assert result[0]["confidence"] == 0.95


def test_canonicalize_handles_unmatched_entity_by_legacy_behavior() -> None:
    # Legacy does NOT drop unmatched entities. Score for "customer_ref" vs
    # "invoice_number" is 0.0 (no token overlap). Entity is returned unchanged.
    result = canonicalize_entities([_ent("customer_ref")], schema_fields=["invoice_number"])
    assert len(result) == 1
    assert result[0]["key"] == "customer_ref"
    assert "raw_key" not in result[0]["metadata"]


def test_merge_by_key_keeps_best_candidate_if_legacy_supports_it() -> None:
    # After canonicalization both entities map to "invoice_number".
    # merge_by_key must keep the one with higher confidence (0.9 over 0.6).
    e1 = _ent("invoice_number", value="INV-001", confidence=0.6)
    e2 = _ent("invoice_num", value="INV-002", confidence=0.9)
    canonical = canonicalize_entities([e1, e2], schema_fields=["invoice_number"])
    assert all(e["key"] == "invoice_number" for e in canonical)
    merged = merge_by_key(canonical)
    assert len(merged) == 1
    assert merged[0]["value"] == "INV-002"
    assert merged[0]["confidence"] == 0.9


def test_public_exports_available() -> None:
    assert callable(canonicalize_entities)
    assert callable(merge_by_key)
    # Smoke-test round-trip
    entities = [_ent("invoice_number", "INV-001", 0.9)]
    result = canonicalize_entities(entities, schema_fields=["invoice_number"])
    assert result[0]["key"] == "invoice_number"
