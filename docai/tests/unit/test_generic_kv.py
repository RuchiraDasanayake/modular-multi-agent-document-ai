from __future__ import annotations

import pytest

from docai_core.extraction import (
    KeyValueCandidate,
    extract_key_values,
    parse_amount_line,
    parse_kv_line,
    parse_multi_kv_line,
)


def test_parse_kv_line_colon_delimiter() -> None:
    result = parse_kv_line("Invoice Number: INV-001")
    assert result is not None
    key, value = result
    assert key == "invoice_number"
    assert value == "INV-001"


def test_parse_kv_line_equals_delimiter() -> None:
    result = parse_kv_line("Invoice Number = INV-001")
    assert result is not None
    key, value = result
    assert key == "invoice_number"
    assert value == "INV-001"


def test_parse_kv_line_space_delimiter() -> None:
    result = parse_kv_line("Vendor Name    Acme Corp")
    assert result is not None
    key, value = result
    assert key == "vendor_name"
    assert value == "Acme Corp"


def test_parse_multi_kv_line_multiple_pairs() -> None:
    pairs = parse_multi_kv_line("Invoice No: INV-001 Date: 2026-03-15 PO: PO-9922")
    keys = {k for k, _ in pairs}
    assert len(pairs) >= 2
    assert "invoice_no" in keys
    assert "date" in keys


def test_parse_amount_line_extracts_total() -> None:
    result = parse_amount_line("Total Due: $1,234.00")
    assert result is not None
    key, value = result
    assert key == "total_due"
    assert value == "$1,234.00"


def test_extract_key_values_from_text_returns_candidates() -> None:
    text = (
        "Invoice Number: INV-001\n"
        "Vendor Name: Acme Corp\n"
        "Total Due: $500.00\n"
    )
    results = extract_key_values(text)
    assert len(results) >= 3
    assert all(isinstance(c, KeyValueCandidate) for c in results)
    keys = {c.key for c in results}
    assert "invoice_number" in keys
    assert "vendor_name" in keys


def test_noise_filter_rejects_sentence_like_line() -> None:
    results = extract_key_values("This invoice was issued for services rendered.")
    assert results == []


def test_invoice_relevant_single_word_keys_are_preserved() -> None:
    text = "Date: 2026-03-15\nStatus: Paid\nType: Invoice\n"
    results = extract_key_values(text)
    keys = {c.key for c in results}
    assert "date" in keys
    assert "status" in keys
    assert "type" in keys


def test_quoted_short_value_not_suppressed() -> None:
    results = extract_key_values('Invoice Number: "INV-001"')
    assert len(results) >= 1
    assert results[0].key == "invoice_number"


def test_missing_values_are_ignored() -> None:
    results = extract_key_values("Total Amount: N/A")
    assert results == []


def test_confidence_scoring_for_date() -> None:
    results = extract_key_values("Invoice Date: 2026-03-15")
    assert len(results) == 1
    assert results[0].confidence == 0.75


def test_confidence_scoring_for_amount() -> None:
    results = extract_key_values("Total Amount: $100.00")
    assert len(results) == 1
    assert results[0].confidence == 0.72


def test_confidence_scoring_for_id_like_value() -> None:
    results = extract_key_values("Invoice Number: INV-001")
    assert len(results) == 1
    assert results[0].confidence == 0.70


def test_public_exports_available() -> None:
    from docai_core.extraction import (
        KeyValueCandidate,
        extract_key_values,
        parse_amount_line,
        parse_kv_line,
        parse_multi_kv_line,
    )

    assert callable(extract_key_values)
    assert callable(parse_kv_line)
    assert callable(parse_multi_kv_line)
    assert callable(parse_amount_line)
    assert KeyValueCandidate is not None

    # Smoke round-trip
    results = extract_key_values("Invoice Number: INV-999\nTotal: $250.00\n")
    assert len(results) >= 1
    assert all(isinstance(c, KeyValueCandidate) for c in results)
