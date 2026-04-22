"""Canonical runtime orchestrator for IDPO document execution.

This module should coordinate the main document path:

- analysis
- planning
- execution
- result assembly

Cleanup work should move peripheral concerns out of this file over time,
especially reward logic, shadow execution, rollback handling, and feedback
logging.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import random
import threading
import time
import uuid
from collections import deque
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
    ExecutionPlan,
    StageSignal,
    SystemConstraints,
)
from idpo.retrieval.bm25 import BM25Index
from idpo.retrieval.index_bundle import IndexBundle
from idpo.retrieval.vector_store import HashingEmbedder, VectorStore
from idpo.pipeline.executor import PlanExecutor, ExecutionState
from idpo.pipeline.feedback import log_ahmn_feedback
from idpo.pipeline.planning import PlanRouter, build_plan
from idpo.pipeline.policy_safety import PolicyRollbackMonitor
from idpo.pipeline.export import export_simple_workspace as write_simple_workspace
from idpo.pipeline.export import export_structured_results as write_structured_export
from idpo.pipeline.results import PipelineResult, build_pipeline_result
from idpo.pipeline.reward import compute_reward, evaluate_policy_gates
from idpo.pipeline.shadow import (
    append_shadow_comparisons,
    build_shadow_comparison,
    compute_quality_metrics,
    dispatch_shadow_plans,
    should_run_shadow,
)
from idpo.core.storage import resolve_default_run_dir

logger = logging.getLogger("idpo.pipeline")

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
        if should_run_shadow(self.config, self._rng):
            shadow_executor, shadow_futures = dispatch_shadow_plans(
                config=self.config,
                policy_store=self.policy_store,
                rollback_monitor=self.rollback_monitor,
                base_run_dir=self.base_run_dir,
                run_id=self.run_id,
                doc=doc,
                dae_output=dae_output,
                constraints=constraints,
            )

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
        reward_type, reward_value, reward_details = compute_reward(doc, plan, state)
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

        primary_metrics = compute_quality_metrics(state, latency_ms)
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
                comparison = build_shadow_comparison(doc.doc_id, primary_metrics, shadow_result)
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
            append_shadow_comparisons(self.run_dir, self.config.shadow.comparison_file, shadow_comparisons)

        defer_status = "not_needed"
        defer_reason = None
        if state.escalated:
            defer_status = "requested"
            defer_reason = str(state.escalation_info.get("reason", "") or state.escalation_status or "validation_issues")
        elif state.escalation_status in {"budget_blocked", "quota_blocked", "model_unavailable"}:
            defer_status = "blocked"
            defer_reason = str(state.escalation_info.get("reason", "") or state.escalation_status)

        gate_result = evaluate_policy_gates(policy, reward_details, latency_ms)
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

        feedback_logged, feedback_error = log_ahmn_feedback(
            ctx=self.ctx,
            config=self.config,
            advice_id=advice_id,
            selected_policy_id=policy.policy_id,
            reward_value=reward_value,
            reward_details=reward_details,
            latency_ms=latency_ms,
            state=state,
            dae_output=dae_output,
            spent_budget_units=state.spent_budget_units,
        )

        return build_pipeline_result(
            doc=doc,
            dae_output=dae_output,
            state=state,
            category=category,
            bin_name=bin_name,
            reward_value=reward_value,
            reward_type=reward_type,
            reward_details=reward_details,
            policy=policy,
            static_policy=static_policy,
            plan=plan,
            plan_payload=plan_payload,
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
            model_used=model_used,
            model_mode=model_mode,
            model_reason=model_reason,
            queue_partition=queue_partition,
            queue_wait_ms=queue_wait_ms,
            artifact_ids=artifact_ids,
            latency_ms=latency_ms,
            feedback_logged=feedback_logged,
            feedback_error=feedback_error,
            shadow_comparisons=shadow_comparisons,
            static_policy_reason=static_policy_reason,
            analysis_signal=analysis_signal,
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
