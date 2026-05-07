from datetime import datetime, timezone

from docai_core.contracts.domain import Document, DocumentProfile, RunPlan
from docai_core.plugins.ocr.base import OCRPluginConfig
from docai_core.plugins.ocr.stub_ocr_plugin import StubOCRPlugin


def test_ocr_plugin_config_can_be_created() -> None:
    config = OCRPluginConfig(
        plugin_id="stub_ocr_plugin",
        engine_name="Stub OCR",
        enabled=True,
        settings={"mode": "stub"},
    )

    assert config.plugin_id == "stub_ocr_plugin"
    assert config.engine_name == "Stub OCR"
    assert config.enabled is True
    assert config.settings["mode"] == "stub"


def test_stub_ocr_plugin_returns_expected_output() -> None:
    now = datetime.now(timezone.utc)
    plugin = StubOCRPlugin()
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice_001.pdf",
        file_path="invoice_001.pdf",
        status="uploaded",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-1"),
    )
    run_plan = RunPlan(
        plan_id="plan-1",
        document_id="doc-1",
        schema_id="schema-1",
        policy_id="policy-1",
    )

    output = plugin.run_ocr(document, run_plan)

    assert plugin.plugin_id == "stub_ocr_plugin"
    assert plugin.engine_name == "Stub OCR"
    assert output.document_id == "doc-1"
    assert output.text == "Fake OCR output for invoice_001.pdf"
    assert len(output.pages) == 1
    assert output.pages[0].page_number == 1
    assert output.confidence == 0.9
