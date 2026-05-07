from __future__ import annotations

from docai_core.extraction import (
    MISSING_VALUE_MARKERS,
    TOKEN_EQUIVALENTS,
    clean_candidate_value,
    normalize_key,
)


def test_normalize_key_lowercases_and_strips() -> None:
    assert normalize_key(" Invoice Number ") == "invoice_number"


def test_normalize_key_collapses_punctuation_and_spaces() -> None:
    result = normalize_key("Total Amount ($)")
    # Parentheses and $ are non-alphanumeric → collapsed to underscore, then stripped
    assert result == "total_amount"
    assert "__" not in result
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_normalize_key_applies_token_equivalents_if_legacy_does() -> None:
    # Legacy normalize_key does NOT apply TOKEN_EQUIVALENTS — that belongs in
    # canonicalization. The constant is exported for use by callers.
    # Verify: normalize_key("no") stays "no", not "number".
    assert normalize_key("no") == "no"
    # Verify TOKEN_EQUIVALENTS contains the known legacy mapping.
    assert TOKEN_EQUIVALENTS["no"] == ("number",)
    assert TOKEN_EQUIVALENTS["inv"] == ("invoice",)


def test_normalize_key_truncates_long_keys_if_legacy_does() -> None:
    # Legacy truncates at 40 chars, preferring the last underscore > pos 20.
    long_input = "Purchase Order Invoice Number Total Amount Field"
    result = normalize_key(long_input)
    assert len(result) <= 40
    # Legacy finds last underscore in first 40 chars (pos 35 > 20), cuts there.
    assert result == "purchase_order_invoice_number_total"
    assert not result.endswith("_")


def test_clean_candidate_value_strips_whitespace_and_collapses_spaces() -> None:
    assert clean_candidate_value("  ABC    123  ") == "ABC 123"


def test_clean_candidate_value_removes_bullet_prefix_if_legacy_does() -> None:
    # Leading hyphen is in the bullet prefix set — stripped.
    assert clean_candidate_value("- Total Amount") == "Total Amount"
    # Unicode bullet (U+2022) also in the bullet prefix set.
    assert clean_candidate_value("• Total Amount") == "Total Amount"


def test_clean_candidate_value_strips_trailing_punctuation_if_legacy_does() -> None:
    # Legacy strips("|;,. ") — colon is NOT in that set, so trailing ":" is kept.
    assert clean_candidate_value("INV-001:") == "INV-001:"
    # Trailing comma IS in the strip set — stripped.
    assert clean_candidate_value("Acme Corp,") == "Acme Corp"
    # Trailing period IS in the strip set — stripped.
    assert clean_candidate_value("100.00.") == "100.00"


def test_missing_value_markers_contains_common_absent_values() -> None:
    assert "n/a" in MISSING_VALUE_MARKERS
    assert "na" in MISSING_VALUE_MARKERS
    assert "none" in MISSING_VALUE_MARKERS
    assert "null" in MISSING_VALUE_MARKERS
    assert "" in MISSING_VALUE_MARKERS
    assert "-" in MISSING_VALUE_MARKERS
    assert "not found" in MISSING_VALUE_MARKERS
    assert "unknown" in MISSING_VALUE_MARKERS


def test_public_exports_available() -> None:
    assert callable(normalize_key)
    assert callable(clean_candidate_value)
    assert isinstance(MISSING_VALUE_MARKERS, frozenset)
    assert isinstance(TOKEN_EQUIVALENTS, dict)
    # Spot-check one round-trip to confirm imports are live
    assert normalize_key("Vendor Name") == "vendor_name"
    assert clean_candidate_value("  hello  ") == "hello"
