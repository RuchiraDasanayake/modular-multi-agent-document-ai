from docai_core.contracts.domain import ExtractedOutput, OCROutput
from docai_core.validation.stub_validation_runner import StubValidationRunner


def _extracted(doc_id: str = "doc-1") -> ExtractedOutput:
    return ExtractedOutput(
        document_id=doc_id,
        schema_id="schema-1",
        policy_id="policy-1",
    )


def _ocr(doc_id: str = "doc-1") -> OCROutput:
    return OCROutput(document_id=doc_id, engine_id="test", text="some text")


def test_stub_validation_runner_builds_expected_report() -> None:
    report = StubValidationRunner().build_validation_report(_extracted(), _ocr())

    assert report.document_id == "doc-1"
    assert report.field_issues == []
    assert report.table_issues == []
    assert report.document_issues == []
    assert report.pass_status is True
    assert report.summary is not None
    assert "stub" in report.summary


def test_stub_validation_runner_uses_extracted_output_document_id() -> None:
    report = StubValidationRunner().build_validation_report(
        _extracted("doc-xyz"), _ocr("doc-xyz")
    )
    assert report.document_id == "doc-xyz"


def test_stub_validation_runner_ignores_ocr_content() -> None:
    report = StubValidationRunner().build_validation_report(
        _extracted(), OCROutput(document_id="doc-1", engine_id="test", text="")
    )
    assert report.pass_status is True
    assert report.summary == "stub validation passed"
