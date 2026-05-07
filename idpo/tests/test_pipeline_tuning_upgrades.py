from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from idpo.agents.base import AgentContext
from idpo.agents.preprocess import OcrAgent
from idpo.agents.recovery import RecoveryAgent
from idpo.agents.validation import ValidationAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig, ValidationRule
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import DAEOutput, Document, Entity, Page, ValidationIssue
from idpo.pipeline.executor import ExecutionState, PlanExecutor
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


def test_validation_marks_text_grounded_entities(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.validation.rules = []
    agent = ValidationAgent()
    ctx = _ctx(tmp_path, cfg)
    entity = Entity(key="total_amount", value="1234.50", confidence=0.9)
    doc = Document(
        doc_id="doc-1",
        source="scanned",
        path="receipt.txt",
        pages=[Page(number=1, text="SUBTOTAL 1200.00\nTAX 34.50\nTOTAL 1234.50\n")],
    )

    result = agent.run({"document": doc, "entities": [entity], "stage": "initial"}, ctx)

    assert result.artifacts["validation_issues"] == []
    assert entity.metadata["text_grounded"] is True
    assert "ungrounded" not in entity.metadata


def test_validation_normalizes_natural_language_dates_before_pattern_check(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.validation.rules = [
        ValidationRule(
            field_pattern=".*_date$",
            value_pattern=r"^\d{4}-\d{2}-\d{2}$",
            severity="medium",
            normalize="date",
        )
    ]
    agent = ValidationAgent()
    ctx = _ctx(tmp_path, cfg)
    doc = Document(
        doc_id="doc-1",
        source="digital",
        path="memo.txt",
        pages=[Page(number=1, text="Date: March 27, 1984")],
    )

    result = agent.run(
        {
            "document": doc,
            "entities": [Entity(key="document_date", value="March 27, 1984", confidence=0.95)],
            "stage": "initial",
        },
        ctx,
    )

    issues = result.artifacts["validation_issues"]
    assert not any(issue.issue == "pattern_mismatch" for issue in issues)
    assert not any(issue.issue == "semantic_date_mismatch" for issue in issues)
    assert result.artifacts["normalized_entities"]["document_date"] == "1984-03-27"


def test_validation_allows_document_type_supported_by_analysis_metadata(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.validation.rules = []
    agent = ValidationAgent()
    ctx = _ctx(tmp_path, cfg)
    doc = Document(
        doc_id="doc-1",
        source="scanned",
        path="receipt.txt",
        pages=[Page(number=1, text="TOTAL 1234.50\nCASH 1500.00\nCHANGE 265.50")],
        metadata={"semantic_doc_type": "receipt"},
        doc_type="scanned_document",
    )

    result = agent.run(
        {
            "document": doc,
            "entities": [Entity(key="document_type", value="receipt", confidence=0.95)],
            "stage": "initial",
        },
        ctx,
    )

    issues = result.artifacts["validation_issues"]
    assert not any(issue.issue == "ungrounded_value" for issue in issues)


def test_validation_allows_document_type_supported_by_routing_family_alias(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    cfg.validation.rules = []
    agent = ValidationAgent()
    ctx = _ctx(tmp_path, cfg)
    doc = Document(
        doc_id="doc-1",
        source="scanned",
        path="memo.txt",
        pages=[Page(number=1, text="FAX TRANSMISSION\nTO Jane Smith\nFROM John Doe\nDATE January 11 1999")],
        metadata={"routing_family": "correspondence", "route_specialization": "form"},
        doc_type="form_document",
    )

    result = agent.run(
        {
            "document": doc,
            "entities": [Entity(key="document_type", value="form", confidence=0.95)],
            "stage": "initial",
        },
        ctx,
    )

    issues = result.artifacts["validation_issues"]
    assert not any(issue.issue == "ungrounded_value" for issue in issues)


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


def test_default_pipeline_omits_recovery_step() -> None:
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
    specs = _default_operator_specs(dae, {})
    operators = [item["operator"] for item in specs]

    assert "validation" in operators
    assert "recovery" not in operators
    assert "escalation" in operators


def test_recovery_step_requires_explicit_enablement() -> None:
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
    config = PipelineConfig()
    config.recovery.enabled = True

    specs = _default_operator_specs(dae, {}, config)
    operators = [item["operator"] for item in specs]

    assert operators[operators.index("validation") + 1] == "recovery"
    assert operators[operators.index("recovery") + 1] == "escalation"


def test_recovery_attempts_llm_and_degrades_gracefully_on_failure(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    ctx = _ctx(tmp_path, cfg)
    agent = RecoveryAgent()
    doc = Document(doc_id="doc-1", source="digital", path="doc.txt", pages=[Page(number=1, text="Total Amount: ABC")])
    issues = [ValidationIssue(field="total_amount", issue="pattern_mismatch", severity="medium")]
    result = agent.run({"document": doc, "entities": [], "issues": issues}, ctx)
    # LLM unavailable in unit tests → recovered_fields empty, but no exception raised.
    assert isinstance(result.artifacts["recovered_fields"], dict)
    trace = result.artifacts["recovery_trace"]
    assert trace  # at least one trace entry (llm attempt + error)
    assert trace[0]["strategy"] == "llm_reextraction"


def test_recovery_preserves_existing_entities_when_llm_fails(tmp_path: Path) -> None:
    cfg = PipelineConfig()
    ctx = _ctx(tmp_path, cfg)
    agent = RecoveryAgent()
    doc = Document(doc_id="doc-1", source="scanned", path="doc.txt", pages=[Page(number=1, text="CASH 7000")])
    entities = [Entity(key="cash_amount", value="7000", confidence=0.9)]
    issues = [ValidationIssue(field="total_amount", issue="missing_field", severity="medium")]
    result = agent.run({"document": doc, "entities": entities, "issues": issues}, ctx)
    # cash_amount not in failing fields → should be preserved unchanged
    updated = {e.key: e.value for e in result.artifacts["entities"]}
    assert updated.get("cash_amount") == "7000"


def test_executor_passes_extraction_context_to_extractor(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, PipelineConfig())
    executor = PlanExecutor()
    state = ExecutionState(
        document=Document(doc_id="doc-1", source="digital", path="doc.txt", pages=[Page(number=1, text="Total Amount: 10.00")])
    )
    captured: dict[str, object] = {}

    def fake_run(payload, _ctx):  # noqa: ANN001
        captured.update(payload)
        return SimpleNamespace(
            artifacts={
                "entities": [],
                "explicit_entities": [],
                "default_entities": [],
                "explicit_source": "config",
                "requested_field_status": {},
                "llm_diagnostics": {},
                "signal": None,
            }
        )

    executor.extractor.run = fake_run  # type: ignore[method-assign]
    step = SimpleNamespace(
        params={
            "model_tier": "local",
            "explicit_entities": ["total_amount"],
            "field_descriptions": {"total_amount": "Total amount"},
            "per_field_extraction": True,
            "use_thinking": False,
            "extraction_context": "JOB CONTEXT: total_amount is often ambiguous.",
        }
    )

    executor._run_extraction(step, state, ctx)  # noqa: SLF001

    assert captured["extraction_context"] == "JOB CONTEXT: total_amount is often ambiguous."


def test_inbox_batch_run_processes_multiple_docs_in_one_run(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("IDPO_DATA_DIR", str(tmp_path / "idpo-data"))
    doc1 = root / "one.txt"
    doc2 = root / "two.txt"
    doc1.write_text("Invoice Number: INV-1\nTotal Amount: 10.00\n", encoding="utf-8")
    doc2.write_text("Invoice Number: INV-2\nTotal Amount: 20.00\n", encoding="utf-8")
    result = process_inbox(root=root, file_paths=[str(doc1), str(doc2)])
    metrics = result["metrics"]
    assert int(metrics["doc_count"]) == 2
    assert int(metrics["processed_doc_count"]) == 2
