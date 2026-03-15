"""Execution planning with AHMN integration and policy-driven step selection."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import DAEOutput, ExecutionPlan, PlanStep, PolicyDefinition, SystemConstraints

@dataclass(frozen=True)
class AHMNRecommendation:
    policy_id: str | None
    action_overrides: dict[str, Any]
    source: str = "ahmn"

class AHMNAdapter:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

    def recommend(
        self,
        dae_output: DAEOutput,
        objective: str,
        slo_state: dict[str, Any] | None = None,
    ) -> AHMNRecommendation | None:
        if not self.config.ahmn.enabled:
            return None
        if self.config.ahmn.mode != "mock":
            return None
        return AHMNRecommendation(
            policy_id=self.config.ahmn.policy_override_id,
            action_overrides=self.config.ahmn.action_overrides or {},
        )

class PlanRouter:
    def __init__(self, config: PipelineConfig, policy_store: PolicyStore) -> None:
        self.config = config
        self.policy_store = policy_store
        self.ahmn = AHMNAdapter(config)

    def route(
        self,
        dae_output: DAEOutput,
        system_constraints: SystemConstraints,
        doc_metadata: dict[str, Any] | None = None,
        doc: object | None = None,
        slo_state: dict[str, Any] | None = None,
    ) -> tuple[ExecutionPlan, PolicyDefinition, str]:
        policy, reason = self.policy_store.select_policy(dae_output, doc)
        source = "config"
        action_overrides: dict[str, Any] = {}

        recommendation = self.ahmn.recommend(dae_output, self.config.ahmn.objective, slo_state)
        if recommendation:
            if recommendation.policy_id and recommendation.policy_id in self.policy_store._policy_map:
                policy = self.policy_store._policy_map[recommendation.policy_id]
                source = "ahmn"
            if recommendation.action_overrides:
                action_overrides = recommendation.action_overrides
                source = "blended" if source == "config" else source

        plan = build_plan(
            config=self.config,
            dae_output=dae_output,
            policy=policy,
            system_constraints=system_constraints,
            action_overrides=action_overrides,
            source=source,
            rationale=reason,
        )
        return plan, policy, source

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
    is_image_pipeline = dae_output.doc_type == "scanned_document" or dae_output.content_profile == "image-heavy"

    # For scanned/image-heavy docs, image cleanup must happen before OCR.
    if is_image_pipeline and preprocess.get("deskew", {}).get("enabled", True) and (
        dae_output.quality_bin == "C" or abs(dae_output.signals.get("skew_angle", 0.0)) > 2.0
    ):
        specs.append({"operator": "preprocess.deskew"})
    if is_image_pipeline and preprocess.get("denoise", {}).get("enabled", True) and dae_output.quality_bin in {"B", "C"}:
        specs.append({"operator": "preprocess.denoise"})
    if is_image_pipeline and preprocess.get("ocr", {}).get("enabled", True):
        specs.append({"operator": "preprocess.ocr"})
    if preprocess.get("table_extract", {}).get("enabled", True) and (
        dae_output.content_profile in {"table-heavy", "form-centric"}
        or dae_output.signals.get("table_likelihood", 0.0) > 0.2
    ):
        specs.append({"operator": "preprocess.table_extract"})

    specs.append({"operator": "structuring.extract"})
    if not extraction_only:
        specs.extend(
            [
                {"operator": "structuring.section"},
                {"operator": "structuring.summary"},
            ]
        )
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
        return {
            "model_tier": params.get("model_tier", config.llm.default_mode),
            "explicit_entities": params.get("explicit_entities", []),
            "field_descriptions": params.get("field_descriptions", {}),
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
