from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

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
import scripts.run_idpo_benchmark as benchmark_module
from idpo.pipeline.policy_safety import PolicySafetyMonitor
from idpo.pipeline.planning import PlanRouter
from idpo.pipeline.reward import _has_field_value
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
    assert "ocr_noise_ratio" in first.quality_features
    assert "kv_density" in first.structural_features
    assert "numeric_density" in first.structural_features
    assert "line_length_cv" in first.structural_features


def test_dae_emits_mixed_profile_when_form_and_table_signals_coexist(tmp_path: Path) -> None:
    agent = DocumentAnalysisAgent()
    ctx = _ctx(tmp_path)
    doc = Document(
        doc_id="doc-mixed",
        source="digital",
        path="doc-mixed.txt",
        pages=[
            Page(
                number=1,
                text=(
                    "Agreement ID: AGR-2048\n"
                    "Effective Date: 2026-02-15\n"
                    "Party A: Northwind Systems\n"
                    "Party B: Blue River Logistics\n"
                    "Milestone | Due Date | Amount\n"
                    "Design | 2026-03-01 | 25000.00\n"
                ),
            )
        ],
    )
    output = agent.run({"document": doc}, ctx).artifacts["dae_output"]
    assert output.content_profile == "mixed"
    assert output.doc_type == "mixed_document"
    assert output.layout_cluster_id == "mixed_dense"


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


def test_policy_advisor_uses_ahmn_contract_and_preserves_adaptive_metadata(tmp_path: Path, monkeypatch) -> None:
    policy_path = tmp_path / "policies.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "table_policy", "name": "Table", "conditions": {"content_profile": ["table-heavy"]}, "actions": {}},
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    config = PipelineConfig()
    config.ahmn.enabled = True
    config.ahmn.mode = "http"
    config.ahmn.endpoint = "http://ahmn"
    config.ahmn.advice_endpoint = "/advice"
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
        layout_cluster_id="table_dense",
        route_bin="heavy",
        quality_features={"ocr_noise_ratio": 0.1},
        structural_features={"table_ratio": 0.4},
        signals={"table_likelihood": 1.0},
    )
    captured: dict[str, object] = {}

    class DummyResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            {
                "advice_id": str(uuid4()),
                "policy_id": "table_policy",
                "policy_data": {"action": "table_extraction"},
                "retrieval_source": "LTM",
                "confidence": 0.83,
                "rabi_used": True,
                "n_neighbors": 4,
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    advice = advisor.advise(dae, SystemConstraints(max_cost_units=5, max_latency_ms=2000), store, {"source": "test"})

    payload = captured["payload"]
    assert captured["url"] == "http://ahmn/advice"
    assert payload["doc_type"] == "table_document"
    assert payload["vendor"] == "acme"
    assert payload["content_profile"] == "table-heavy"
    assert payload["extra_context"]["layout_cluster_id"] == "table_dense"
    assert payload["extra_context"]["constraints"]["max_cost_units"] == 5
    assert advice.recommendations[0].policy_id == "table_policy"
    assert advice.advice_id
    assert advice.confidence == 0.83
    assert advice.retrieval_source == "LTM"
    assert advice.rabi_used is True
    assert advice.n_neighbors == 4
    assert any(item.policy_id == "default" for item in advice.fallback_recommendations)


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
    assert adaptive.advisor_recommendation is None
    assert adaptive.fallback_candidates
    assert adaptive.route_specialization == "table"

    static_config = PipelineConfig()
    static_config.ahmn.policy_mode = "static"
    static_store = PolicyStore(str(policy_path), default_policy_id="default")
    static_router = PlanRouter(static_config, static_store)
    static = static_router.route(dae, constraints, blocked_policy_ids={"table_policy"})
    assert static.policy.policy_id == "default"
    assert static.advice_source == "static"
    assert static.fallback_reason == "baseline_blocked"


def test_reward_treats_na_requested_values_as_missing() -> None:
    assert _has_field_value(
        "invoice_id",
        {"invoice_id": {"status": "missing", "value": "N/A"}},
        [],
    ) is False


def test_plan_router_prefers_job_overlay_before_adaptive_advice(tmp_path: Path, monkeypatch) -> None:
    policy_path = tmp_path / "policies.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                    {"policy_id": "overlay_policy", "name": "Overlay", "conditions": {}, "actions": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    overlay_path = tmp_path / "job_overlay.json"
    overlay_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "overlay_key": "acme|table_document|table-heavy|4f53cda18c2baa0c",
                        "policy_id": "overlay_policy",
                        "mean_reviewed_f1": 0.91,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("IDPO_JOB_OVERLAY_PATH", str(overlay_path))

    config = PipelineConfig()
    config.ahmn.policy_mode = "adaptive"
    store = PolicyStore(str(policy_path), default_policy_id="default")
    router = PlanRouter(config, store)
    dae = DAEOutput(
        doc_id="d1",
        doc_type="table_document",
        vendor_cluster="acme",
        quality_bin="B",
        complexity_bin="2",
        content_profile="table-heavy",
        quality_score=0.7,
        complexity_score=0.8,
    )
    decision = router.route(dae, SystemConstraints(max_cost_units=5, max_latency_ms=2000))
    assert decision.policy.policy_id == "overlay_policy"
    assert decision.plan_source == "job_overlay"
    assert decision.advice_source == "job_overlay"


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
    assert result.spent_budget_units >= 0.0


def test_pipeline_posts_ahmn_feedback_after_execution(tmp_path: Path, monkeypatch) -> None:
    policy_path = tmp_path / "policies.json"
    policy_path.write_text(
        json.dumps(
            {
                "default_policy_id": "default",
                "policies": [
                    {"policy_id": "default", "name": "Default", "conditions": {}, "actions": {}},
                    {"policy_id": "table_heavy", "name": "Table", "conditions": {"content_profile": ["table-heavy"]}, "actions": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    config = PipelineConfig()
    config.ahmn.enabled = True
    config.ahmn.policy_mode = "adaptive"
    config.ahmn.mode = "http"
    config.ahmn.endpoint = "http://ahmn"
    config.ahmn.advice_endpoint = "/advice"
    config.ahmn.log_endpoint = "/advice/log"
    config.knowledge.policy_store_path = str(policy_path)
    config.rollback.enabled = False

    requests: list[tuple[str, dict[str, object]]] = []

    class DummyResponse:
        def __init__(self, payload: dict[str, object] | None = None) -> None:
            self._payload = payload or {}

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        payload = json.loads(request.data.decode("utf-8"))
        requests.append((request.full_url, payload))
        if request.full_url.endswith("/advice"):
            return DummyResponse(
                {
                    "advice_id": str(uuid4()),
                    "policy_id": "table_heavy",
                    "policy_data": {"action": "table_extraction"},
                    "retrieval_source": "LTM",
                    "confidence": 0.91,
                    "rabi_used": True,
                    "n_neighbors": 3,
                }
            )
        return DummyResponse({})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    pipeline = Pipeline(config=config, run_dir=str(tmp_path / "run"))
    doc = Document(
        doc_id="feedback-doc",
        source="digital",
        path="feedback.txt",
        metadata={"vendor": "acme"},
        pages=[Page(number=1, text="Invoice Number: INV-55\nTotal Amount: 10.00\nTax: 0.80\n")],
    )
    result = pipeline.process_documents([doc])[0]

    assert len(requests) == 2
    advice_request, log_request = requests
    assert advice_request[0] == "http://ahmn/advice"
    assert log_request[0] == "http://ahmn/advice/log"
    assert log_request[1]["policy_id_used"] == "table_heavy"
    assert log_request[1]["document_context"]["vendor"] == "acme"
    assert log_request[1]["document_context"]["vendor_cluster"] == "acme"
    assert "quality_features" in log_request[1]["document_context"]
    assert "structural_features" in log_request[1]["document_context"]
    assert result.feedback_logged is True
    assert result.feedback_error is None
    assert result.advice_id
    assert result.retrieval_source == "LTM"
    assert result.rabi_used is True


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
    assert "feedback_status" in decision_chain
    assert "safety_status" in decision_chain
    assert "advisor_recommendation" in decision_chain["policy"]
    assert "fallback_candidates" in decision_chain["policy"]
    assert "blocked_policy" in decision_chain["policy"]
    assert "feedback_logged" in decision_chain["reward"]
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
                        "tags": ["table", "clean"],
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
    def fake_process_inbox(root, config_path, extraction_fields, run_id, file_paths):  # noqa: ANN001
        config_payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        mode = config_payload.get("ahmn", {}).get("policy_mode", "static")
        adaptive = mode == "adaptive"
        doc = {
            "doc_id": "invoice_basic",
            "policy_id": "table_heavy" if adaptive else "default",
            "latency_ms": 12.0 if adaptive else 10.0,
            "reward": 0.95 if adaptive else 0.9,
            "reward_type": "direct_set_based",
            "reward_details": {"f1": 0.95 if adaptive else 0.9, "precision": 1.0, "recall": 0.9},
            "validation_issue_count": 0,
            "recovered_fields_count": 0,
            "escalation_status": "not_needed",
            "operator_stack": ["structuring.extract", "validation"],
            "advice_source": "ahmn_http" if adaptive else "static",
            "retrieval_source": "LTM" if adaptive else None,
            "advisor_recommendation": {"policy_id": "table_heavy", "score": 0.82, "source": "ahmn_http"} if adaptive else None,
            "fallback_candidates": [{"policy_id": "default", "score": 0.1, "source": "fallback"}] if adaptive else [],
            "feedback_logged": adaptive,
            "feedback_error": None,
            "rabi_used": adaptive,
            "advice_confidence": 0.82 if adaptive else 0.0,
            "fallback_reason": None,
            "blocked_policy": False,
            "rollback_triggered": False,
            "defer_status": "requested" if adaptive else "not_needed",
            "defer_reason": "validation_issues" if adaptive else None,
            "schema_coverage": 1.0,
            "schema_grounding_coverage": 1.0,
            "schema_valid": True,
            "schema_missing_required_count": 0,
            "schema_hallucinated_field_count": 0,
            "structured_fields": {
                "invoice_number": "INV-2026-1001",
                "total_amount": "1388.80",
            },
        }
        return {"run_id": run_id, "run_dir": str(tmp_path / run_id), "doc_records": [doc]}

    monkeypatch.setattr(benchmark_module, "process_inbox", fake_process_inbox)
    evidence = run_benchmark(config_path="configs/idpo_research_config.json", pack_path=str(pack_path))
    report_path = runtime_root / "runs" / "benchmarks" / evidence["experiment"]["benchmark_run_id"] / "paper_evidence.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(payload.keys()) == {"experiment", "conditions", "comparison", "documents"}
    assert "static" in payload["conditions"]
    assert benchmark_module.ADAPTIVE_LABEL in payload["conditions"]
    assert "table" in payload["comparison"]
    assert "groups" in payload["comparison"]
    assert "clean" in payload["comparison"]["groups"]
    assert payload["experiment"]["condition_configs"][benchmark_module.ADAPTIVE_LABEL]["ahmn_enabled"] is True
    assert payload["experiment"]["condition_configs"][benchmark_module.ADAPTIVE_LABEL]["ahmn_mode"] == "http"
    assert payload["experiment"]["condition_configs"][benchmark_module.ADAPTIVE_LABEL]["policy_mode"] == benchmark_module.ADAPTIVE_LABEL
    assert payload["experiment"]["condition_configs"][benchmark_module.ADAPTIVE_LABEL]["runtime_policy_mode"] == "adaptive"
    assert "exact_f1" in payload["comparison"]["table"]
    assert "advice_source_counts" in payload["comparison"]["table"]
    assert "rollback_count" in payload["comparison"]["table"]
    assert "avg_schema_coverage" in payload["comparison"]["table"]
    assert "schema_valid_rate" in payload["comparison"]["table"]
    assert "defer_requested_count" in payload["comparison"]["table"]
    assert "bootstrap" in payload["comparison"]
    assert "overall" in payload["comparison"]["bootstrap"]
    assert "exact_f1_delta" in payload["comparison"]["bootstrap"]["overall"]
    assert payload["comparison"]["table"]["feedback_logged_count"][benchmark_module.ADAPTIVE_LABEL] == 1
    assert payload["comparison"]["table"]["defer_requested_count"][benchmark_module.ADAPTIVE_LABEL] == 1


def test_benchmark_fails_when_adaptive_feedback_is_missing(tmp_path: Path, monkeypatch) -> None:
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
                        "tags": ["table"],
                        "path": "idpo/benchmark/data/invoice_basic.txt",
                        "fields": {"invoice_number": "Invoice identifier"},
                        "expected": {"invoice_number": "INV-2026-1001"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_process_inbox(root, config_path, extraction_fields, run_id, file_paths):  # noqa: ANN001
        config_payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
        adaptive = config_payload.get("ahmn", {}).get("policy_mode") == "adaptive"
        doc = {
            "doc_id": "invoice_basic",
            "policy_id": "table_heavy" if adaptive else "default",
            "latency_ms": 10.0,
            "reward": 0.9,
            "reward_type": "direct_set_based",
            "reward_details": {"f1": 0.9},
            "validation_issue_count": 0,
            "recovered_fields_count": 0,
            "escalation_status": "not_needed",
            "operator_stack": ["structuring.extract"],
            "advice_source": "ahmn_http" if adaptive else "static",
            "retrieval_source": "LTM" if adaptive else None,
            "advisor_recommendation": {"policy_id": "table_heavy", "score": 0.8, "source": "ahmn_http"} if adaptive else None,
            "fallback_candidates": [{"policy_id": "default", "score": 0.1, "source": "fallback"}] if adaptive else [],
            "feedback_logged": False,
            "feedback_error": "unreachable" if adaptive else None,
            "rabi_used": adaptive,
            "advice_confidence": 0.8 if adaptive else 0.0,
            "fallback_reason": None,
            "blocked_policy": False,
            "rollback_triggered": False,
            "defer_status": "requested" if adaptive else "not_needed",
            "defer_reason": "validation_issues" if adaptive else None,
            "schema_coverage": 1.0,
            "schema_grounding_coverage": 1.0,
            "schema_valid": True,
            "schema_missing_required_count": 0,
            "schema_hallucinated_field_count": 0,
            "structured_fields": {"invoice_number": "INV-2026-1001"},
        }
        return {"run_id": run_id, "run_dir": str(tmp_path / run_id), "doc_records": [doc]}

    monkeypatch.setattr(benchmark_module, "process_inbox", fake_process_inbox)
    with pytest.raises(SystemExit) as exc:
        run_benchmark(config_path="configs/idpo_research_config.json", pack_path=str(pack_path))
    assert "feedback logging failed" in str(exc.value)


def test_research_config_and_policy_store_align_with_ahmn_ids() -> None:
    config_payload = json.loads((repo_root() / "configs" / "idpo_research_config.json").read_text(encoding="utf-8"))
    policy_payload = json.loads((repo_root() / "configs" / "policy_store_research.json").read_text(encoding="utf-8"))
    assert config_payload["ahmn"]["enabled"] is True
    assert config_payload["ahmn"]["policy_mode"] == "adaptive"
    assert config_payload["ahmn"]["advice_endpoint"] == "/advice"
    assert config_payload["ahmn"]["log_endpoint"] == "/advice/log"
    assert config_payload["queue"]["enabled"] is False
    assert config_payload["shadow"]["enabled"] is False
    assert {item["policy_id"] for item in policy_payload["policies"]} == {
        "unknown_vendor_safe",
        "forms",
        "noisy_ocr_rescue",
        "scanned_text",
        "long_document_chunked",
        "table_heavy",
        "mixed_content",
        "fast_local_text",
        "default",
    }


def test_research_policy_condition_keys_match_live_dae_outputs(tmp_path: Path) -> None:
    agent = DocumentAnalysisAgent()
    ctx = _ctx(tmp_path)
    doc = Document(
        doc_id="schema-check",
        source="scanned",
        path="schema-check.txt",
        metadata={"vendor": "schema_vendor", "skew_angle": 2.0},
        pages=[
            Page(
                number=1,
                text=(
                    "Claim Number: C-42\n"
                    "Member ID: M-88\n"
                    "Service Date: 2026-03-01\n"
                    "Approval Code: AP-77\n"
                    "Milestone | Due Date | Amount\n"
                    "Phase 1 | 2026-03-10 | 1200.00\n"
                ),
                raw_text=(
                    "Claim Number: C-42\n"
                    "Member ID: M-88\n"
                    "Service Date: 2026-03-01\n"
                    "Approval Code: AP-77\n"
                    "Milestone | Due Date | Amount\n"
                    "Phase 1 | 2026-03-10 | 1200.00\n"
                ),
                image_path="schema.png",
            )
        ],
    )
    dae_output = agent.run({"document": doc}, ctx).artifacts["dae_output"]
    allowed_keys = {
        "doc_type",
        "vendor_cluster",
        "layout_cluster_id",
        "quality_bin",
        "complexity_bin",
        "content_profile",
        "route_bin",
        "quality_score",
        "complexity_score",
        "profile",
        "source",
    }
    allowed_keys.update({f"quality_features.{key}" for key in dae_output.quality_features})
    allowed_keys.update({f"structural_features.{key}" for key in dae_output.structural_features})
    allowed_keys.update({f"signals.{key}" for key in dae_output.signals})

    policy_payload = json.loads((repo_root() / "configs" / "policy_store_research.json").read_text(encoding="utf-8"))
    invalid_keys: dict[str, list[str]] = {}
    for item in policy_payload["policies"]:
        conditions = item.get("conditions", {})
        if not isinstance(conditions, dict):
            continue
        unknown = sorted(key for key in conditions if key not in allowed_keys)
        if unknown:
            invalid_keys[str(item.get("policy_id", "unknown"))] = unknown

    assert invalid_keys == {}


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
