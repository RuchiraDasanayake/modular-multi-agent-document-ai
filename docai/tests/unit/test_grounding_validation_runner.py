from __future__ import annotations

from docai_core.contracts.domain import (
    ExtractedOutput,
    FieldOutput,
    OCROutput,
    ValidationReport,
)
from docai_core.validation.grounding_validation_runner import GroundingValidationRunner


def _ocr(text: str) -> OCROutput:
    return OCROutput(document_id="doc-1", engine_id="test", text=text)


def _extracted(fields: list[tuple[str, str]]) -> ExtractedOutput:
    return ExtractedOutput(
        document_id="doc-1",
        schema_id="schema-1",
        policy_id="policy-1",
        fields=[
            FieldOutput(field_name=name, value=value, validation_status="needs_review")
            for name, value in fields
        ],
    )


def test_all_grounded_fields_produce_pass_status() -> None:
    source = "Invoice Number: INV-001\nTotal Amount: $100.00\nStatus: Paid"
    extracted = _extracted([
        ("invoice_number", "INV-001"),
        ("total_amount", "100.00"),
        ("status", "Paid"),
    ])

    report = GroundingValidationRunner().build_validation_report(extracted, _ocr(source))

    assert report.pass_status is True
    assert report.field_issues == []
    assert report.document_id == "doc-1"


def test_ungrounded_field_produces_fail_status() -> None:
    source = "Invoice Number: INV-001"
    extracted = _extracted([
        ("invoice_number", "INV-001"),
        ("total_amount", "INV-999"),
    ])

    report = GroundingValidationRunner().build_validation_report(extracted, _ocr(source))

    assert report.pass_status is False
    assert any("total_amount" in issue and "not_found_in_source" in issue
               for issue in report.field_issues)


def test_missing_fields_do_not_fail_pass_status() -> None:
    source = "Invoice Number: INV-001"
    extracted = _extracted([
        ("invoice_number", "INV-001"),
        ("total_amount", "N/A"),
    ])

    report = GroundingValidationRunner().build_validation_report(extracted, _ocr(source))

    assert report.pass_status is True
    assert any("total_amount" in issue and "missing_value" in issue
               for issue in report.field_issues)


def test_summary_contains_counts() -> None:
    source = "Invoice Number: INV-001\nStatus: Paid"
    extracted = _extracted([
        ("invoice_number", "INV-001"),
        ("status", "Paid"),
        ("total_amount", "N/A"),
        ("date", "GHOST-VALUE"),
    ])

    report = GroundingValidationRunner().build_validation_report(extracted, _ocr(source))

    assert "2 grounded" in report.summary
    assert "1 ungrounded" in report.summary
    assert "1 missing" in report.summary


def test_field_issues_contain_field_name_and_reason() -> None:
    source = "Status: Paid"
    extracted = _extracted([
        ("status", "Paid"),
        ("invoice_number", "MISSING-VALUE"),
        ("total_amount", "N/A"),
    ])

    report = GroundingValidationRunner().build_validation_report(extracted, _ocr(source))

    ungrounded_issues = [i for i in report.field_issues if "not_found_in_source" in i]
    missing_issues = [i for i in report.field_issues if "missing_value" in i]

    assert len(ungrounded_issues) == 1
    assert "invoice_number: not_found_in_source" in ungrounded_issues[0]
    assert len(missing_issues) == 1
    assert "total_amount: missing_value" in missing_issues[0]


def test_grounding_validation_runner_satisfies_protocol() -> None:
    runner = GroundingValidationRunner()
    assert callable(getattr(runner, "build_validation_report", None))

    report = runner.build_validation_report(
        _extracted([("f", "val")]),
        _ocr("val"),
    )
    assert isinstance(report, ValidationReport)
    assert report.document_id == "doc-1"


def test_grounding_validation_runner_empty_fields() -> None:
    extracted = _extracted([])
    report = GroundingValidationRunner().build_validation_report(
        extracted, _ocr("some text")
    )
    assert report.pass_status is True
    assert report.field_issues == []
    assert "0 grounded" in report.summary
