from __future__ import annotations

from docai_core.contracts.domain import ExtractedOutput, FieldOutput
from docai_core.validation import GroundedFieldResult, GroundingResult, GroundingValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extracted(fields: list[tuple[str, str]]) -> ExtractedOutput:
    """Build a minimal ExtractedOutput from (field_name, value) pairs."""
    return ExtractedOutput(
        document_id="doc-1",
        schema_id="schema-1",
        policy_id="policy-1",
        fields=[
            FieldOutput(
                field_name=name,
                value=value,
                validation_status="needs_review",
            )
            for name, value in fields
        ],
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_grounding_validator_exact_match() -> None:
    source = "Invoice Number: INV-001\nTotal Amount: $100.00"
    extracted = _extracted([("invoice_number", "INV-001")])

    result = GroundingValidator().validate(extracted, source)

    assert result.grounded_count == 1
    field = result.fields[0]
    assert field.is_grounded is True
    assert field.field_name == "invoice_number"
    assert field.match_text is not None
    assert "INV-001" in field.match_text


def test_grounding_validator_case_insensitive_match() -> None:
    source = "Status: Paid"
    extracted = _extracted([("status", "paid")])

    result = GroundingValidator(case_sensitive=False).validate(extracted, source)

    assert result.grounded_count == 1
    assert result.fields[0].is_grounded is True


def test_grounding_validator_case_sensitive_no_match() -> None:
    source = "Status: Paid"
    extracted = _extracted([("status", "paid")])

    result = GroundingValidator(case_sensitive=True).validate(extracted, source)

    assert result.ungrounded_count == 1
    assert result.fields[0].is_grounded is False


def test_grounding_validator_whitespace_normalized_match() -> None:
    source = "Company: Acme    Corporation"
    extracted = _extracted([("company", "Acme Corporation")])

    result = GroundingValidator(normalize_whitespace=True).validate(extracted, source)

    assert result.grounded_count == 1
    assert result.fields[0].is_grounded is True


def test_grounding_validator_missing_value_counts_as_missing() -> None:
    source = "Invoice Number: INV-001"
    extracted = _extracted([("total_amount", "N/A")])

    result = GroundingValidator().validate(extracted, source)

    assert result.missing_count == 1
    assert result.grounded_count == 0
    assert result.ungrounded_count == 0
    assert result.fields[0].reason == "missing_value"
    assert result.fields[0].is_grounded is False


def test_grounding_validator_empty_string_counts_as_missing() -> None:
    source = "Invoice Number: INV-001"
    extracted = _extracted([("status", "")])

    result = GroundingValidator().validate(extracted, source)

    assert result.missing_count == 1
    assert result.fields[0].reason == "missing_value"


def test_grounding_validator_ungrounded_value() -> None:
    source = "Invoice Number: INV-001\nStatus: Paid"
    extracted = _extracted([("invoice_number", "INV-999")])

    result = GroundingValidator().validate(extracted, source)

    assert result.ungrounded_count == 1
    assert result.grounded_count == 0
    field = result.fields[0]
    assert field.is_grounded is False
    assert field.reason == "not_found_in_source"


def test_grounding_validator_currency_loose_match() -> None:
    source = "Total Amount: $100.00"
    extracted = _extracted([("total_amount", "100.00")])

    result = GroundingValidator().validate(extracted, source)

    assert result.grounded_count == 1
    assert result.fields[0].is_grounded is True


def test_grounding_validator_currency_symbol_stripped_match() -> None:
    source = "Total Amount: 100.00"
    extracted = _extracted([("total_amount", "$100.00")])

    result = GroundingValidator(allow_numeric_loose_match=True).validate(extracted, source)

    assert result.grounded_count == 1
    assert result.fields[0].is_grounded is True
    assert result.fields[0].reason == "numeric_loose_match"


def test_grounding_validator_does_not_overmatch_invoice_id_as_numeric() -> None:
    source = "Reference: 001 items"
    extracted = _extracted([("invoice_number", "INV-001")])

    result = GroundingValidator().validate(extracted, source)

    assert result.ungrounded_count == 1
    assert result.fields[0].is_grounded is False


def test_grounding_result_counts() -> None:
    source = "Invoice Number: INV-001\nTotal Amount: $100.00\nStatus: Paid"
    extracted = _extracted([
        ("invoice_number", "INV-001"),
        ("total_amount", "100.00"),
        ("status", "Paid"),
        ("missing_field", "N/A"),
        ("hallucinated_field", "GHOST-VALUE"),
    ])

    result = GroundingValidator().validate(extracted, source)

    assert result.grounded_count == 3
    assert result.missing_count == 1
    assert result.ungrounded_count == 1
    assert len(result.fields) == 5


def test_grounding_result_span_populated_on_match() -> None:
    source = "Invoice Number: INV-001"
    extracted = _extracted([("invoice_number", "INV-001")])

    result = GroundingValidator().validate(extracted, source)

    field = result.fields[0]
    assert field.start_index is not None
    assert field.end_index is not None
    assert field.end_index > field.start_index


def test_public_exports_available() -> None:
    from docai_core.validation import GroundedFieldResult, GroundingResult, GroundingValidator

    assert GroundingValidator is not None
    assert GroundingResult is not None
    assert GroundedFieldResult is not None
