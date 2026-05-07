from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Column,
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    OCROutput,
    OCRPage,
    SelectedPolicy,
    Table,
)
from docai_core.extraction.stub_extraction_runner import StubExtractionRunner


def _build_schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Invoice extraction schema",
        version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", description="Invoice number", type="string"),
            Field(field_id="f2", name="total_amount", description="Total amount", type="string"),
        ],
        tables=[
            Table(
                table_id="t1",
                name="line_items",
                description="Invoice rows",
                columns=[
                    Column(column_id="c1", name="description", description="Item description", type="string"),
                    Column(column_id="c2", name="line_total", description="Line total", type="string"),
                ],
            )
        ],
    )


def _build_policy() -> SelectedPolicy:
    return SelectedPolicy(
        policy_id="invoice_table_heavy_local_v1",
        policy_family="invoice_extraction",
        policy_version="v1",
        selected_by="deterministic_strategy_assigner",
    )


def test_stub_extraction_runner_builds_expected_ocr_output() -> None:
    now = datetime.now(timezone.utc)
    runner = StubExtractionRunner()
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice_001.pdf",
        file_path="invoice_001.pdf",
        status="uploaded",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-1"),
    )

    ocr_output = runner.build_ocr_output(document)

    assert ocr_output.text == "Fake OCR output for invoice_001.pdf"
    assert ocr_output.engine_id == "fake_ocr_v1"
    assert len(ocr_output.pages) == 1
    assert ocr_output.pages[0].page_number == 1


def test_stub_extraction_runner_builds_expected_extracted_output() -> None:
    now = datetime.now(timezone.utc)
    runner = StubExtractionRunner()
    schema = _build_schema()
    policy = _build_policy()
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice_001.pdf",
        file_path="invoice_001.pdf",
        status="uploaded",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-1"),
    )
    ocr_text = "Fake OCR output for invoice_001.pdf"
    ocr_output = OCROutput(
        document_id="doc-1",
        engine_id="fake_ocr_v1",
        text=ocr_text,
        pages=[OCRPage(page_number=1, text=ocr_text)],
        blocks=[],
        tables_detected=[],
        confidence=0.9,
    )

    extracted = runner.build_extracted_output(schema, document, policy, ocr_output)

    assert extracted.policy_id == "invoice_table_heavy_local_v1"
    assert [item.field_name for item in extracted.fields] == ["invoice_number", "total_amount"]
    assert all(item.evidence_text == ocr_text for item in extracted.fields)
    assert len(extracted.tables) == 1
    assert len(extracted.tables[0].rows) == 1
    assert set(extracted.tables[0].rows[0].columns.keys()) == {"description", "line_total"}
    assert extracted.tables[0].rows[0].evidence_text == ocr_text
