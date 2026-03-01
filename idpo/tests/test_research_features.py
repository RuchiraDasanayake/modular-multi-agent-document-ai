from __future__ import annotations

import json
from pathlib import Path

from idpo.agents.base import AgentContext
from idpo.agents.doc_analysis import DocumentAnalysisAgent
from idpo.agents.recovery import RecoveryAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.budget import BudgetManager
from idpo.core.calibration import ConfidenceCalibrator, load_calibration_samples
from idpo.core.config import BudgetConfig, PipelineConfig, RollbackConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import DAEOutput, Document, Entity, Page, SystemConstraints, ValidationIssue
from idpo.pipeline.orchestrator import Pipeline
from idpo.pipeline.policy_advisor import PolicyAdvisor
from idpo.pipeline.policy_safety import PolicySafetyMonitor


def _ctx(tmp_path: Path, config: PipelineConfig | None = None) -> AgentContext:
    cfg = config or PipelineConfig()
    store = ArtifactStore(str(tmp_path / "artifacts"))
    provenance = ProvenanceRecorder(str(tmp_path / "prov.jsonl"))
    return AgentContext(
        config=cfg,
        artifact_store=store,
        provenance=provenance,
        run_id="test-run",
        budget_manager=BudgetManager(cfg.budget),
        calibrator=None,
    )


def test_dae_feature_extraction_is_deterministic(tmp_path: Path) -> None:
    agent = DocumentAnalysisAgent()
    ctx = _ctx(tmp_path)
    doc = Document(
        doc_id="doc-1",
        source="scanned",
        path="doc-1.txt",
        metadata={"vendor": "acme", "skew_angle": 6.0},
        pages=[
            Page(
                number=1,
                text="Invoice ID: INV-123\nTotal Amount: 100.00\nItem | Qty | Price\nA | 1 | 100.00\n",
                raw_text="Invoice ID: INV-123\nTotal Amount: 100.00\nItem | Qty | Price\nA | 1 | 100.00\n",
                image_path="scan.png",
            )
        ],
    )
    first = agent.run({"document": doc}, ctx).artifacts["dae_output"]
    second = agent.run({"document": doc}, ctx).artifacts["dae_output"]
    assert first.route_bin == second.route_bin
    assert first.layout_cluster_id == second.layout_cluster_id
    assert first.quality_features == second.quality_features
    assert first.structural_features == second.structural_features


def test_policy_advisor_ranked_fallback(tmp_path: Path) -> None:
    policy_path = tmp_path / "policies.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {
                        "policy_id": "table_policy",
                        "name": "Table",
                        "conditions": {"content_profile": ["table-heavy"]},
                        "actions": {},
                    },
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    config = PipelineConfig()
    config.ahmn.enabled = False
    advisor = PolicyAdvisor(config)
    store = PolicyStore(str(policy_path), default_policy_id="default")
    dae = DAEOutput(
        doc_id="d1",
        doc_type="table_document",
        vendor_cluster="acme",
        quality_bin="B",
        complexity_bin="2",
        content_profile="table-heavy",
        quality_score=0.6,
        complexity_score=0.7,
    )
    advice = advisor.advise(dae, SystemConstraints(max_cost_units=5, max_latency_ms=2000), store, {})
    assert advice.recommendations
    assert advice.recommendations[0].policy_id == "table_policy"
    assert advice.fallback_used is True


def test_budget_manager_blocks_escalation_when_budget_exceeded() -> None:
    budget = BudgetConfig(max_cost_per_doc=1.0, max_cost_per_minute=1.0)
    manager = BudgetManager(budget)
    manager.start_document("d1")
    manager.spend("d1", 1.0)
    decision = manager.allow_escalation("d1", estimated_cost=0.2)
    assert decision.allowed is False
    assert decision.reason == "max_cost_per_doc"


def test_calibration_fit_and_eval_from_fixture(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "calibration_samples.jsonl"
    samples = load_calibration_samples(str(fixture))
    calibrator = ConfidenceCalibrator(method="platt")
    calibrator.fit(samples)
    report = calibrator.evaluate(samples, bins=5)
    assert report["count"] == len(samples)
    assert "ece" in report
    assert report["reliability_curve"]


def test_recovery_retries_only_failing_fields(tmp_path: Path) -> None:
    config = PipelineConfig()
    ctx = _ctx(tmp_path, config=config)
    agent = RecoveryAgent()
    doc = Document(
        doc_id="doc-recover",
        source="digital",
        path="doc.txt",
        pages=[
            Page(
                number=1,
                text="invoice id: INV-1\ntotal amount: 100.00\n",
                raw_text="invoice id: INV-1\ntotal amount: 100.00\n",
            )
        ],
    )
    entities = [
        Entity(key="invoice_id", value="INV-1", confidence=0.55),
        Entity(key="total_amount", value="100.00", confidence=0.45),
    ]
    issues = [ValidationIssue(field="total_amount", issue="low_confidence", severity="medium")]
    result = agent.run(
        {
            "document": doc,
            "entities": entities,
            "issues": issues,
            "failing_fields": ["total_amount"],
            "strategy": "regex",
            "max_retries": 2,
        },
        ctx,
    )
    recovered = result.artifacts["recovered_fields"]
    assert list(recovered.keys()) == ["total_amount"]
    updated = {entity.key: entity.value for entity in result.artifacts["entities"]}
    assert updated["invoice_id"] == "INV-1"


def test_shadow_mode_does_not_change_canonical_output(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy_store.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                    {
                        "policy_id": "shadow_alt",
                        "name": "ShadowAlt",
                        "conditions": {"route_bin": ["heavy"]},
                        "actions": {"preprocess": {"denoise": {"enabled": True}}},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    config = PipelineConfig()
    config.shadow.enabled = True
    config.shadow.sample_rate = 1.0
    config.shadow.candidate_policy_ids = ["shadow_alt"]
    config.queue.enabled = False
    config.knowledge.policy_store_path = str(policy_path)

    pipeline = Pipeline(config=config, run_dir=str(tmp_path / "run"))
    doc = Document(
        doc_id="shadow-doc",
        source="digital",
        path="shadow.txt",
        metadata={"vendor": "acme"},
        pages=[Page(number=1, text="Record ID: A-1\nDate: 01/01/2026\n", raw_text="Record ID: A-1\nDate: 01/01/2026\n")],
    )
    result = pipeline.process_documents([doc])[0]
    assert result.policy_id == "default"
    comparison_path = pipeline.run_dir / "metrics" / config.shadow.comparison_file
    assert comparison_path.exists()
    comparisons = json.loads(comparison_path.read_text(encoding="utf-8"))
    assert comparisons


def test_rollback_triggers_when_metrics_regress(tmp_path: Path) -> None:
    config = RollbackConfig(
        enabled=True,
        window_size=6,
        latency_p95_ms=400.0,
        validation_failure_rate=0.5,
        quality_drop_threshold=0.05,
        max_latency_regression_pct=0.1,
        min_validation_pass_delta=0.05,
    )
    monitor = PolicySafetyMonitor(tmp_path, config, baseline_policy_id="default")
    for _ in range(6):
        monitor.update("default", {"latency_ms": 100.0, "validation_failure": 0.0, "quality_proxy": 0.9})
    last = None
    for _ in range(6):
        last = monitor.update("candidate", {"latency_ms": 600.0, "validation_failure": 0.6, "quality_proxy": 0.4})
    assert last is not None
    assert last.triggered is True
    assert monitor.is_blocked("candidate") is True


def test_provenance_contains_required_event_types(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy_store.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                    {
                        "policy_id": "shadow_alt",
                        "name": "ShadowAlt",
                        "conditions": {"route_bin": ["heavy"]},
                        "actions": {"recovery": {"strategy": "alternate_rules"}},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    config = PipelineConfig()
    config.shadow.enabled = True
    config.shadow.sample_rate = 1.0
    config.shadow.candidate_policy_ids = ["shadow_alt"]
    config.queue.enabled = False
    config.validation.min_confidence = 0.95
    config.plan.max_total_budget_units = 20.0
    config.budget.max_cost_per_doc = 20.0
    config.escalation.flagship_model = "flagship-sim"
    config.knowledge.policy_store_path = str(policy_path)
    pipeline = Pipeline(config=config, run_dir=str(tmp_path / "run"))
    doc = Document(
        doc_id="prov-doc",
        source="scanned",
        path="prov.txt",
        metadata={"vendor": "acme", "guardrail_flags": ["approval_code"]},
        pages=[
            Page(
                number=1,
                text="Invoice ID: INV-9\nTotal Amount: 99.00\n",
                raw_text="Invoice ID: INV-9\nTotal Amount: 99.00\n",
                image_path="x.png",
            )
        ],
    )
    pipeline.process_documents([doc])
    events_path = pipeline.run_dir / "provenance" / "events.jsonl"
    events = [
        json.loads(line)["event_type"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    required = {
        "DAEOutput",
        "PolicyAdvice",
        "RouteSelection",
        "ValidationResult",
        "RecoveryAction",
        "EscalationAction",
        "ShadowComparison",
    }
    assert required.issubset(set(events))


def test_partition_scheduler_fairness(tmp_path: Path) -> None:
    pipeline = Pipeline(config=PipelineConfig(), run_dir=str(tmp_path / "run"))
    dae = DAEOutput(
        doc_id="x",
        doc_type="text_document",
        vendor_cluster="a",
        quality_bin="A",
        complexity_bin="1",
        content_profile="text-heavy",
        quality_score=0.9,
        complexity_score=0.2,
    )
    hot = [(Document(doc_id=f"hot-{idx}", source="digital", path=f"h{idx}", pages=[Page(number=1, text="x")]), dae, None) for idx in range(5)]
    cold = [(Document(doc_id="cold-1", source="digital", path="c1", pages=[Page(number=1, text="y")]), dae, None)]
    schedule = pipeline._fair_partition_schedule({"hot": hot, "cold": cold})
    ordered_partitions = [item[0] for item in schedule]
    assert ordered_partitions[0] == "cold" or ordered_partitions[1] == "cold"
    assert ordered_partitions.index("cold") < len(ordered_partitions) - 1
