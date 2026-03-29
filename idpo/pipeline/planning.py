"""Execution planning with config-gated static/adaptive policy routing."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import DAEOutput, ExecutionPlan, PlanStep, PolicyDefinition, SystemConstraints
from idpo.pipeline.policy_advisor import PolicyAdvice, PolicyAdvisor


@dataclass(frozen=True)
class RouteDecision:
    plan: ExecutionPlan
    policy: PolicyDefinition
    baseline_policy: PolicyDefinition
    baseline_policy_reason: str
    plan_source: str
    advice_source: str
    advice_status: str
    advisor_recommendation: dict[str, Any] | None
    fallback_candidates: list[dict[str, Any]]
    ranked_policies: list[dict[str, Any]]
    advice_id: str | None = None
    advice_confidence: float = 0.0
    retrieval_source: str | None = None
    rabi_used: bool = False
    n_neighbors: int | None = None
    fallback_reason: str | None = None
    route_specialization: str | None = None
    advice_accepted: bool = False
    policy_changed: bool = False


class PlanRouter:
    def __init__(self, config: PipelineConfig, policy_store: PolicyStore) -> None:
        self.config = config
        self.policy_store = policy_store
        self.advisor = PolicyAdvisor(config)

    def route(
        self,
        dae_output: DAEOutput,
        system_constraints: SystemConstraints,
        doc_metadata: dict[str, Any] | None = None,
        doc: object | None = None,
        blocked_policy_ids: set[str] | None = None,
    ) -> RouteDecision:
        metadata = doc_metadata or {}
        blocked = blocked_policy_ids or set()
        route_specialization = _route_specialization(dae_output)

        baseline_policy, baseline_reason = self.policy_store.select_policy(dae_output, doc)
        policy_mode = str(self.config.ahmn.policy_mode or "static").strip().lower()

        advice_source = "static"
        plan_source = "static"
        fallback_reason: str | None = None
        selected_policy = baseline_policy
        rationale = baseline_reason
        action_overrides: dict[str, Any] = {}
        advisor_recommendation: dict[str, Any] | None = None
        fallback_candidates: list[dict[str, Any]] = []
        ranked_payloads: list[dict[str, Any]] = []

        if policy_mode == "adaptive":
            advice = self.advisor.advise(dae_output, system_constraints, self.policy_store, metadata)
            advisor_recommendation = _advisor_payload(advice)
            fallback_candidates = _fallback_payloads(advice)
            ranked_payloads = _recommendation_payloads(advice.recommendations)
            advice_source = advice.source
            plan_source = advice.source
            selected_policy, action_overrides, rationale, fallback_reason = self._select_adaptive_policy(
                advice,
                baseline_policy,
                baseline_reason,
                blocked,
            )
            if selected_policy.policy_id in blocked and selected_policy.policy_id != self.config.knowledge.default_policy_id:
                selected_policy = self.policy_store._policy_map.get(self.config.knowledge.default_policy_id, selected_policy)
                action_overrides = {}
                fallback_reason = fallback_reason or "blocked_recommendation"
                rationale = fallback_reason
            if fallback_reason:
                plan_source = "fallback"
                rationale = fallback_reason
        else:
            ranked_payloads = [
                {
                    "policy_id": baseline_policy.policy_id,
                    "score": 1.0,
                    "reason": "static_baseline",
                    "source": "static",
                }
            ]
            if baseline_policy.policy_id in blocked and baseline_policy.policy_id != self.config.knowledge.default_policy_id:
                fallback = self.policy_store._policy_map.get(self.config.knowledge.default_policy_id, baseline_policy)
                selected_policy = fallback
                plan_source = "static_fallback"
                advice_source = "static"
                fallback_reason = "baseline_blocked"
                rationale = fallback_reason

        plan = build_plan(
            config=self.config,
            dae_output=dae_output,
            policy=selected_policy,
            system_constraints=system_constraints,
            action_overrides=action_overrides,
            source=plan_source,
            rationale=rationale,
        )
        return RouteDecision(
            plan=plan,
            policy=selected_policy,
            baseline_policy=baseline_policy,
            baseline_policy_reason=baseline_reason,
            plan_source=plan_source,
            advice_source=advice_source,
            advice_status=_advice_status(
                policy_mode=policy_mode,
                advisor_recommendation=advisor_recommendation,
                selected_policy_id=selected_policy.policy_id,
                fallback_reason=fallback_reason,
            ),
            advisor_recommendation=advisor_recommendation,
            fallback_candidates=fallback_candidates,
            ranked_policies=ranked_payloads,
            advice_id=advice.advice_id if policy_mode == "adaptive" else None,
            advice_confidence=advice.confidence if policy_mode == "adaptive" else 0.0,
            retrieval_source=advice.retrieval_source if policy_mode == "adaptive" else None,
            rabi_used=advice.rabi_used if policy_mode == "adaptive" else False,
            n_neighbors=advice.n_neighbors if policy_mode == "adaptive" else None,
            fallback_reason=fallback_reason,
            route_specialization=route_specialization,
            advice_accepted=policy_mode == "adaptive" and fallback_reason is None and selected_policy.policy_id == (advisor_recommendation or {}).get("policy_id"),
            policy_changed=selected_policy.policy_id != baseline_policy.policy_id,
        )

    def _select_adaptive_policy(
        self,
        advice: PolicyAdvice,
        baseline_policy: PolicyDefinition,
        baseline_reason: str,
        blocked_policy_ids: set[str],
    ) -> tuple[PolicyDefinition, dict[str, Any], str, str | None]:
        fallback_reason: str | None = None
        for recommendation in advice.recommendations:
            policy = self.policy_store._policy_map.get(recommendation.policy_id)
            if not policy:
                fallback_reason = "invalid_recommendation"
                continue
            if recommendation.policy_id in blocked_policy_ids:
                fallback_reason = "blocked_recommendation"
                continue
            return policy, recommendation.action_overrides, recommendation.reason, None
        if advice.recommendations:
            if fallback_reason is None:
                fallback_reason = "no_allowed_recommendation"
        elif advice.fallback_used:
            fallback_reason = str((advice.raw or {}).get("reason") or "ahmn_fallback")
        else:
            fallback_reason = "empty_recommendation_set"
        return baseline_policy, {}, baseline_reason, fallback_reason


def build_plan(
    config: PipelineConfig,
    dae_output: DAEOutput,
    policy: PolicyDefinition,
    system_constraints: SystemConstraints,
    action_overrides: dict[str, Any] | None = None,
    source: str = "config",
    rationale: str = "",
) -> ExecutionPlan:
    actions = _merge_dicts(policy.actions, action_overrides or {})
    operators = actions.get("operators")
    if operators:
        operator_specs = _normalize_operator_specs(operators)
    else:
        operator_specs = _default_operator_specs(dae_output, actions)

    budgets = actions.get("budgets", {})
    max_cost_units = float(budgets.get("max_cost_units", config.plan.max_total_budget_units))
    max_cost_units = min(max_cost_units, system_constraints.max_cost_units)
    budgets = {**budgets, "max_cost_units": max_cost_units}

    step_timeouts = actions.get("timeouts", {})
    step_budgets = actions.get("step_budgets", {})
    step_fallbacks = actions.get("fallbacks", {})

    steps: list[PlanStep] = []
    for idx, spec in enumerate(operator_specs):
        operator = spec["operator"]
        params = _params_for_operator(operator, actions, config, spec.get("params"))
        timeout_ms = int(
            spec.get("timeout_ms")
            or step_timeouts.get(operator)
            or config.plan.default_step_timeout_ms
        )
        budget_units = float(
            spec.get("budget_units")
            or step_budgets.get(operator)
            or config.plan.default_step_budget_units
        )
        fallback = spec.get("fallback") or step_fallbacks.get(operator) or []
        steps.append(
            PlanStep(
                step_id=f"{idx}_{operator}",
                operator=operator,
                params=params,
                timeout_ms=timeout_ms,
                budget_units=budget_units,
                fallback=list(fallback) if isinstance(fallback, list) else [str(fallback)],
            )
        )

    retrieval = actions.get("retrieval", {})
    if not retrieval:
        retrieval = {
            "dense_k": config.retrieval.dense_k,
            "sparse_k": config.retrieval.sparse_k,
            "final_k": config.retrieval.final_k,
            "mmr_lambda": config.retrieval.mmr_lambda,
            "metadata_boost": config.retrieval.metadata_boost,
        }

    token_budget = actions.get("token_budget", {})
    if not token_budget:
        token_budget = {
            "max_tokens": config.context.max_tokens,
            "reserved_tokens": config.context.reserved_tokens,
            "strategy": "simple",
        }

    return ExecutionPlan(
        plan_id=uuid.uuid4().hex,
        doc_id=dae_output.doc_id,
        policy_id=policy.policy_id,
        policy_name=policy.name,
        source=source,
        steps=steps,
        budgets=budgets,
        retrieval=retrieval,
        token_budget=token_budget,
        rationale=rationale,
        created_at=time.time(),
    )


def _default_operator_specs(dae_output: DAEOutput, actions: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    preprocess = actions.get("preprocess", {})
    execution_mode = str(actions.get("execution_mode", "")).strip().lower()
    extraction_only = execution_mode in {"extract", "extraction_only", "fields_only"}
    structural = dae_output.structural_features or {}
    quality = dae_output.quality_features or {}
    table_ratio = float(structural.get("table_ratio", dae_output.signals.get("table_likelihood", 0.0)))
    form_ratio = float(structural.get("form_ratio", 0.0))
    image_ratio = float(quality.get("image_ratio", dae_output.signals.get("image_ratio", 0.0)))
    skew_angle = abs(float(quality.get("skew_angle", dae_output.signals.get("skew_angle", 0.0))))
    is_image_pipeline = (
        dae_output.doc_type == "scanned_document"
        or dae_output.content_profile == "image-heavy"
        or (dae_output.route_bin == "heavy" and image_ratio >= 0.35)
    )

    if is_image_pipeline and preprocess.get("deskew", {}).get("enabled", True) and (
        dae_output.quality_bin == "C" or skew_angle > 2.0
    ):
        specs.append({"operator": "preprocess.deskew"})
    if is_image_pipeline and preprocess.get("denoise", {}).get("enabled", True) and (
        dae_output.route_bin == "heavy" or dae_output.quality_bin in {"B", "C"}
    ):
        specs.append({"operator": "preprocess.denoise"})
    if is_image_pipeline and preprocess.get("ocr", {}).get("enabled", True):
        specs.append({"operator": "preprocess.ocr"})
    if preprocess.get("table_extract", {}).get("enabled", True) and (
        dae_output.content_profile in {"table-heavy", "form-centric"}
        or dae_output.layout_cluster_id in {"table_dense", "form_dense"}
        or table_ratio >= 0.15
        or form_ratio >= 0.2
    ):
        specs.append({"operator": "preprocess.table_extract"})

    specs.append({"operator": "structuring.extract"})
    if not extraction_only:
        specs.append({"operator": "structuring.section"})
        if dae_output.route_bin != "light":
            specs.append({"operator": "structuring.summary"})
    specs.extend(
        [
            {"operator": "validation"},
            {"operator": "recovery"},
            {"operator": "escalation"},
        ]
    )
    if not extraction_only:
        specs.append({"operator": "chunking"})
    return specs


def _normalize_operator_specs(operators: list[Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for item in operators:
        if isinstance(item, str):
            specs.append({"operator": item})
        elif isinstance(item, dict) and "operator" in item:
            specs.append(item)
    return specs


def _params_for_operator(
    operator: str,
    actions: dict[str, Any],
    config: PipelineConfig,
    inline_params: dict[str, Any] | None,
) -> dict[str, Any]:
    if inline_params:
        return inline_params
    if operator == "preprocess.ocr":
        params = actions.get("preprocess", {}).get("ocr", {})
        return {
            "engine": params.get("engine", config.preprocessing.ocr_engine),
            "passes": params.get("passes", config.preprocessing.ocr_passes),
            "lang": params.get("lang", config.preprocessing.ocr_lang),
            "psm": params.get("psm", config.preprocessing.ocr_psm),
            "oem": params.get("oem", config.preprocessing.ocr_oem),
            "dpi": params.get("dpi", config.preprocessing.ocr_dpi),
            "alt_psm": params.get("alt_psm", config.preprocessing.ocr_alt_psm),
        }
    if operator == "preprocess.deskew":
        params = actions.get("preprocess", {}).get("deskew", {})
        return {"enabled": params.get("enabled", True)}
    if operator == "preprocess.denoise":
        params = actions.get("preprocess", {}).get("denoise", {})
        return {"enabled": params.get("enabled", True), "strength": params.get("strength", "standard")}
    if operator == "preprocess.table_extract":
        params = actions.get("preprocess", {}).get("table_extract", {})
        return {"type": params.get("type", config.preprocessing.table_mode)}
    if operator == "structuring.extract":
        params = actions.get("extraction", {})
        explicit_entities = params.get("explicit_entities", [])
        if config.structuring.requested_fields:
            explicit_entities = list(config.structuring.requested_fields)
        field_descriptions = params.get("field_descriptions", {})
        if config.structuring.field_descriptions:
            merged_descriptions = {}
            if isinstance(field_descriptions, dict):
                merged_descriptions.update(field_descriptions)
            merged_descriptions.update(config.structuring.field_descriptions)
            field_descriptions = merged_descriptions
        return {
            "model_tier": params.get("model_tier", config.llm.default_mode),
            "explicit_entities": explicit_entities,
            "field_descriptions": field_descriptions,
            "ruleset": params.get("ruleset", "config"),
        }
    if operator == "structuring.section":
        return {}
    if operator == "structuring.summary":
        return {}
    if operator == "validation":
        return {"min_confidence": config.validation.min_confidence}
    if operator == "recovery":
        params = actions.get("recovery", {})
        return {"strategy": params.get("strategy", "regex")}
    if operator == "escalation":
        params = actions.get("escalation", {})
        return {"tier": params.get("tier", "tier2")}
    if operator == "chunking":
        params = actions.get("chunking", {})
        return {
            "chunk_size": params.get("chunk_size", config.chunking.chunk_size),
            "chunk_overlap": params.get("chunk_overlap", config.chunking.chunk_overlap),
            "max_chunks": params.get("max_chunks", config.chunking.max_chunks),
        }
    return {}


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    if not override:
        return dict(base)
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _recommendation_payload(item) -> dict[str, Any]:
    return {
        "policy_id": item.policy_id,
        "score": round(float(item.score), 4),
        "reason": item.reason,
        "source": item.source,
        "action_overrides": item.action_overrides,
        "rag_hints": item.rag_hints,
        "field_templates": item.field_templates,
    }


def _recommendation_payloads(items: list[Any]) -> list[dict[str, Any]]:
    return [
        _recommendation_payload(item)
        for item in items
    ]


def _advisor_payload(advice: PolicyAdvice) -> dict[str, Any] | None:
    if advice.source == "fallback":
        return None
    for item in advice.recommendations:
        if item.source != "fallback":
            return _recommendation_payload(item)
    return None


def _fallback_payloads(advice: PolicyAdvice) -> list[dict[str, Any]]:
    return _recommendation_payloads(advice.fallback_recommendations)


def _route_specialization(dae_output: DAEOutput) -> str:
    table_ratio = float((dae_output.structural_features or {}).get("table_ratio", 0.0))
    form_ratio = float((dae_output.structural_features or {}).get("form_ratio", 0.0))
    image_ratio = float((dae_output.quality_features or {}).get("image_ratio", dae_output.signals.get("image_ratio", 0.0)))
    if dae_output.layout_cluster_id == "table_dense" or table_ratio >= 0.2:
        return "table"
    if dae_output.layout_cluster_id == "form_dense" or form_ratio >= 0.2:
        return "form"
    if dae_output.layout_cluster_id == "image_sparse" or image_ratio >= 0.5:
        return "image"
    return "text"


def _advice_status(
    *,
    policy_mode: str,
    advisor_recommendation: dict[str, Any] | None,
    selected_policy_id: str,
    fallback_reason: str | None,
) -> str:
    if policy_mode != "adaptive":
        return "static"
    if advisor_recommendation is None:
        return "no_advice"
    if fallback_reason:
        return "rejected"
    if selected_policy_id == str(advisor_recommendation.get("policy_id") or ""):
        return "accepted"
    return "rejected"
