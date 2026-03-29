"""Main pipeline orchestrator coordinating all IDPO agents."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import math
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from idpo.agents.base import AgentContext
from idpo.agents.doc_analysis import DocumentAnalysisAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import (
    Chunk,
    DAEOutput,
    Document,
    Entity,
    ExecutionPlan,
    Section,
    StageSignal,
    SystemConstraints,
    ValidationIssue,
)
from idpo.retrieval.bm25 import BM25Index
from idpo.retrieval.index_bundle import IndexBundle
from idpo.retrieval.vector_store import HashingEmbedder, VectorStore
from idpo.pipeline.executor import PlanExecutor, ExecutionState
from idpo.pipeline.planning import PlanRouter, build_plan
from idpo.pipeline.export import export_simple_workspace as write_simple_workspace
from idpo.pipeline.export import export_structured_results as write_structured_export
from idpo.core.storage import resolve_default_run_dir

logger = logging.getLogger("idpo.pipeline")

@dataclass
class PipelineResult:
    doc_id: str
    path: str
    source: str
    doc_type: str
    vendor_cluster: str
    quality_bin: str
    complexity_bin: str
    content_profile: str
    profile: str
    category: str
    bin: str
    quality_score: float
    complexity_score: float
    entities: list[Entity]
    explicit_entities: list[Entity]
    default_entities: list[Entity]
    explicit_source: str
    sections: list[Section]
    chunks: list[Chunk]
    summary: str
    normalized_entities: dict[str, str]
    validation_issues: list[ValidationIssue]
    recovered_fields: dict[str, str]
    escalated: bool
    field_confidence: dict[str, float]
    stage_signals: list[StageSignal]
    chunk_artifact_id: str
    preprocess_route: list[str]
    preprocess_artifacts: list[str]
    policy_id: str
    policy_name: str
    policy_reason: str
    static_policy_id: str
    static_policy_name: str
    static_policy_reason: str
    plan_id: str
    plan_source: str
    advice_status: str
    plan_budgets: dict[str, object]
    plan_retrieval: dict[str, object]
    plan_token_budget: dict[str, object]
    model_used: str
    model_mode: str
    model_reason: str
    layout_cluster_id: str = "unknown"
    route_bin: str = "standard"
    analysis_confidence: float = 0.0
    analysis_confidence_type: str = "heuristic"
    quality_features: dict[str, float] = field(default_factory=dict)
    structural_features: dict[str, float] = field(default_factory=dict)
    extracted_fields: list[Entity] = field(default_factory=list)
    field_details: dict[str, object] = field(default_factory=dict)
    llm_diagnostics: dict[str, object] = field(default_factory=dict)
    failed_recovery_fields: list[str] = field(default_factory=list)
    recovery_log: list[dict[str, object]] = field(default_factory=list)
    reward: float = 0.0
    reward_type: str = "proxy"
    reward_details: dict[str, object] = field(default_factory=dict)
    escalation_info: dict[str, object] = field(default_factory=dict)
    escalation_status: str = "not_needed"
    advice_source: str = "config"
    advice_id: str | None = None
    advice_confidence: float = 0.0
    retrieval_source: str | None = None
    rabi_used: bool = False
    n_neighbors: int | None = None
    advisor_recommendation: dict[str, object] | None = None
    fallback_candidates: list[dict[str, object]] = field(default_factory=list)
    ranked_policies: list[dict[str, object]] = field(default_factory=list)
    route_specialization: str | None = None
    fallback_reason: str | None = None
    advice_accepted: bool = False
    policy_changed: bool = False
    blocked_policy: bool = False
    rollback_triggered: bool = False
    rollback_reason: str | None = None
    defer_status: str = "not_needed"
    defer_reason: str | None = None
    policy_blocked_count: int = 0
    operator_stack: list[str] = field(default_factory=list)
    dae_signals: dict[str, object] = field(default_factory=dict)
    queue_partition: str = ""
    queue_wait_ms: float = 0.0
    artifacts: dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0
    spent_budget_units: float = 0.0
    feedback_logged: bool = False
    feedback_error: str | None = None
    plan_payload: dict[str, object] = field(default_factory=dict)
    shadow_comparisons: list[dict[str, object]] = field(default_factory=list)

class PolicyRollbackMonitor:
    def __init__(self, run_dir: Path, config: PipelineConfig) -> None:
        self.config = config
        self.path = Path(run_dir) / "policy_rollbacks.json"
        self.history: dict[str, list[dict[str, float]]] = {}
        self.blocked: set[str] = set()
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.history = {key: list(values) for key, values in payload.get("history", {}).items()}
        self.blocked = set(payload.get("blocked", []))

    def record(self) -> None:
        payload = {"history": self.history, "blocked": sorted(self.blocked)}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def is_blocked(self, policy_id: str) -> bool:
        return policy_id in self.blocked

    def update(self, policy_id: str, metrics: dict[str, float], baseline_policy_id: str) -> dict[str, object]:
        if not self.config.rollback.enabled:
            return {
                "blocked": False,
                "triggered": False,
                "reason": "disabled",
                "blocked_count": len(self.blocked),
            }
        with self._lock:
            items = self.history.setdefault(policy_id, [])
            items.append(metrics)
            window = self.config.rollback.window_size
            if len(items) > window:
                self.history[policy_id] = items[-window:]
            reason = self._block_reason(policy_id, baseline_policy_id)
            should_block = reason is not None
            if should_block:
                self.blocked.add(policy_id)
            self.record()
            return {
                "blocked": policy_id in self.blocked,
                "triggered": should_block,
                "reason": reason,
                "blocked_count": len(self.blocked),
            }

    def _block_reason(self, policy_id: str, baseline_policy_id: str) -> str | None:
        if policy_id == baseline_policy_id:
            return None
        items = self.history.get(policy_id, [])
        if len(items) < min(5, self.config.rollback.window_size):
            return None
        latencies = [item.get("latency_ms", 0.0) for item in items]
        failures = [item.get("validation_failure", 0.0) for item in items]
        qualities = [item.get("quality_proxy", 0.0) for item in items]

        latency_p95 = _percentile(latencies, 95)
        failure_rate = sum(1.0 for flag in failures if flag) / len(failures)
        candidate_quality = sum(qualities) / len(qualities) if qualities else 0.0

        baseline_items = self.history.get(baseline_policy_id, [])
        baseline_quality = None
        if baseline_items:
            base_qualities = [item.get("quality_proxy", 0.0) for item in baseline_items]
            baseline_quality = sum(base_qualities) / len(base_qualities)

        if latency_p95 > self.config.rollback.latency_p95_ms:
            return "latency_p95_limit"
        if failure_rate > self.config.rollback.validation_failure_rate:
            return "validation_failure_rate"
        if baseline_quality is not None and (baseline_quality - candidate_quality) > self.config.rollback.quality_drop_threshold:
            return "quality_drop"
        return None

def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(round((percentile / 100) * (len(sorted_vals) - 1)))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return sorted_vals[idx]

class Pipeline:
    def __init__(
        self,
        config: PipelineConfig | None = None,
        run_dir: str | None = None,
        read_only: bool = False,
    ) -> None:
        self.base_run_dir = Path(run_dir) if run_dir else resolve_default_run_dir(uuid.uuid4().hex)
        if self.base_run_dir.name == "primary":
            parent_meta = self.base_run_dir.parent / "run_metadata.json"
            if parent_meta.exists():
                self.base_run_dir = self.base_run_dir.parent
        self.base_run_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = self.base_run_dir / "run_metadata.json"
        if metadata_path.exists() and read_only:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            from idpo.core.config import config_from_dict

            if config is None:
                config = config_from_dict(payload.get("config", {}))
            self.run_id = payload.get("run_id", uuid.uuid4().hex)
        elif metadata_path.exists() and config is None:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            from idpo.core.config import config_from_dict

            config = config_from_dict(payload.get("config", {}))
            self.run_id = payload.get("run_id", uuid.uuid4().hex)
        else:
            self.run_id = uuid.uuid4().hex
        self.config = config or PipelineConfig()
        self.run_dir = self.base_run_dir / "primary" if self.config.shadow.enabled else self.base_run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.artifacts = ArtifactStore(str(self.run_dir / "artifacts"))
        self.provenance = self._init_provenance()
        self.ctx = AgentContext(
            config=self.config,
            artifact_store=self.artifacts,
            provenance=self.provenance,
            run_id=self.run_id,
        )

        self.analysis = DocumentAnalysisAgent()
        self.policy_store = PolicyStore(
            self.config.knowledge.policy_store_path,
            default_policy_id=self.config.knowledge.default_policy_id,
        )
        self.router = PlanRouter(self.config, self.policy_store)
        self.executor = PlanExecutor()
        self.rollback_monitor = PolicyRollbackMonitor(self.run_dir, self.config)
        self._escalation_count = 0
        self._escalation_lock = threading.Lock()
        self._rng = random.Random(self.config.seed)

        if not read_only:
            self._write_run_metadata()

    def _init_provenance(self):
        from idpo.core.provenance import ProvenanceRecorder

        return ProvenanceRecorder(str(self.run_dir / "provenance" / "events.jsonl"))

    def _write_run_metadata(self) -> None:
        payload = {
            "run_id": self.run_id,
            "config": json.loads(json.dumps(self.config, default=lambda o: o.__dict__)),
        }
        (self.base_run_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def process_documents(self, docs: list[Document]) -> list[PipelineResult]:
        if not self.config.queue.enabled:
            return [self.process_document(doc) for doc in docs]

        dae_payloads = []
        for doc in docs:
            analysis_result = self.analysis.run({"document": doc}, self.ctx)
            dae_output = analysis_result.artifacts.get("dae_output")
            analysis_signal = analysis_result.artifacts.get("signal")
            dae_payloads.append((doc, dae_output, analysis_signal))

        partitions: dict[str, list[tuple[Document, DAEOutput, StageSignal | None]]] = {}
        for doc, dae_output, analysis_signal in dae_payloads:
            key = self._queue_partition_key(dae_output, doc)
            partitions.setdefault(key, []).append((doc, dae_output, analysis_signal))

        queue_metrics: dict[str, list[dict[str, float]]] = {}
        results: list[PipelineResult] = []
        max_workers = max(1, self.config.queue.max_workers)
        concurrency = max(1, self.config.queue.per_partition_concurrency)
        semaphores = {key: threading.Semaphore(concurrency) for key in partitions}

        def _run(item: tuple[Document, DAEOutput, StageSignal | None], partition_key: str, depth: int):
            doc_item, dae_output, analysis_signal = item
            start_wait = time.time()
            with semaphores[partition_key]:
                wait_ms = (time.time() - start_wait) * 1000
                queue_metrics.setdefault(partition_key, []).append(
                    {"queue_depth": depth, "queue_wait_ms": wait_ms}
                )
                return self.process_document(
                    doc_item,
                    dae_output=dae_output,
                    analysis_signal=analysis_signal,
                    queue_partition=partition_key,
                    queue_wait_ms=wait_ms,
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            if self.config.queue.fairness_enabled:
                schedule = self._fair_partition_schedule(partitions)
                for partition_key, item, depth in schedule:
                    futures.append(executor.submit(_run, item, partition_key, depth))
            else:
                for partition_key, items in partitions.items():
                    for idx, item in enumerate(items):
                        depth = len(items) - idx
                        futures.append(executor.submit(_run, item, partition_key, depth))
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())

        if queue_metrics:
            (self.run_dir / "queue_metrics.json").write_text(json.dumps(queue_metrics, indent=2), encoding="utf-8")
        return results

    def process_document(
        self,
        doc: Document,
        dae_output: DAEOutput | None = None,
        analysis_signal: StageSignal | None = None,
        queue_partition: str = "",
        queue_wait_ms: float = 0.0,
    ) -> PipelineResult:
        started = time.time()
        raw_text = "\n".join((page.raw_text or page.text) for page in doc.pages)
        raw_artifact = self.artifacts.save_text(
            f"{doc.doc_id}_raw.txt",
            raw_text,
            kind="raw_text",
            raw=True,
            metadata={"doc_id": doc.doc_id, "agent": "intake"},
        )
        self.ctx.provenance.record(
            agent="intake",
            version="v1",
            inputs={"doc_id": doc.doc_id},
            outputs={"output_artifacts": [raw_artifact.artifact_id]},
            parameters={},
            artifacts=[raw_artifact.artifact_id],
            event_type="OperatorExecution",
        )

        if dae_output is None:
            analysis_result = self.analysis.run({"document": doc}, self.ctx)
            dae_output = analysis_result.artifacts.get("dae_output")
            analysis_signal = analysis_result.artifacts.get("signal")

        category, bin_name = self._categorize(dae_output, doc)
        doc_type = dae_output.doc_type
        doc.metadata.update({"category": category, "bin": bin_name, "doc_type": doc_type})

        constraints = SystemConstraints(
            max_cost_units=self.config.plan.max_total_budget_units,
            max_latency_ms=self.config.rollback.latency_p95_ms,
            rate_limit=None,
        )
        blocked_policy_ids = set(self.rollback_monitor.blocked)
        if self.config.shadow.enabled:
            blocked_policy_ids.update(self.config.shadow.candidate_policy_ids)
        route_decision = self.router.route(
            dae_output=dae_output,
            system_constraints=constraints,
            doc_metadata=doc.metadata,
            doc=doc,
            blocked_policy_ids=blocked_policy_ids,
        )
        plan = route_decision.plan
        policy = route_decision.policy
        plan_source = route_decision.plan_source
        advice_source = route_decision.advice_source
        advice_status = route_decision.advice_status
        advice_id = route_decision.advice_id
        advice_confidence = route_decision.advice_confidence
        retrieval_source = route_decision.retrieval_source
        rabi_used = route_decision.rabi_used
        n_neighbors = route_decision.n_neighbors
        advisor_recommendation = route_decision.advisor_recommendation
        fallback_candidates = route_decision.fallback_candidates
        ranked_policies = route_decision.ranked_policies
        route_specialization = route_decision.route_specialization
        fallback_reason = route_decision.fallback_reason
        static_policy = route_decision.baseline_policy
        static_policy_reason = route_decision.baseline_policy_reason
        advice_accepted = route_decision.advice_accepted
        policy_changed = route_decision.policy_changed
        blocked_policy = False
        rollback_triggered = False
        rollback_reason = None

        if self.rollback_monitor.is_blocked(policy.policy_id) and policy.policy_id != self.config.knowledge.default_policy_id:
            fallback = self.policy_store._policy_map.get(self.config.knowledge.default_policy_id, policy)
            plan = build_plan(
                config=self.config,
                dae_output=dae_output,
                policy=fallback,
                system_constraints=constraints,
                source="rollback",
                rationale="blocked_policy",
            )
            policy = fallback
            plan_source = "rollback"
            advice_source = "rollback"
            fallback_reason = "blocked_policy"
            blocked_policy = True
            rollback_reason = "blocked_policy"

        plan_payload = json.loads(json.dumps(plan, default=lambda o: o.__dict__))
        plan_payload.update(
            {
                "advisor_recommendation": advisor_recommendation,
                "fallback_candidates": fallback_candidates,
                "ranked_policies_legacy": ranked_policies,
                "advice_source": advice_source,
                "advice_status": advice_status,
                "advice_id": advice_id,
                "advice_confidence": advice_confidence,
                "retrieval_source": retrieval_source,
                "rabi_used": rabi_used,
                "n_neighbors": n_neighbors,
                "fallback_reason": fallback_reason,
                "static_policy_id": static_policy.policy_id,
                "static_policy_name": static_policy.name,
                "static_policy_reason": static_policy_reason,
                "advice_accepted": advice_accepted,
                "policy_changed": policy_changed,
                "route_specialization": route_specialization,
                "blocked_policy": blocked_policy,
                "operator_stack": [step.operator for step in plan.steps],
            }
        )
        plan_artifact = self.artifacts.save_json(
            f"{doc.doc_id}_plan.json",
            plan_payload,
            kind="plan",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": "router", "policy_id": policy.policy_id},
        )
        self.ctx.provenance.record(
            agent="router",
            version="v1",
            inputs={"doc_id": doc.doc_id, "dae_output": dae_output.__dict__},
            outputs={
                "source": advice_source,
                "advice_status": advice_status,
                "advisor_recommendation": advisor_recommendation,
                "fallback_candidates": fallback_candidates,
                "advice_id": advice_id,
                "advice_confidence": advice_confidence,
                "retrieval_source": retrieval_source,
                "rabi_used": rabi_used,
                "n_neighbors": n_neighbors,
                "fallback_reason": fallback_reason,
                "static_policy_id": static_policy.policy_id,
                "static_policy_name": static_policy.name,
                "static_policy_reason": static_policy_reason,
                "advice_accepted": advice_accepted,
                "policy_changed": policy_changed,
            },
            parameters={"rationale": plan.rationale},
            artifacts=[],
            event_type="PolicyAdvice",
        )
        self.ctx.provenance.record(
            agent="router",
            version="v1",
            inputs={"doc_id": doc.doc_id, "dae_output": dae_output.__dict__},
            outputs={
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "plan_id": plan.plan_id,
                "plan_source": plan_source,
                "advice_source": advice_source,
                "advice_status": advice_status,
                "advice_id": advice_id,
                "advice_confidence": advice_confidence,
                "retrieval_source": retrieval_source,
                "rabi_used": rabi_used,
                "n_neighbors": n_neighbors,
                "route_specialization": route_specialization,
                "static_policy_id": static_policy.policy_id,
                "static_policy_name": static_policy.name,
                "static_policy_reason": static_policy_reason,
                "advice_accepted": advice_accepted,
                "policy_changed": policy_changed,
                "blocked_policy": blocked_policy,
                "operator_stack": [step.operator for step in plan.steps],
                "output_artifacts": [plan_artifact.artifact_id],
            },
            parameters={"rationale": plan.rationale, "fallback_reason": fallback_reason},
            artifacts=[plan_artifact.artifact_id],
            event_type="RouteSelection",
        )

        shadow_executor = None
        shadow_futures: list[concurrent.futures.Future] = []
        if self._should_run_shadow():
            shadow_executor, shadow_futures = self._dispatch_shadow_plans(doc, dae_output, constraints)

        state = self.executor.execute(plan, doc, self.ctx, escalation_count=self._escalation_count)
        if state.escalated:
            with self._escalation_lock:
                self._escalation_count += 1

        if analysis_signal:
            state.stage_signals.insert(0, analysis_signal)

        latency_ms = (time.time() - started) * 1000
        model_used, model_mode, model_reason = self._plan_model_info(plan)
        artifact_ids = {
            "raw": raw_artifact.artifact_id,
            "plan": plan_artifact.artifact_id,
        }
        reward_type, reward_value, reward_details = self._compute_reward(doc, plan, state)
        self.ctx.provenance.record(
            agent="reward",
            version="v1",
            inputs={"doc_id": doc.doc_id, "policy_id": policy.policy_id},
            outputs={"reward": reward_value, "reward_type": reward_type, "reward_details": reward_details},
            parameters={"plan_id": plan.plan_id},
            artifacts=[],
            event_type="RewardComputation",
        )

        self.ctx.provenance.record(
            agent="finalize",
            version="v1",
            inputs={"doc_id": doc.doc_id},
            outputs={
                "entity_count": len(state.entities),
                "chunk_count": len(state.chunks),
                "reward": reward_value,
                "reward_type": reward_type,
                "output_artifacts": list(artifact_ids.values()),
            },
            parameters={"plan_id": plan.plan_id, "policy_id": policy.policy_id},
            artifacts=list(artifact_ids.values()),
            event_type="FinalArtifacts",
        )

        primary_metrics = self._quality_metrics(state, latency_ms)
        rollback_status = self.rollback_monitor.update(
            policy.policy_id,
            primary_metrics,
            self.config.knowledge.default_policy_id,
        )
        rollback_triggered = bool(rollback_status.get("triggered", False))
        if rollback_status.get("reason"):
            rollback_reason = str(rollback_status.get("reason"))
        policy_blocked_count = int(rollback_status.get("blocked_count", len(self.rollback_monitor.blocked)) or 0)
        blocked_policy = blocked_policy or bool(rollback_status.get("blocked", False))

        shadow_comparisons: list[dict[str, object]] = []
        for future in shadow_futures:
            shadow_result = future.result()
            if shadow_result:
                self.rollback_monitor.update(
                    shadow_result["policy_id"],
                    shadow_result["metrics"],
                    self.config.knowledge.default_policy_id,
                )
                comparison = self._shadow_comparison(doc.doc_id, primary_metrics, shadow_result)
                shadow_comparisons.append(comparison)
                self.ctx.provenance.record(
                    agent="shadow",
                    version="v1",
                    inputs={"doc_id": doc.doc_id, "policy_id": shadow_result["policy_id"]},
                    outputs=comparison,
                    parameters={"run_id": self.run_id},
                    artifacts=[],
                    event_type="ShadowComparison",
                )
        if shadow_executor:
            shadow_executor.shutdown(wait=True)
        if shadow_comparisons:
            self._append_shadow_comparisons(shadow_comparisons)

        defer_status = "not_needed"
        defer_reason = None
        if state.escalated:
            defer_status = "requested"
            defer_reason = str(state.escalation_info.get("reason", "") or state.escalation_status or "validation_issues")
        elif state.escalation_status in {"budget_blocked", "quota_blocked", "model_unavailable"}:
            defer_status = "blocked"
            defer_reason = str(state.escalation_info.get("reason", "") or state.escalation_status)

        gate_result = self._evaluate_policy_gates(policy, reward_details, latency_ms)
        if gate_result["violations"]:
            if defer_status == "not_needed":
                defer_status = "requested"
            if not defer_reason:
                defer_reason = "policy_gate_violation"
            if not fallback_reason:
                fallback_reason = "policy_gate_violation"
        reward_details["defer_status"] = defer_status
        reward_details["policy_gate_violations"] = gate_result["violations"]
        reward_details["policy_gate_passed"] = not gate_result["violations"]

        feedback_logged, feedback_error = self._log_ahmn_feedback(
            advice_id=advice_id,
            selected_policy_id=policy.policy_id,
            reward_value=reward_value,
            reward_details=reward_details,
            latency_ms=latency_ms,
            state=state,
            dae_output=dae_output,
            spent_budget_units=state.spent_budget_units,
        )

        return PipelineResult(
            doc_id=doc.doc_id,
            path=doc.path,
            source=doc.source,
            doc_type=doc_type,
            vendor_cluster=dae_output.vendor_cluster,
            quality_bin=dae_output.quality_bin,
            complexity_bin=dae_output.complexity_bin,
            content_profile=dae_output.content_profile,
            profile=doc.profile or dae_output.content_profile,
            category=category,
            bin=bin_name,
            quality_score=dae_output.quality_score,
            complexity_score=dae_output.complexity_score,
            layout_cluster_id=getattr(dae_output, "layout_cluster_id", "unknown"),
            route_bin=getattr(dae_output, "route_bin", "standard"),
            analysis_confidence=getattr(dae_output, "analysis_confidence", analysis_signal.confidence if analysis_signal else dae_output.quality_score),
            analysis_confidence_type=getattr(dae_output, "confidence_type", "heuristic"),
            quality_features=getattr(dae_output, "quality_features", {}),
            structural_features=getattr(dae_output, "structural_features", {}),
            entities=state.entities,
            extracted_fields=state.entities,
            explicit_entities=state.explicit_entities,
            default_entities=state.default_entities,
            explicit_source=state.explicit_source,
            sections=state.sections,
            chunks=state.chunks,
            summary=state.summary,
            normalized_entities=state.normalized_entities,
            validation_issues=state.validation_issues,
            field_details=state.requested_field_status,
            llm_diagnostics=state.llm_diagnostics,
            recovered_fields=state.recovered_fields,
            failed_recovery_fields=state.failed_recovery_fields,
            recovery_log=state.recovery_trace,
            reward=reward_value,
            reward_type=reward_type,
            reward_details=reward_details,
            escalated=state.escalated,
            escalation_info=state.escalation_info,
            escalation_status=state.escalation_status,
            field_confidence=state.field_confidence,
            stage_signals=state.stage_signals,
            chunk_artifact_id=state.chunk_artifact_id,
            preprocess_route=state.preprocess_route,
            preprocess_artifacts=state.preprocess_artifacts,
            policy_id=policy.policy_id,
            policy_name=policy.name,
            policy_reason=plan.rationale,
            static_policy_id=static_policy.policy_id,
            static_policy_name=static_policy.name,
            static_policy_reason=static_policy_reason,
            advice_status=advice_status,
            advice_source=advice_source,
            advice_id=advice_id,
            advice_confidence=advice_confidence,
            retrieval_source=retrieval_source,
            rabi_used=rabi_used,
            n_neighbors=n_neighbors,
            advisor_recommendation=advisor_recommendation,
            fallback_candidates=fallback_candidates,
            ranked_policies=ranked_policies,
            route_specialization=route_specialization,
            fallback_reason=fallback_reason,
            advice_accepted=advice_accepted,
            policy_changed=policy_changed,
            blocked_policy=blocked_policy,
            rollback_triggered=rollback_triggered,
            rollback_reason=rollback_reason,
            defer_status=defer_status,
            defer_reason=defer_reason,
            policy_blocked_count=policy_blocked_count,
            operator_stack=[step.operator for step in plan.steps],
            plan_id=plan.plan_id,
            plan_source=plan.source,
            plan_budgets=plan.budgets,
            plan_retrieval=plan.retrieval,
            plan_token_budget=plan.token_budget,
            plan_payload=plan_payload,
            model_used=model_used,
            model_mode=model_mode,
            model_reason=model_reason,
            dae_signals=dae_output.signals,
            queue_partition=queue_partition,
            queue_wait_ms=queue_wait_ms,
            artifacts=artifact_ids,
            latency_ms=latency_ms,
            spent_budget_units=state.spent_budget_units,
            feedback_logged=feedback_logged,
            feedback_error=feedback_error,
            shadow_comparisons=shadow_comparisons,
        )

    def _categorize(self, dae_output: DAEOutput, doc: Document) -> tuple[str, str]:
        content = dae_output.content_profile
        if dae_output.doc_type == "scanned_document" or content == "image-heavy":
            category = "scanned"
        elif content == "table-heavy":
            category = "table"
        elif content == "form-centric":
            category = "form"
        else:
            category = "text"
        domain = doc.metadata.get("domain")
        bin_name = f"{category}:{domain}" if domain else category
        return category, bin_name

    def _queue_partition_key(self, dae_output: DAEOutput, doc: Document) -> str:
        parts = []
        for key in self.config.queue.partition_keys:
            value = getattr(dae_output, key, None)
            if value is None:
                value = doc.metadata.get(key, "unknown")
            parts.append(str(value))
        return "|".join(parts)

    def _fair_partition_schedule(
        self,
        partitions: dict[str, list[tuple[Document, DAEOutput, StageSignal | None]]],
    ) -> list[tuple[str, tuple[Document, DAEOutput, StageSignal | None], int]]:
        if not partitions:
            return []

        # Round-robin partitions, starting from the smallest queue to avoid starvation.
        queues: dict[str, deque[tuple[Document, DAEOutput, StageSignal | None]]] = {
            key: deque(items) for key, items in partitions.items()
        }
        schedule: list[tuple[str, tuple[Document, DAEOutput, StageSignal | None], int]] = []
        while queues:
            ordered_keys = sorted(queues.keys(), key=lambda key: (len(queues[key]), key))
            exhausted: list[str] = []
            for key in ordered_keys:
                queue = queues[key]
                if not queue:
                    exhausted.append(key)
                    continue
                depth = len(queue)
                item = queue.popleft()
                schedule.append((key, item, depth))
                if not queue:
                    exhausted.append(key)
            for key in exhausted:
                queues.pop(key, None)
        return schedule

    def _plan_model_info(self, plan: ExecutionPlan) -> tuple[str, str, str]:
        for step in plan.steps:
            if step.operator == "structuring.extract":
                model_tier = str(step.params.get("model_tier", self.config.llm.default_mode))
                mode = "cloud" if model_tier in {"cloud", "tier2"} else "local"
                model_name = self.config.llm.cloud_model if mode == "cloud" else self.config.llm.local_model
                return model_name, mode, "plan"
        return self.config.llm.local_model, self.config.llm.default_mode, "plan"

    def _should_run_shadow(self) -> bool:
        return self.config.shadow.enabled and self.config.shadow.sample_rate > 0 and self._rng.random() < self.config.shadow.sample_rate

    def _dispatch_shadow_plans(
        self,
        doc: Document,
        dae_output: DAEOutput,
        constraints: SystemConstraints,
    ) -> tuple[concurrent.futures.ThreadPoolExecutor | None, list[concurrent.futures.Future]]:
        candidates = [pid for pid in self.config.shadow.candidate_policy_ids if pid in self.policy_store._policy_map]
        if not candidates:
            return None, []
        max_policies = max(1, self.config.shadow.max_policies_per_doc)
        selected = candidates[:max_policies]

        futures: list[concurrent.futures.Future] = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(selected))
        for policy_id in selected:
            if self.rollback_monitor.is_blocked(policy_id):
                continue
            policy = self.policy_store._policy_map[policy_id]
            plan = build_plan(
                config=self.config,
                dae_output=dae_output,
                policy=policy,
                system_constraints=constraints,
                source="shadow",
                rationale="shadow_candidate",
            )
            futures.append(executor.submit(self._execute_shadow_plan, doc, dae_output, policy_id, plan))
        if not futures:
            executor.shutdown(wait=False)
            return None, []
        return executor, futures

    def _execute_shadow_plan(
        self,
        doc: Document,
        dae_output: DAEOutput,
        policy_id: str,
        plan: ExecutionPlan,
    ) -> dict[str, object] | None:
        shadow_dir = self.base_run_dir / "shadow" / policy_id
        shadow_dir.mkdir(parents=True, exist_ok=True)
        artifacts = ArtifactStore(str(shadow_dir / "artifacts"))
        from idpo.core.provenance import ProvenanceRecorder

        provenance = ProvenanceRecorder(str(shadow_dir / "provenance" / "events.jsonl"))
        shadow_ctx = AgentContext(
            config=self.config,
            artifact_store=artifacts,
            provenance=provenance,
            run_id=f"{self.run_id}_{policy_id}_shadow",
        )
        shadow_executor = PlanExecutor()
        shadow_doc = self._clone_document(doc)
        started = time.time()
        state = shadow_executor.execute(plan, shadow_doc, shadow_ctx)
        latency_ms = (time.time() - started) * 1000
        metrics = self._quality_metrics(state, latency_ms)
        payload = {
            "doc_id": doc.doc_id,
            "policy_id": policy_id,
            "plan_id": plan.plan_id,
            "latency_ms": latency_ms,
            "validation_issue_count": len(state.validation_issues),
            "entity_count": len(state.entities),
            "quality_proxy": metrics["quality_proxy"],
        }
        (shadow_dir / "shadow_result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {"policy_id": policy_id, "plan_id": plan.plan_id, "metrics": metrics}

    def _quality_metrics(self, state: ExecutionState, latency_ms: float) -> dict[str, float]:
        if state.field_confidence:
            avg_conf = sum(state.field_confidence.values()) / max(len(state.field_confidence), 1)
        elif state.entities:
            avg_conf = sum(entity.confidence for entity in state.entities) / len(state.entities)
        else:
            avg_conf = 0.0
        return {
            "latency_ms": latency_ms,
            "validation_failure": 1.0 if state.validation_issues else 0.0,
            "quality_proxy": avg_conf,
        }

    def _log_ahmn_feedback(
        self,
        advice_id: str | None,
        selected_policy_id: str,
        reward_value: float,
        reward_details: dict[str, object],
        latency_ms: float,
        state: ExecutionState,
        dae_output: DAEOutput,
        spent_budget_units: float,
    ) -> tuple[bool, str | None]:
        if not self.config.ahmn.enabled:
            return False, None
        if not advice_id:
            return False, "missing_advice_id"
        endpoint = (self.config.ahmn.endpoint or "").strip()
        if not endpoint:
            return False, "ahmn_endpoint_missing"

        metrics: dict[str, object] = {
            "f1_score": float((reward_details or {}).get("f1", reward_value) or reward_value),
            "cost": round(float(spent_budget_units or 0.0), 4),
            "processing_time_ms": round(float(latency_ms or 0.0), 2),
            "success": len(state.validation_issues) == 0,
            "schema_valid": bool((reward_details or {}).get("schema_valid", False)),
            "missing_required_count": int((reward_details or {}).get("missing_required_count", 0) or 0),
            "hallucinated_field_count": int((reward_details or {}).get("hallucinated_field_count", 0) or 0),
            "grounding_coverage": round(float((reward_details or {}).get("grounding_coverage", 0.0) or 0.0), 4),
            "defer_status": str((reward_details or {}).get("defer_status", "not_needed")),
            "direct_scored": "f1" in (reward_details or {}),
        }
        if "precision" in reward_details:
            metrics["precision"] = float(reward_details.get("precision", 0.0) or 0.0)
        if "recall" in reward_details:
            metrics["recall"] = float(reward_details.get("recall", 0.0) or 0.0)

        payload = {
            "advice_id": advice_id,
            "policy_id_used": selected_policy_id,
            "metrics": metrics,
            "document_context": {
                "doc_type": dae_output.doc_type,
                "vendor": dae_output.vendor_cluster,
                "vendor_cluster": dae_output.vendor_cluster,
                "content_profile": dae_output.content_profile,
                "route_bin": dae_output.route_bin,
                "layout_cluster_id": dae_output.layout_cluster_id,
                "quality_bin": dae_output.quality_bin,
                "complexity_bin": dae_output.complexity_bin,
                "quality_features": dae_output.quality_features,
                "structural_features": dae_output.structural_features,
            },
        }
        log_url = endpoint.rstrip("/") + self.config.ahmn.log_endpoint
        request = urllib.request.Request(
            log_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        timeout = max(self.config.ahmn.timeout_ms, 10) / 1000.0
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                self.ctx.provenance.record(
                    agent="ahmn_feedback",
                    version="v1",
                    inputs={"advice_id": advice_id, "policy_id_used": selected_policy_id},
                    outputs={"logged": True},
                    parameters={"log_endpoint": self.config.ahmn.log_endpoint, "metrics": metrics},
                    artifacts=[],
                    event_type="AHMNFeedback",
                )
                return True, None
        except urllib.error.HTTPError as exc:
            error = f"http_{exc.code}"
        except urllib.error.URLError:
            error = "unreachable"
        except TimeoutError:
            error = "timeout"
        except Exception:
            error = "unknown_error"

        self.ctx.provenance.record(
            agent="ahmn_feedback",
            version="v1",
            inputs={"advice_id": advice_id, "policy_id_used": selected_policy_id},
            outputs={"logged": False, "error": error},
            parameters={"log_endpoint": self.config.ahmn.log_endpoint, "metrics": metrics},
            artifacts=[],
            event_type="AHMNFeedback",
        )
        return False, error

    def _compute_reward(
        self,
        doc: Document,
        plan: ExecutionPlan,
        state: ExecutionState,
    ) -> tuple[str, float, dict[str, object]]:
        expected_fields = self._expected_fields_for_reward(plan, state)
        schema_details = self._schema_quality_from_state(expected_fields, state)
        if expected_fields:
            extracted_expected = {
                key
                for key in expected_fields
                if self._has_field_value(key, state.requested_field_status, state.entities)
            }
            all_extracted_keys = {entity.key for entity in state.entities}
            tp = len(extracted_expected)
            fn = max(len(expected_fields) - tp, 0)
            fp = len([key for key in all_extracted_keys if key not in expected_fields])
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
            details = {
                "doc_id": doc.doc_id,
                "expected_fields": expected_fields,
                "extracted_field_count": len(all_extracted_keys),
                "true_positive_count": tp,
                "false_positive_count": fp,
                "false_negative_count": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                **schema_details,
            }
            return "direct_set_based", round(f1, 4), details

        validation_component = 1.0 if not state.validation_issues else 0.0
        unresolved_fields = len({issue.field for issue in state.validation_issues})
        unresolved_penalty = min(unresolved_fields * 0.15, 0.6)
        recovery_component = min(len(state.recovered_fields) * 0.1, 0.3)
        confidence_component = 0.0
        if state.field_confidence:
            confidence_component = sum(state.field_confidence.values()) / max(len(state.field_confidence), 1)
        elif state.entities:
            confidence_component = sum(entity.confidence for entity in state.entities) / max(len(state.entities), 1)
        escalation_penalty = 0.15 if state.escalated else 0.0
        proxy_value = max(
            0.0,
            min(validation_component + recovery_component + (confidence_component * 0.4) - unresolved_penalty - escalation_penalty, 1.0),
        )
        details = {
            "doc_id": doc.doc_id,
            "validation_component": round(validation_component, 4),
            "recovery_component": round(recovery_component, 4),
            "confidence_component": round(confidence_component, 4),
            "unresolved_field_penalty": round(unresolved_penalty, 4),
            "escalation_penalty": round(escalation_penalty, 4),
            "unresolved_field_count": unresolved_fields,
            **schema_details,
        }
        return "proxy", round(proxy_value, 4), details

    def _schema_quality_from_state(
        self,
        expected_fields: list[str],
        state: ExecutionState,
    ) -> dict[str, object]:
        target_fields = [str(key).strip() for key in expected_fields if str(key).strip()]
        if not target_fields:
            target_fields = sorted(
                str(key).strip()
                for key in state.requested_field_status.keys()
                if str(key).strip()
            )
        target_set = set(target_fields)
        extracted_keys: set[str] = set()
        extracted_target_keys: set[str] = set()
        grounded_target_keys: set[str] = set()

        for entity in state.entities:
            key = str(entity.key).strip()
            if not key:
                continue
            extracted_keys.add(key)
            if key in target_set:
                extracted_target_keys.add(key)
                if self._entity_is_grounded(entity):
                    grounded_target_keys.add(key)

        for key in target_fields:
            if self._has_field_value(key, state.requested_field_status, state.entities):
                extracted_target_keys.add(key)

        required_field_count = len(target_set)
        extracted_required_count = len(extracted_target_keys)
        missing_required_count = max(required_field_count - extracted_required_count, 0)
        hallucinated_field_count = len([key for key in extracted_keys if key not in target_set]) if target_set else 0
        grounded_field_count = len(grounded_target_keys)
        coverage = round(extracted_required_count / required_field_count, 4) if required_field_count else 0.0
        grounding_coverage = round(grounded_field_count / extracted_required_count, 4) if extracted_required_count else 0.0
        schema_valid = (
            required_field_count > 0
            and missing_required_count == 0
            and hallucinated_field_count == 0
            and len(state.validation_issues) == 0
        )
        return {
            "required_field_count": required_field_count,
            "extracted_required_count": extracted_required_count,
            "missing_required_count": missing_required_count,
            "hallucinated_field_count": hallucinated_field_count,
            "grounded_field_count": grounded_field_count,
            "schema_coverage": coverage,
            "grounding_coverage": grounding_coverage,
            "schema_valid": schema_valid,
        }

    def _entity_is_grounded(self, entity: Entity) -> bool:
        if entity.page is not None or entity.span is not None:
            return True
        bbox = (entity.metadata or {}).get("bbox")
        return isinstance(bbox, list) and len(bbox) >= 4

    def _evaluate_policy_gates(
        self,
        policy,
        reward_details: dict[str, object],
        latency_ms: float,
    ) -> dict[str, object]:
        metadata = policy.metadata if isinstance(getattr(policy, "metadata", None), dict) else {}
        violations: list[str] = []
        if metadata.get("schema_valid_required") and not bool(reward_details.get("schema_valid", False)):
            violations.append("schema_valid_required")
        max_missing = metadata.get("max_missing_required")
        if isinstance(max_missing, (int, float)) and int(reward_details.get("missing_required_count", 0) or 0) > int(max_missing):
            violations.append("max_missing_required")
        max_hallucinated = metadata.get("max_hallucinated_fields")
        if isinstance(max_hallucinated, (int, float)) and int(reward_details.get("hallucinated_field_count", 0) or 0) > int(max_hallucinated):
            violations.append("max_hallucinated_fields")
        min_grounding = metadata.get("min_grounding_coverage")
        if isinstance(min_grounding, (int, float)) and float(reward_details.get("grounding_coverage", 0.0) or 0.0) < float(min_grounding):
            violations.append("min_grounding_coverage")
        max_latency = metadata.get("max_latency_ms")
        if isinstance(max_latency, (int, float)) and float(latency_ms or 0.0) > float(max_latency):
            violations.append("max_latency_ms")
        return {"violations": violations}

    def _expected_fields_for_reward(self, plan: ExecutionPlan, state: ExecutionState) -> list[str]:
        requested = sorted(key for key in state.requested_field_status.keys() if str(key).strip())
        if requested and state.explicit_source in {"plan", "policy", "rules"}:
            return requested
        for step in plan.steps:
            if step.operator == "structuring.extract":
                explicit = step.params.get("explicit_entities", [])
                if isinstance(explicit, list):
                    expected = [str(item).strip() for item in explicit if str(item).strip()]
                    if expected:
                        return expected
        return []

    def _has_field_value(
        self,
        key: str,
        requested_field_status: dict[str, dict[str, object]],
        entities: list[Entity],
    ) -> bool:
        status = requested_field_status.get(key) or {}
        value = str(status.get("value", "") or "").strip()
        if value:
            return True
        return any(entity.key == key and str(entity.value).strip() for entity in entities)

    def _shadow_comparison(
        self,
        doc_id: str,
        primary_metrics: dict[str, float],
        shadow_result: dict[str, object],
    ) -> dict[str, object]:
        shadow_metrics = shadow_result.get("metrics", {})
        if not isinstance(shadow_metrics, dict):
            shadow_metrics = {}
        return {
            "doc_id": doc_id,
            "policy_id": str(shadow_result.get("policy_id", "")),
            "plan_id": str(shadow_result.get("plan_id", "")),
            "canonical_latency_ms": float(primary_metrics.get("latency_ms", 0.0)),
            "shadow_latency_ms": float(shadow_metrics.get("latency_ms", 0.0)),
            "canonical_validation_failure": float(primary_metrics.get("validation_failure", 0.0)),
            "shadow_validation_failure": float(shadow_metrics.get("validation_failure", 0.0)),
            "canonical_quality_proxy": float(primary_metrics.get("quality_proxy", 0.0)),
            "shadow_quality_proxy": float(shadow_metrics.get("quality_proxy", 0.0)),
            "canonical_retrieval_proxy": None,
            "shadow_retrieval_proxy": None,
        }

    def _append_shadow_comparisons(self, comparisons: list[dict[str, object]]) -> None:
        metrics_dir = self.run_dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        path = metrics_dir / self.config.shadow.comparison_file
        existing: list[dict[str, object]] = []
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, list):
                    existing = payload
            except Exception:
                existing = []
        existing.extend(comparisons)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def _clone_document(self, doc: Document) -> Document:
        pages = []
        for page in doc.pages:
            pages.append(
                type(page)(
                    number=page.number,
                    text=page.text,
                    raw_text=page.raw_text,
                    image_path=page.image_path,
                    metadata=dict(page.metadata),
                )
            )
        return Document(
            doc_id=doc.doc_id,
            source=doc.source,
            path=doc.path,
            pages=pages,
            metadata=dict(doc.metadata),
            profile=doc.profile,
            quality_score=doc.quality_score,
            complexity_score=doc.complexity_score,
            doc_type=doc.doc_type,
            vendor_cluster=doc.vendor_cluster,
            quality_bin=doc.quality_bin,
            complexity_bin=doc.complexity_bin,
            content_profile=doc.content_profile,
            dae_signals=dict(doc.dae_signals),
        )

    def build_index(self, results: list[PipelineResult], directory: str | None = None) -> IndexBundle:
        chunks: dict[str, Chunk] = {}
        chunk_artifact_ids: list[str] = []
        for result in results:
            for chunk in result.chunks:
                chunks[chunk.chunk_id] = chunk
            if result.chunk_artifact_id:
                chunk_artifact_ids.append(result.chunk_artifact_id)
        embedder = HashingEmbedder(dim=256, seed=self.config.seed)
        vector_store = VectorStore(embedder)
        vector_store.add(chunks.values())
        bm25 = BM25Index()
        bm25.add(chunks.values())
        bundle = IndexBundle(vector_store=vector_store, bm25=bm25, chunks=chunks)
        if directory:
            bundle.save(directory)
            embedding_artifact = self.artifacts.register_external(
                str(Path(directory) / "vectors.json"),
                kind="embedding_index",
                metadata={"agent": "embedding", "version": "v1", "dim": embedder.dim, "seed": self.config.seed},
            )
            self.ctx.provenance.record(
                agent="embedding",
                version="v1",
                inputs={"doc_ids": [result.doc_id for result in results], "input_artifacts": chunk_artifact_ids, "chunk_ids": list(chunks.keys())},
                outputs={"output_artifacts": [embedding_artifact.artifact_id]},
                parameters={"embed_dim": embedder.dim, "seed": self.config.seed},
                artifacts=[embedding_artifact.artifact_id],
            )
        return bundle

    def export_structured_results(self, results: list[PipelineResult], output_path: str) -> dict[str, object]:
        export_payload = write_structured_export(results, output_path)
        artifact_ids = []
        if export_payload.get("format") == "xlsx":
            artifact = self.artifacts.register_external(
                export_payload["path"],
                kind="structured_export",
                metadata={"agent": "export_structured", "format": "xlsx"},
            )
            artifact_ids.append(artifact.artifact_id)
        else:
            for path in export_payload.get("paths", []):
                artifact = self.artifacts.register_external(
                    path,
                    kind="structured_export",
                    metadata={"agent": "export_structured", "format": "csv"},
                )
                artifact_ids.append(artifact.artifact_id)
        self.ctx.provenance.record(
            agent="export_structured",
            version="v1",
            inputs={"doc_ids": [result.doc_id for result in results]},
            outputs={"output_artifacts": artifact_ids, "format": export_payload.get("format")},
            parameters={"output_path": output_path},
            artifacts=artifact_ids,
        )
        return export_payload

    def export_simple_workspace(
        self, docs: list[Document], results: list[PipelineResult], output_dir: str
    ) -> dict[str, object]:
        payload = write_simple_workspace(docs, results, output_dir)
        artifact = self.artifacts.register_external(
            payload["manifest"],
            kind="simple_manifest",
            metadata={"agent": "export_simple_workspace"},
        )
        self.ctx.provenance.record(
            agent="export_simple_workspace",
            version="v1",
            inputs={"doc_ids": [doc.doc_id for doc in docs]},
            outputs={"output_artifacts": [artifact.artifact_id], "count": payload.get("count", 0)},
            parameters={"output_dir": output_dir},
            artifacts=[artifact.artifact_id],
        )
        return payload
