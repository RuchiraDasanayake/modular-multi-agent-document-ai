"""Shadow execution helpers for pipeline policy comparison.

This module keeps non-canonical shadow execution out of the main orchestrator
so the primary document path stays easier to follow.
"""

from __future__ import annotations

import concurrent.futures
import json
import random
import time
from pathlib import Path
from typing import Protocol

from idpo.agents.base import AgentContext
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import DAEOutput, Document, ExecutionPlan, SystemConstraints
from idpo.pipeline.executor import ExecutionState, PlanExecutor
from idpo.pipeline.planning import build_plan


class BlockedPolicyMonitor(Protocol):
    def is_blocked(self, policy_id: str) -> bool:
        ...


def should_run_shadow(config: PipelineConfig, rng: random.Random) -> bool:
    return config.shadow.enabled and config.shadow.sample_rate > 0 and rng.random() < config.shadow.sample_rate


def dispatch_shadow_plans(
    *,
    config: PipelineConfig,
    policy_store: PolicyStore,
    rollback_monitor: BlockedPolicyMonitor,
    base_run_dir: Path,
    run_id: str,
    doc: Document,
    dae_output: DAEOutput,
    constraints: SystemConstraints,
) -> tuple[concurrent.futures.ThreadPoolExecutor | None, list[concurrent.futures.Future]]:
    candidates = [pid for pid in config.shadow.candidate_policy_ids if pid in policy_store._policy_map]
    if not candidates:
        return None, []
    max_policies = max(1, config.shadow.max_policies_per_doc)
    selected = candidates[:max_policies]

    futures: list[concurrent.futures.Future] = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(selected))
    for policy_id in selected:
        if rollback_monitor.is_blocked(policy_id):
            continue
        policy = policy_store._policy_map[policy_id]
        plan = build_plan(
            config=config,
            dae_output=dae_output,
            policy=policy,
            system_constraints=constraints,
            source="shadow",
            rationale="shadow_candidate",
        )
        futures.append(
            executor.submit(
                execute_shadow_plan,
                config=config,
                base_run_dir=base_run_dir,
                run_id=run_id,
                doc=doc,
                dae_output=dae_output,
                policy_id=policy_id,
                plan=plan,
            )
        )
    if not futures:
        executor.shutdown(wait=False)
        return None, []
    return executor, futures


def execute_shadow_plan(
    *,
    config: PipelineConfig,
    base_run_dir: Path,
    run_id: str,
    doc: Document,
    dae_output: DAEOutput,
    policy_id: str,
    plan: ExecutionPlan,
) -> dict[str, object] | None:
    shadow_dir = base_run_dir / "shadow" / policy_id
    shadow_dir.mkdir(parents=True, exist_ok=True)
    artifacts = ArtifactStore(str(shadow_dir / "artifacts"))
    provenance = ProvenanceRecorder(str(shadow_dir / "provenance" / "events.jsonl"))
    shadow_ctx = AgentContext(
        config=config,
        artifact_store=artifacts,
        provenance=provenance,
        run_id=f"{run_id}_{policy_id}_shadow",
    )
    shadow_executor = PlanExecutor()
    shadow_doc = clone_document(doc)
    started = time.time()
    state = shadow_executor.execute(plan, shadow_doc, shadow_ctx)
    latency_ms = (time.time() - started) * 1000
    metrics = compute_quality_metrics(state, latency_ms)
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


def compute_quality_metrics(state: ExecutionState, latency_ms: float) -> dict[str, float]:
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


def build_shadow_comparison(
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


def append_shadow_comparisons(
    run_dir: Path,
    comparison_file: str,
    comparisons: list[dict[str, object]],
) -> None:
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    path = metrics_dir / comparison_file
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


def clone_document(doc: Document) -> Document:
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
