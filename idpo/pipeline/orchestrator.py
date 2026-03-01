from __future__ import annotations

import concurrent.futures
import json
import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from idpo.agents.base import AgentContext
from idpo.agents.doc_analysis import DocumentAnalysisAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.budget import BudgetManager
from idpo.core.calibration import ConfidenceCalibrator
from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import (
    Chunk,
    DAEOutput,
    Document,
    Entity,
    ExecutionPlan,
    FieldExtraction,
    Section,
    StageSignal,
    SystemConstraints,
    ValidationIssue,
)
from idpo.pipeline.executor import ExecutionState, PlanExecutor
from idpo.pipeline.export import export_simple_workspace as write_simple_workspace
from idpo.pipeline.export import export_structured_results as write_structured_export
from idpo.pipeline.planning import PlanRouter, build_plan
from idpo.pipeline.policy_safety import PolicySafetyMonitor
from idpo.pipeline.run_layout import RunLayout
from idpo.retrieval.bm25 import BM25Index
from idpo.retrieval.index_bundle import IndexBundle
from idpo.retrieval.vector_store import HashingEmbedder, VectorStore


logger = logging.getLogger("idpo.pipeline")


@dataclass
class PipelineResult:
    doc_id: str
    path: str
    source: str
    doc_type: str
    vendor_cluster: str
    layout_cluster_id: str
    quality_bin: str
    complexity_bin: str
    route_bin: str
    content_profile: str
    profile: str
    category: str
    bin: str
    quality_score: float
    complexity_score: float
    analysis_confidence: float
    analysis_confidence_type: str
    quality_features: Dict[str, float]
    structural_features: Dict[str, float]
    entities: List[Entity]
    extracted_fields: List[FieldExtraction]
    explicit_entities: List[Entity]
    default_entities: List[Entity]
    explicit_source: str
    sections: List[Section]
    chunks: List[Chunk]
    summary: str
    normalized_entities: Dict[str, str]
    validation_issues: List[ValidationIssue]
    field_details: Dict[str, Dict[str, object]]
    recovered_fields: Dict[str, str]
    failed_recovery_fields: List[str]
    recovery_log: List[Dict[str, object]]
    escalated: bool
    escalation_info: Dict[str, object]
    field_confidence: Dict[str, float]
    stage_signals: List[StageSignal]
    chunk_artifact_id: str
    preprocess_route: List[str]
    preprocess_artifacts: List[str]
    policy_id: str
    policy_name: str
    policy_reason: str
    advice_source: str
    ranked_policies: List[Dict[str, object]]
    route_specialization: str
    operator_stack: Dict[str, object]
    plan_id: str
    plan_source: str
    plan_budgets: Dict[str, object]
    plan_retrieval: Dict[str, object]
    plan_token_budget: Dict[str, object]
    model_used: str
    model_mode: str
    model_reason: str
    dae_signals: Dict[str, object] = field(default_factory=dict)
    queue_partition: str = ""
    queue_wait_ms: float = 0.0
    artifacts: Dict[str, str] = field(default_factory=dict)
    latency_ms: float = 0.0
    plan_payload: Dict[str, object] = field(default_factory=dict)
    shadow_comparisons: List[Dict[str, object]] = field(default_factory=list)


class Pipeline:
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        run_dir: Optional[str] = None,
        read_only: bool = False,
    ) -> None:
        self.base_run_dir = Path(run_dir) if run_dir else Path("runs") / uuid.uuid4().hex
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
        self.layout = RunLayout(self.run_dir)

        self.artifacts = ArtifactStore(str(self.run_dir / "artifacts"))
        self.provenance = self._init_provenance()
        self.budget_manager = BudgetManager(self.config.budget)
        self.calibrator = self._load_calibrator()
        self.ctx = AgentContext(
            config=self.config,
            artifact_store=self.artifacts,
            provenance=self.provenance,
            run_id=self.run_id,
            budget_manager=self.budget_manager,
            calibrator=self.calibrator,
        )

        self.analysis = DocumentAnalysisAgent()
        self.policy_store = PolicyStore(
            self.config.knowledge.policy_store_path,
            default_policy_id=self.config.knowledge.default_policy_id,
        )
        self.router = PlanRouter(self.config, self.policy_store)
        self.executor = PlanExecutor()
        self.safety_monitor = PolicySafetyMonitor(
            self.run_dir,
            self.config.rollback,
            baseline_policy_id=self.config.knowledge.default_policy_id,
        )
        self._escalation_count = 0
        self._escalation_lock = threading.Lock()
        self._rng = random.Random(self.config.seed)
        self._metrics_lock = threading.Lock()
        self._doc_metrics: List[Dict[str, object]] = []

        if not read_only:
            self._write_run_metadata()

    def _init_provenance(self):
        from idpo.core.provenance import ProvenanceRecorder

        return ProvenanceRecorder(str(self.run_dir / "provenance.jsonl"))

    def _load_calibrator(self) -> Optional[ConfidenceCalibrator]:
        if not self.config.calibration.enabled:
            return None
        model_path = self.config.calibration.model_path
        if not model_path:
            return None
        path = Path(model_path)
        if not path.exists():
            return None
        try:
            return ConfidenceCalibrator.load(str(path))
        except Exception:
            return None

    def _write_run_metadata(self) -> None:
        payload = {
            "run_id": self.run_id,
            "config": json.loads(json.dumps(self.config, default=lambda o: o.__dict__)),
        }
        (self.base_run_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def process_documents(self, docs: List[Document]) -> List[PipelineResult]:
        self.layout.write_input_manifest(
            {
                "doc_id": doc.doc_id,
                "path": doc.path,
                "source": doc.source,
                "page_count": len(doc.pages),
                "metadata": doc.metadata,
            }
            for doc in docs
        )
        if not self.config.queue.enabled:
            results = [self.process_document(doc) for doc in docs]
            self._finalize_run_outputs()
            return results

        dae_payloads = []
        for doc in docs:
            analysis_result = self.analysis.run({"document": doc}, self.ctx)
            dae_output = analysis_result.artifacts.get("dae_output")
            analysis_signal = analysis_result.artifacts.get("signal")
            dae_payloads.append((doc, dae_output, analysis_signal))

        partitions: Dict[str, List[Tuple[Document, DAEOutput, Optional[StageSignal]]]] = {}
        for doc, dae_output, analysis_signal in dae_payloads:
            key = self._queue_partition_key(dae_output, doc)
            partitions.setdefault(key, []).append((doc, dae_output, analysis_signal))

        queue_metrics: Dict[str, List[Dict[str, float]]] = {}
        max_workers = max(1, self.config.queue.max_workers)
        concurrency = max(1, self.config.queue.per_partition_concurrency)
        semaphores = {key: threading.Semaphore(concurrency) for key in partitions}
        scheduled = self._fair_partition_schedule(partitions)
        result_map: Dict[str, PipelineResult] = {}

        def _run(item: Tuple[Document, DAEOutput, Optional[StageSignal]], partition_key: str, depth: int):
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
            futures = [
                executor.submit(_run, item, partition_key, depth)
                for partition_key, item, depth in scheduled
            ]
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                result_map[result.doc_id] = result

        if queue_metrics:
            self.layout.write_metrics({"queue_depth": queue_metrics}, filename="queue_metrics.json")
        ordered_results = [result_map[doc.doc_id] for doc in docs if doc.doc_id in result_map]
        self._finalize_run_outputs()
        return ordered_results

    def _fair_partition_schedule(
        self,
        partitions: Dict[str, List[Tuple[Document, DAEOutput, Optional[StageSignal]]]],
    ) -> List[Tuple[str, Tuple[Document, DAEOutput, Optional[StageSignal]], int]]:
        copies = {key: list(items) for key, items in partitions.items()}
        order: List[Tuple[str, Tuple[Document, DAEOutput, Optional[StageSignal]], int]] = []
        while True:
            progressed = False
            for partition_key in sorted(copies.keys()):
                items = copies[partition_key]
                if not items:
                    continue
                progressed = True
                current_depth = len(items)
                item = items.pop(0)
                order.append((partition_key, item, current_depth))
            if not progressed:
                break
        return order

    def process_document(
        self,
        doc: Document,
        dae_output: Optional[DAEOutput] = None,
        analysis_signal: Optional[StageSignal] = None,
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
            max_cost_units=self.config.budget.max_cost_per_doc,
            max_latency_ms=self.config.budget.max_latency_per_doc_ms,
            rate_limit=None,
        )

        route_selection = self.router.route(
            dae_output=dae_output,
            system_constraints=constraints,
            doc_metadata=doc.metadata,
            doc=doc,
            blocked_policy_ids=set(self.safety_monitor.blocked),
        )

        plan = route_selection.plan
        policy = route_selection.policy
        plan_source = route_selection.source

        plan_payload = json.loads(json.dumps(plan, default=lambda o: o.__dict__))
        plan_artifact = self.artifacts.save_json(
            f"{doc.doc_id}_plan.json",
            plan_payload,
            kind="plan",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": "router", "policy_id": policy.policy_id},
        )

        ranked_payload = [item.__dict__ for item in route_selection.advice.recommendations]
        self.ctx.provenance.record(
            agent="policy_advisor",
            version="v1",
            inputs={"doc_id": doc.doc_id, "dae_output": dae_output.__dict__},
            outputs={
                "advice_source": route_selection.advice.source,
                "fallback_used": route_selection.advice.fallback_used,
                "recommendations": ranked_payload,
            },
            parameters={"objective": self.config.ahmn.objective},
            event_type="PolicyAdvice",
        )
        self.ctx.provenance.record(
            agent="router",
            version="v2",
            inputs={"doc_id": doc.doc_id, "dae_output": dae_output.__dict__},
            outputs={
                "policy_id": policy.policy_id,
                "policy_name": policy.name,
                "plan_id": plan.plan_id,
                "plan_source": plan_source,
                "specialization": route_selection.specialization,
                "operator_stack": route_selection.operator_stack,
                "output_artifacts": [plan_artifact.artifact_id],
            },
            parameters={"rationale": plan.rationale},
            artifacts=[plan_artifact.artifact_id],
            event_type="RouteSelection",
        )

        state = self.executor.execute(plan, doc, self.ctx, escalation_count=self._escalation_count)
        if state.escalated:
            with self._escalation_lock:
                self._escalation_count += 1

        if analysis_signal:
            state.stage_signals.insert(0, analysis_signal)

        latency_ms = (time.time() - started) * 1000
        model_used, model_mode, model_reason = self._plan_model_info(plan)
        artifact_ids = {"raw": raw_artifact.artifact_id, "plan": plan_artifact.artifact_id}

        self.ctx.provenance.record(
            agent="finalize",
            version="v1",
            inputs={"doc_id": doc.doc_id},
            outputs={
                "entity_count": len(state.entities),
                "chunk_count": len(state.chunks),
                "output_artifacts": list(artifact_ids.values()),
            },
            parameters={"plan_id": plan.plan_id, "policy_id": policy.policy_id},
            artifacts=list(artifact_ids.values()),
            event_type="FinalArtifacts",
        )

        primary_metrics = self._quality_metrics(state, latency_ms)
        decision = self.safety_monitor.update(policy.policy_id, primary_metrics)
        if decision.triggered:
            self.ctx.provenance.record(
                agent="policy_safety_monitor",
                version="v1",
                inputs={"doc_id": doc.doc_id, "policy_id": policy.policy_id},
                outputs={
                    "rollback_triggered": True,
                    "reason": decision.reason,
                    "revert_to_policy_id": decision.revert_to_policy_id,
                    "deltas": decision.deltas,
                },
                parameters={},
                event_type="RollbackTriggered",
            )

        shadow_comparisons = []
        if self._should_run_shadow():
            shadow_comparisons = self._run_shadow_plans(
                doc=doc,
                dae_output=dae_output,
                constraints=constraints,
                canonical_metrics=primary_metrics,
                canonical_policy_id=policy.policy_id,
            )

        result = PipelineResult(
            doc_id=doc.doc_id,
            path=doc.path,
            source=doc.source,
            doc_type=doc_type,
            vendor_cluster=dae_output.vendor_cluster,
            layout_cluster_id=dae_output.layout_cluster_id,
            quality_bin=dae_output.quality_bin,
            complexity_bin=dae_output.complexity_bin,
            route_bin=dae_output.route_bin,
            content_profile=dae_output.content_profile,
            profile=doc.profile or dae_output.content_profile,
            category=category,
            bin=bin_name,
            quality_score=dae_output.quality_score,
            complexity_score=dae_output.complexity_score,
            analysis_confidence=dae_output.analysis_confidence,
            analysis_confidence_type=dae_output.confidence_type,
            quality_features=dae_output.quality_features,
            structural_features=dae_output.structural_features,
            entities=state.entities,
            extracted_fields=state.fields,
            explicit_entities=state.explicit_entities,
            default_entities=state.default_entities,
            explicit_source=state.explicit_source,
            sections=state.sections,
            chunks=state.chunks,
            summary=state.summary,
            normalized_entities=state.normalized_entities,
            validation_issues=state.validation_issues,
            field_details=state.field_details,
            recovered_fields=state.recovered_fields,
            failed_recovery_fields=state.failed_recovery_fields,
            recovery_log=state.recovery_log,
            escalated=state.escalated,
            escalation_info=state.escalation_info,
            field_confidence=state.field_confidence,
            stage_signals=state.stage_signals,
            chunk_artifact_id=state.chunk_artifact_id,
            preprocess_route=state.preprocess_route,
            preprocess_artifacts=state.preprocess_artifacts,
            policy_id=policy.policy_id,
            policy_name=policy.name,
            policy_reason=plan.rationale,
            advice_source=route_selection.advice.source,
            ranked_policies=ranked_payload,
            route_specialization=route_selection.specialization,
            operator_stack=route_selection.operator_stack,
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
            shadow_comparisons=shadow_comparisons,
        )
        self._write_stage_outputs(result)
        with self._metrics_lock:
            self._doc_metrics.append(
                {
                    "doc_id": result.doc_id,
                    "latency_ms": result.latency_ms,
                    "policy_id": result.policy_id,
                    "validation_issue_count": len(result.validation_issues),
                    "avg_field_confidence": (
                        sum(result.field_confidence.values()) / len(result.field_confidence)
                        if result.field_confidence
                        else 0.0
                    ),
                    "escalated": result.escalated,
                    "queue_partition": result.queue_partition,
                }
            )
        return result

    def _write_stage_outputs(self, result: PipelineResult) -> None:
        self.layout.write_stage_doc(
            "dae",
            result.doc_id,
            {
                "doc_type": result.doc_type,
                "vendor_cluster": result.vendor_cluster,
                "layout_cluster_id": result.layout_cluster_id,
                "quality_bin": result.quality_bin,
                "complexity_bin": result.complexity_bin,
                "route_bin": result.route_bin,
                "content_profile": result.content_profile,
                "quality_score": result.quality_score,
                "complexity_score": result.complexity_score,
                "analysis_confidence": result.analysis_confidence,
                "confidence_type": result.analysis_confidence_type,
                "quality_features": result.quality_features,
                "structural_features": result.structural_features,
                "signals": result.dae_signals,
            },
        )
        self.layout.write_stage_doc(
            "route",
            result.doc_id,
            {
                "policy_id": result.policy_id,
                "policy_name": result.policy_name,
                "policy_reason": result.policy_reason,
                "advice_source": result.advice_source,
                "ranked_policies": result.ranked_policies,
                "specialization": result.route_specialization,
                "operator_stack": result.operator_stack,
                "plan_id": result.plan_id,
                "plan_source": result.plan_source,
                "plan_budgets": result.plan_budgets,
            },
        )
        self.layout.write_stage_doc(
            "preprocess",
            result.doc_id,
            {
                "route": result.preprocess_route,
                "artifacts": result.preprocess_artifacts,
                "signals": [
                    signal.__dict__
                    for signal in result.stage_signals
                    if signal.stage in {"ocr", "deskew", "denoise", "table_form"}
                ],
            },
        )
        self.layout.write_stage_doc(
            "extract",
            result.doc_id,
            {
                "entities": [entity.__dict__ for entity in result.entities],
                "fields": [field.__dict__ for field in result.extracted_fields],
                "explicit_source": result.explicit_source,
            },
        )
        self.layout.write_stage_doc(
            "validate",
            result.doc_id,
            {
                "issues": [issue.__dict__ for issue in result.validation_issues],
                "field_confidence": result.field_confidence,
                "field_details": result.field_details,
                "normalized": result.normalized_entities,
            },
        )
        self.layout.write_stage_doc(
            "recover",
            result.doc_id,
            {
                "recovered_fields": result.recovered_fields,
                "failed_fields": result.failed_recovery_fields,
                "retry_log": result.recovery_log,
            },
        )
        self.layout.write_stage_doc(
            "escalate",
            result.doc_id,
            {
                "escalated": result.escalated,
                "details": result.escalation_info,
            },
        )

    def _categorize(self, dae_output: DAEOutput, doc: Document) -> Tuple[str, str]:
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

    def _plan_model_info(self, plan: ExecutionPlan) -> Tuple[str, str, str]:
        for step in plan.steps:
            if step.operator == "structuring.extract":
                model_tier = str(step.params.get("model_tier", self.config.llm.default_mode))
                mode = "cloud" if model_tier in {"cloud", "tier2"} else "local"
                model_name = self.config.llm.cloud_model if mode == "cloud" else self.config.llm.local_model
                return model_name, mode, "plan"
        return self.config.llm.local_model, self.config.llm.default_mode, "plan"

    def _should_run_shadow(self) -> bool:
        return (
            self.config.shadow.enabled
            and self.config.shadow.sample_rate > 0
            and self._rng.random() < self.config.shadow.sample_rate
        )

    def _run_shadow_plans(
        self,
        doc: Document,
        dae_output: DAEOutput,
        constraints: SystemConstraints,
        canonical_metrics: Dict[str, float],
        canonical_policy_id: str,
    ) -> List[Dict[str, object]]:
        candidates = [
            pid
            for pid in self.config.shadow.candidate_policy_ids
            if pid in self.policy_store._policy_map
            and pid != canonical_policy_id
            and not self.safety_monitor.is_blocked(pid)
        ]
        if not candidates:
            return []

        max_policies = max(1, self.config.shadow.max_policies_per_doc)
        selected = candidates[:max_policies]
        comparisons: List[Dict[str, object]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(selected)) as executor:
            futures = [
                executor.submit(self._execute_shadow_plan, doc, dae_output, policy_id, constraints)
                for policy_id in selected
            ]
            for future in concurrent.futures.as_completed(futures):
                payload = future.result()
                if not payload:
                    continue
                shadow_metrics = payload["metrics"]
                self.safety_monitor.update(payload["policy_id"], shadow_metrics)
                comparison = {
                    "doc_id": doc.doc_id,
                    "policy_id": payload["policy_id"],
                    "canonical_latency_ms": canonical_metrics["latency_ms"],
                    "shadow_latency_ms": shadow_metrics["latency_ms"],
                    "canonical_validation_failure": canonical_metrics["validation_failure"],
                    "shadow_validation_failure": shadow_metrics["validation_failure"],
                    "canonical_quality_proxy": canonical_metrics["quality_proxy"],
                    "shadow_quality_proxy": shadow_metrics["quality_proxy"],
                    "canonical_retrieval_proxy": canonical_metrics.get("retrieval_proxy", 0.0),
                    "shadow_retrieval_proxy": shadow_metrics.get("retrieval_proxy", 0.0),
                }
                comparisons.append(comparison)
                self.layout.append_comparison(comparison, filename=self.config.shadow.comparison_file)
                self.ctx.provenance.record(
                    agent="shadow_mode",
                    version="v1",
                    inputs={"doc_id": doc.doc_id, "policy_id": payload["policy_id"]},
                    outputs=comparison,
                    parameters={},
                    event_type="ShadowComparison",
                )
        return comparisons

    def _execute_shadow_plan(
        self,
        doc: Document,
        dae_output: DAEOutput,
        policy_id: str,
        constraints: SystemConstraints,
    ) -> Optional[Dict[str, object]]:
        policy = self.policy_store._policy_map.get(policy_id)
        if not policy:
            return None

        plan = build_plan(
            config=self.config,
            dae_output=dae_output,
            policy=policy,
            system_constraints=constraints,
            source="shadow",
            rationale="shadow_candidate",
        )
        shadow_dir = self.run_dir / "shadow" / policy_id
        shadow_dir.mkdir(parents=True, exist_ok=True)
        artifacts = ArtifactStore(str(shadow_dir / "artifacts"))
        from idpo.core.provenance import ProvenanceRecorder

        provenance = ProvenanceRecorder(str(shadow_dir / "provenance.jsonl"))
        shadow_ctx = AgentContext(
            config=self.config,
            artifact_store=artifacts,
            provenance=provenance,
            run_id=f"{self.run_id}_{policy_id}_shadow",
            budget_manager=BudgetManager(self.config.budget),
            calibrator=self.calibrator,
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
            "retrieval_proxy": metrics["retrieval_proxy"],
        }
        self.layout.write_shadow_doc(policy_id, doc.doc_id, payload)
        return {"policy_id": policy_id, "metrics": metrics}

    def _quality_metrics(self, state: ExecutionState, latency_ms: float) -> Dict[str, float]:
        if state.field_confidence:
            avg_conf = sum(state.field_confidence.values()) / max(len(state.field_confidence), 1)
        elif state.entities:
            avg_conf = sum(entity.confidence for entity in state.entities) / len(state.entities)
        else:
            avg_conf = 0.0
        retrieval_proxy = 0.0
        if state.chunks:
            avg_tokens = sum(chunk.tokens for chunk in state.chunks) / len(state.chunks)
            retrieval_proxy = min((len(state.chunks) / 10.0) + (avg_tokens / 1000.0), 1.0)
        return {
            "latency_ms": latency_ms,
            "validation_failure": 1.0 if state.validation_issues else 0.0,
            "quality_proxy": avg_conf,
            "retrieval_proxy": retrieval_proxy,
        }

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

    def _finalize_run_outputs(self) -> None:
        events_path = self.run_dir / "provenance.jsonl"
        graph_path = self.run_dir / "provenance_graph.json"
        provenance_paths = self.layout.write_provenance_bundle(events_path, graph_path)
        with self._metrics_lock:
            docs = list(self._doc_metrics)
        aggregate = {
            "run_id": self.run_id,
            "doc_count": len(docs),
            "avg_latency_ms": (sum(item["latency_ms"] for item in docs) / len(docs)) if docs else 0.0,
            "escalation_count": sum(1 for item in docs if item.get("escalated")),
            "validation_issue_total": sum(int(item.get("validation_issue_count", 0)) for item in docs),
            "docs": docs,
            "provenance": provenance_paths,
        }
        self.layout.write_metrics(aggregate, filename="metrics.json")
        report_lines = [
            "# IDPO Run Summary",
            "",
            f"- Run ID: `{self.run_id}`",
            f"- Documents processed: `{aggregate['doc_count']}`",
            f"- Average latency (ms): `{aggregate['avg_latency_ms']:.2f}`",
            f"- Escalations: `{aggregate['escalation_count']}`",
            f"- Validation issues: `{aggregate['validation_issue_total']}`",
            "",
            "## Per-Document",
        ]
        for row in docs:
            report_lines.append(
                f"- `{row['doc_id']}` policy={row['policy_id']} latency_ms={row['latency_ms']:.2f} "
                f"issues={row['validation_issue_count']} escalated={row['escalated']}"
            )
        (self.run_dir / "reports" / "summary.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    def build_index(self, results: List[PipelineResult], directory: Optional[str] = None) -> IndexBundle:
        chunks: Dict[str, Chunk] = {}
        chunk_artifact_ids: List[str] = []
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
                inputs={
                    "doc_ids": [result.doc_id for result in results],
                    "input_artifacts": chunk_artifact_ids,
                    "chunk_ids": list(chunks.keys()),
                },
                outputs={"output_artifacts": [embedding_artifact.artifact_id]},
                parameters={"embed_dim": embedder.dim, "seed": self.config.seed},
                artifacts=[embedding_artifact.artifact_id],
            )
        return bundle

    def export_structured_results(self, results: List[PipelineResult], output_path: str) -> Dict[str, object]:
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
        self, docs: List[Document], results: List[PipelineResult], output_dir: str
    ) -> Dict[str, object]:
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
