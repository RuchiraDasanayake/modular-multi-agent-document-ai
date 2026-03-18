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
from idpo.pipeline.inbox import process_inbox
import idpo.pipeline.inbox as inbox_module
from idpo.pipeline.policy_safety import PolicySafetyMonitor
from idpo.pipeline.planning import PlanRouter
from scripts.run_idpo_benchmark import run_benchmark
from idpo.core.storage import repo_root


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
    assert first.route_bin in {"light", "standard", "heavy"}
    assert first.layout_cluster_id != "unknown"
    assert first.analysis_confidence > 0.0
    assert first.confidence_type == "heuristic"


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


def test_plan_router_uses_adaptive_fallback_and_static_mode(tmp_path: Path) -> None:
    policy_path = tmp_path / "policies.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                    {
                        "policy_id": "table_policy",
                        "name": "Table",
                        "conditions": {"route_bin": ["heavy"]},
                        "actions": {"preprocess": {"table_extract": {"enabled": True}}},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    dae = DAEOutput(
        doc_id="d1",
        doc_type="table_document",
        vendor_cluster="acme",
        quality_bin="B",
        complexity_bin="2",
        content_profile="table-heavy",
        quality_score=0.7,
        complexity_score=0.8,
        layout_cluster_id="table_dense",
        route_bin="heavy",
        structural_features={"table_ratio": 0.4, "form_ratio": 0.0, "page_count": 1.0, "avg_line_length": 20.0, "heading_density": 0.0},
        quality_features={"blur_score": 0.2, "skew_angle": 0.0, "text_density": 0.8, "image_ratio": 0.1, "dpi_est": 300.0},
    )
    constraints = SystemConstraints(max_cost_units=5, max_latency_ms=2000)

    adaptive_config = PipelineConfig()
    adaptive_config.ahmn.policy_mode = "adaptive"
    adaptive_store = PolicyStore(str(policy_path), default_policy_id="default")
    adaptive_router = PlanRouter(adaptive_config, adaptive_store)
    adaptive = adaptive_router.route(dae, constraints, blocked_policy_ids=set())
    assert adaptive.policy.policy_id == "table_policy"
    assert adaptive.advice_source == "fallback"
    assert adaptive.ranked_policies
    assert adaptive.route_specialization == "table"

    static_config = PipelineConfig()
    static_config.ahmn.policy_mode = "static"
    static_store = PolicyStore(str(policy_path), default_policy_id="default")
    static_router = PlanRouter(static_config, static_store)
    static = static_router.route(dae, constraints, blocked_policy_ids={"table_policy"})
    assert static.policy.policy_id == "default"
    assert static.advice_source == "static"
    assert static.fallback_reason == "baseline_blocked"


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
    trace = result.artifacts["recovery_trace"]
    assert trace
    assert trace[0]["field"] == "total_amount"
    assert trace[0]["success"] is True
    updated = {entity.key: entity.value for entity in result.artifacts["entities"]}
    assert updated["invoice_id"] == "INV-1"


def test_pipeline_emits_reward_and_trace_fields(tmp_path: Path) -> None:
    config = PipelineConfig()
    config.validation.min_confidence = 0.95
    pipeline = Pipeline(config=config, run_dir=str(tmp_path / "run"))
    doc = Document(
        doc_id="reward-doc",
        source="digital",
        path="reward.txt",
        pages=[Page(number=1, text="Invoice Number: INV-55\nTotal Amount: 10.00\nDate: 01/01/2026\n")],
    )
    result = pipeline.process_documents([doc])[0]
    assert result.reward_type == "proxy"
    assert isinstance(result.reward_details, dict)
    assert result.recovery_log is not None
    assert result.escalation_status in {"not_needed", "attempted", "budget_blocked", "quota_blocked", "model_unavailable"}


def test_process_inbox_writes_decision_chain_and_reward_artifacts(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))
    doc_path = workspace / "invoice.txt"
    doc_path.write_text("Invoice Number: INV-1\nTotal Amount: 10.00\nDue Date: 2026-03-25\n", encoding="utf-8")

    result = process_inbox(
        root=workspace,
        file_paths=[str(doc_path)],
        extraction_fields=[
            {"name": "invoice_number", "description": "Invoice identifier"},
            {"name": "total_amount", "description": "Total due amount"},
        ],
    )
    doc = result["doc_records"][0]
    assert doc["reward_type"] == "direct_set_based"
    assert Path(doc["decision_chain_path"]).exists()
    assert Path(doc["reward_path"]).exists()
    assert Path(doc["recovery_trace_path"]).exists()
    decision_chain = json.loads(Path(doc["decision_chain_path"]).read_text(encoding="utf-8"))
    assert "policy" in decision_chain
    assert "reward" in decision_chain
    metrics = result["metrics"]
    assert "avg_reward" in metrics


def test_process_inbox_preserves_shadow_and_queue_config(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))

    policy_path = tmp_path / "policy_store.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                    {"policy_id": "shadow_alt", "name": "ShadowAlt", "conditions": {}, "actions": {}},
                ],
            }
        ),
        encoding="utf-8",
    )

    config_payload = json.loads((repo_root() / "configs" / "config.json").read_text(encoding="utf-8"))
    config_payload.setdefault("shadow", {})
    config_payload["shadow"]["enabled"] = True
    config_payload["shadow"]["sample_rate"] = 1.0
    config_payload["shadow"]["candidate_policy_ids"] = ["shadow_alt"]
    config_payload.setdefault("queue", {})
    config_payload["queue"]["enabled"] = False
    config_payload.setdefault("knowledge", {})
    config_payload["knowledge"]["policy_store_path"] = str(policy_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_payload, indent=2), encoding="utf-8")

    doc_a = workspace / "invoice_a.txt"
    doc_b = workspace / "invoice_b.txt"
    doc_a.write_text("Invoice Number: INV-11\nTotal Amount: 10.00\n", encoding="utf-8")
    doc_b.write_text("Invoice Number: INV-12\nTotal Amount: 15.00\n", encoding="utf-8")

    captured: dict[str, object] = {}

    class DummyPipeline:
        def __init__(self, config, run_dir: str) -> None:
            captured["shadow_enabled"] = config.shadow.enabled
            captured["queue_enabled"] = config.queue.enabled
            self.run_dir = Path(run_dir)

        def process_documents(self, docs):  # noqa: ANN001
            return []

        def build_index(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return None

    monkeypatch.setattr(inbox_module, "Pipeline", DummyPipeline)

    result = process_inbox(root=workspace, config_path=str(config_path), file_paths=[str(doc_a), str(doc_b)])

    assert captured["shadow_enabled"] is True
    assert captured["queue_enabled"] is False
    assert not any("Queue mode auto-enabled" in warning for warning in result["preflight_warnings"])


def test_benchmark_generates_paper_evidence(tmp_path: Path, monkeypatch) -> None:
    runtime_root = tmp_path / "idpo-data"
    monkeypatch.setenv("IDPO_DATA_DIR", str(runtime_root))
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "name": "tiny_pack",
                "cases": [
                    {
                        "case_id": "invoice_basic",
                        "path": "idpo/benchmark/data/invoice_basic.txt",
                        "fields": {
                            "invoice_number": "Invoice identifier",
                            "total_amount": "Total due amount",
                        },
                        "expected": {
                            "invoice_number": "INV-2026-1001",
                            "total_amount": "1388.80",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence = run_benchmark(config_path="configs/config.json", pack_path=str(pack_path))
    report_path = runtime_root / "runs" / "benchmarks" / evidence["experiment"]["benchmark_run_id"] / "paper_evidence.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"experiment", "conditions", "comparison", "documents"}
    assert "static" in payload["conditions"]
    assert "adaptive" in payload["conditions"]
    assert "table" in payload["comparison"]
    assert payload["experiment"]["condition_configs"]["adaptive"]["ahmn_enabled"] is True
    assert payload["experiment"]["condition_configs"]["adaptive"]["ahmn_mode"] != "mock"
    assert "exact_f1" in payload["comparison"]["table"]
    assert "advice_source_counts" in payload["comparison"]["table"]


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
