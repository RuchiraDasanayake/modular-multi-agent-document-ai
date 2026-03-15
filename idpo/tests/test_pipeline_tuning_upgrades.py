from __future__ import annotations

from pathlib import Path

from idpo.agents.base import AgentContext
from idpo.agents.preprocess import OcrAgent
from idpo.agents.recovery import RecoveryAgent
from idpo.agents.validation import ValidationAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig, ValidationRule
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import DAEOutput, Document, Entity, Page, ValidationIssue
from idpo.pipeline.inbox import process_inbox
from idpo.pipeline.planning import _default_operator_specs


def _ctx(tmp_path: Path, config: PipelineConfig | None = None) -> AgentContext:
    cfg = config or PipelineConfig()
    artifacts = ArtifactStore(str(tmp_path / "artifacts"))
    provenance = ProvenanceRecorder(str(tmp_path / "provenance.jsonl"))
    return AgentContext(config=cfg, artifact_store=artifacts, provenance=provenance, run_id="test-run")


def test_scanned_pipeline_orders_image_cleanup_before_ocr() -> None:
    dae = DAEOutput(
        doc_id="doc-1",
        doc_type="scanned_document",
        vendor_cluster="unknown",
        quality_bin="C",
        complexity_bin="2",
        content_profile="image-heavy",
        quality_score=0.45,
        complexity_score=0.5,
        signals={"skew_angle": 5.0},
    )
    actions = {"preprocess": {"ocr": {"enabled": True}, "deskew": {"enabled": True}, "denoise": {"enabled": True}}}

    specs = _default_operator_specs(dae, actions)
    operators = [item["operator"] for item in specs]

    assert operators[:3] == ["preprocess.deskew", "preprocess.denoise", "preprocess.ocr"]


def test_ocr_retry_settings_raise_dpi_and_add_alt_psm(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.preprocessing.ocr_retry_dpi = 500
    cfg.preprocessing.ocr_retry_alt_psm = [3, 4, 11]
    agent = OcrAgent()
    ctx = _ctx(tmp_path, cfg)

    retry = agent._build_retry_settings(  # noqa: SLF001
        {"psm": 6, "dpi": 300, "alt_psm": [4, 11]},
        ctx,
    )

    assert retry["dpi"] == 500
    assert 6 in retry["alt_psm"]
    assert 3 in retry["alt_psm"]


def test_validation_adds_semantic_date_issue(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.validation.rules = []
    agent = ValidationAgent()
    ctx = _ctx(tmp_path, cfg)
    doc = Document(doc_id="doc-1", source="digital", path="doc.txt", pages=[Page(number=1, text="x")])

    result = agent.run(
        {
            "document": doc,
            "entities": [Entity(key="document_date", value="bad-date-text", confidence=0.85)],
            "stage": "initial",
        },
        ctx,
    )

    issues = result.artifacts["validation_issues"]
    assert any(issue.issue == "semantic_date_mismatch" for issue in issues)


def test_extraction_only_route_skips_summary_and_chunking() -> None:
    dae = DAEOutput(
        doc_id="doc-1",
        doc_type="text_document",
        vendor_cluster="unknown",
        quality_bin="A",
        complexity_bin="1",
        content_profile="text-heavy",
        quality_score=0.9,
        complexity_score=0.2,
        signals={},
    )
    actions = {"execution_mode": "extraction_only", "preprocess": {"ocr": {"enabled": True}}}
    specs = _default_operator_specs(dae, actions)
    operators = [item["operator"] for item in specs]
    assert "structuring.extract" in operators
    assert "validation" in operators
    assert "chunking" not in operators
    assert "structuring.summary" not in operators


def test_recovery_rejects_invalid_amount_candidate(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.validation.rules = [
        ValidationRule(field_pattern=".*_amount$", value_pattern=r"^\d+(\.\d{2})?$", normalize="numeric")
    ]
    ctx = _ctx(tmp_path, cfg)
    agent = RecoveryAgent()
    doc = Document(doc_id="doc-1", source="digital", path="doc.txt", pages=[Page(number=1, text="Total Amount: ABC")])
    issues = [ValidationIssue(field="total_amount", issue="pattern_mismatch", severity="medium")]
    result = agent.run({"document": doc, "entities": [], "issues": issues, "strategy": "regex"}, ctx)
    assert result.artifacts["recovered_fields"] == {}


def test_inbox_batch_run_processes_multiple_docs_in_one_run(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    doc1 = root / "one.txt"
    doc2 = root / "two.txt"
    doc1.write_text("Invoice Number: INV-1\nTotal Amount: 10.00\n", encoding="utf-8")
    doc2.write_text("Invoice Number: INV-2\nTotal Amount: 20.00\n", encoding="utf-8")
    result = process_inbox(root=root, file_paths=[str(doc1), str(doc2)])
    metrics = result["metrics"]
    assert int(metrics["doc_count"]) == 2
    assert int(metrics["processed_doc_count"]) == 2
