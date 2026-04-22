"""Pipeline result contract for canonical document execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from idpo.core.types import Chunk, DAEOutput, Document, Entity, Section, StageSignal, ValidationIssue

if TYPE_CHECKING:
    from idpo.pipeline.executor import ExecutionState


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


def build_pipeline_result(
    *,
    doc: Document,
    dae_output: DAEOutput,
    state: ExecutionState,
    category: str,
    bin_name: str,
    reward_value: float,
    reward_type: str,
    reward_details: dict[str, object],
    policy,
    static_policy,
    plan,
    plan_payload: dict[str, object],
    advice_status: str,
    advice_source: str,
    advice_id: str | None,
    advice_confidence: float,
    retrieval_source: str | None,
    rabi_used: bool,
    n_neighbors: int | None,
    advisor_recommendation: dict[str, object] | None,
    fallback_candidates: list[dict[str, object]],
    ranked_policies: list[dict[str, object]],
    route_specialization: str | None,
    fallback_reason: str | None,
    advice_accepted: bool,
    policy_changed: bool,
    blocked_policy: bool,
    rollback_triggered: bool,
    rollback_reason: str | None,
    defer_status: str,
    defer_reason: str | None,
    policy_blocked_count: int,
    model_used: str,
    model_mode: str,
    model_reason: str,
    queue_partition: str,
    queue_wait_ms: float,
    artifact_ids: dict[str, str],
    latency_ms: float,
    feedback_logged: bool,
    feedback_error: str | None,
    shadow_comparisons: list[dict[str, object]],
    static_policy_reason: str,
    analysis_signal: StageSignal | None,
) -> PipelineResult:
    return PipelineResult(
        doc_id=doc.doc_id,
        path=doc.path,
        source=doc.source,
        doc_type=dae_output.doc_type,
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
        analysis_confidence=getattr(
            dae_output,
            "analysis_confidence",
            analysis_signal.confidence if analysis_signal else dae_output.quality_score,
        ),
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
