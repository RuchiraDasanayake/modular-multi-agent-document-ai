from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from idpo.core.config import PipelineConfig
from idpo.core.policy_store import PolicyStore
from idpo.core.types import DAEOutput, ExecutionPlan, PlanStep, PolicyDefinition, SystemConstraints
from idpo.pipeline.policy_advisor import PolicyAdvice, PolicyAdvisor, PolicyRecommendation


@dataclass(frozen=True)
class RouteSelection:
    plan: ExecutionPlan
    policy: PolicyDefinition
    source: str
    advice: PolicyAdvice
    selected_recommendation: Optional[PolicyRecommendation]
    specialization: str
    operator_stack: Dict[str, Any]


class PlanRouter:
    def __init__(self, config: PipelineConfig, policy_store: PolicyStore) -> None:
        self.config = config
        self.policy_store = policy_store
        self.policy_advisor = PolicyAdvisor(config)

    def route(
        self,
        dae_output: DAEOutput,
        system_constraints: SystemConstraints,
        doc_metadata: Optional[Dict[str, Any]] = None,
        doc: Optional[object] = None,
        blocked_policy_ids: Optional[Set[str]] = None,
    ) -> RouteSelection:
        metadata = doc_metadata or {}
        blocked = blocked_policy_ids or set()
        advice = self.policy_advisor.advise(
            dae_output=dae_output,
            constraints=system_constraints,
            policy_store=self.policy_store,
            doc_metadata=metadata,
        )

        selected_rec: Optional[PolicyRecommendation] = None
        selected_policy = None
        source = advice.source
        for rec in advice.recommendations:
            if rec.policy_id in blocked:
                continue
            if rec.policy_id in self.policy_store._policy_map:
                selected_rec = rec
                selected_policy = self.policy_store._policy_map[rec.policy_id]
                break

        if selected_policy is None:
            selected_policy, _ = self.policy_store.select_policy(dae_output, doc)
            source = "fallback" if advice.fallback_used else advice.source
            selected_rec = None

        action_overrides = dict(self.config.ahmn.action_overrides)
        if selected_rec and selected_rec.action_overrides:
            action_overrides = _merge_dicts(action_overrides, selected_rec.action_overrides)

        specialization = _specialization_for_doc(dae_output, self.config)
        operator_stack = _operator_stack(dae_output, specialization)
        if action_overrides:
            operator_stack = _merge_dicts(operator_stack, action_overrides.get("operator_stack", {}))

        plan = build_plan(
            config=self.config,
            dae_output=dae_output,
            policy=selected_policy,
            system_constraints=system_constraints,
            action_overrides=action_overrides,
            source=source,
            rationale=(selected_rec.reason if selected_rec else "policy_store"),
            advice_bundle={
                "rag_hints": selected_rec.rag_hints if selected_rec else {},
                "field_templates": selected_rec.field_templates if selected_rec else {},
                "specialization": specialization,
                "operator_stack": operator_stack,
            },
        )
        return RouteSelection(
            plan=plan,
            policy=selected_policy,
            source=source,
            advice=advice,
            selected_recommendation=selected_rec,
            specialization=specialization,
            operator_stack=operator_stack,
        )


def build_plan(
    config: PipelineConfig,
    dae_output: DAEOutput,
    policy: PolicyDefinition,
    system_constraints: SystemConstraints,
    action_overrides: Optional[Dict[str, Any]] = None,
    source: str = "config",
    rationale: str = "",
    advice_bundle: Optional[Dict[str, Any]] = None,
) -> ExecutionPlan:
    actions = _merge_dicts(policy.actions, action_overrides or {})
    operators = actions.get("operators")
    specialization = (advice_bundle or {}).get("specialization", _specialization_for_doc(dae_output, config))
    operator_stack = (advice_bundle or {}).get("operator_stack", _operator_stack(dae_output, specialization))
    rag_hints = (advice_bundle or {}).get("rag_hints", {})
    field_templates = (advice_bundle or {}).get("field_templates", {})

    if operators:
        operator_specs = _normalize_operator_specs(operators)
    else:
        operator_specs = _default_operator_specs(dae_output, actions, specialization)

    budgets = actions.get("budgets", {})
    max_cost_units = float(budgets.get("max_cost_units", config.plan.max_total_budget_units))
    max_cost_units = min(max_cost_units, system_constraints.max_cost_units)
    budgets = {
        **budgets,
        "max_cost_units": max_cost_units,
        "route_bin": dae_output.route_bin,
        "specialization": specialization,
    }

    step_timeouts = actions.get("timeouts", {})
    step_budgets = actions.get("step_budgets", {})
    step_fallbacks = actions.get("fallbacks", {})

    steps: List[PlanStep] = []
    for idx, spec in enumerate(operator_specs):
        operator = spec["operator"]
        params = _params_for_operator(
            operator=operator,
            actions=actions,
            config=config,
            inline_params=spec.get("params"),
            dae_output=dae_output,
            specialization=specialization,
            operator_stack=operator_stack,
            rag_hints=rag_hints,
            field_templates=field_templates,
        )
        timeout_ms = int(spec.get("timeout_ms") or step_timeouts.get(operator) or config.plan.default_step_timeout_ms)
        budget_units = float(
            spec.get("budget_units") or step_budgets.get(operator) or config.plan.default_step_budget_units
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
    if rag_hints:
        retrieval = _merge_dicts(retrieval, {"rag_hints": rag_hints})

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


def _default_operator_specs(
    dae_output: DAEOutput,
    actions: Dict[str, Any],
    specialization: str,
) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    preprocess = actions.get("preprocess", {})

    if dae_output.doc_type == "scanned_document" or specialization == "image-dominant":
        if preprocess.get("ocr", {}).get("enabled", True):
            specs.append({"operator": "preprocess.ocr"})

    if preprocess.get("deskew", {}).get("enabled", True) and dae_output.route_bin in {"standard", "heavy"}:
        specs.append({"operator": "preprocess.deskew"})

    if preprocess.get("denoise", {}).get("enabled", True):
        if dae_output.route_bin in {"standard", "heavy"} or dae_output.quality_bin in {"B", "C"}:
            specs.append({"operator": "preprocess.denoise"})

    table_needed = (
        specialization in {"table-heavy", "form-centric"}
        or dae_output.content_profile in {"table-heavy", "form-centric"}
        or dae_output.signals.get("table_density_proxy", 0.0) > 0.15
    )
    if preprocess.get("table_extract", {}).get("enabled", True) and table_needed:
        specs.append({"operator": "preprocess.table_extract"})

    specs.extend(
        [
            {"operator": "structuring.extract"},
            {"operator": "structuring.section"},
            {"operator": "structuring.summary"},
            {"operator": "validation"},
            {"operator": "recovery"},
            {"operator": "escalation"},
            {"operator": "chunking"},
        ]
    )
    return specs


def _normalize_operator_specs(operators: List[Any]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for item in operators:
        if isinstance(item, str):
            specs.append({"operator": item})
        elif isinstance(item, dict) and "operator" in item:
            specs.append(item)
    return specs


def _params_for_operator(
    operator: str,
    actions: Dict[str, Any],
    config: PipelineConfig,
    inline_params: Optional[Dict[str, Any]],
    dae_output: DAEOutput,
    specialization: str,
    operator_stack: Dict[str, Any],
    rag_hints: Dict[str, Any],
    field_templates: Dict[str, Any],
) -> Dict[str, Any]:
    if inline_params:
        return inline_params
    if operator == "preprocess.ocr":
        params = actions.get("preprocess", {}).get("ocr", {})
        stack = operator_stack.get("ocr", {})
        return {
            "engine": params.get("engine", config.preprocessing.ocr_engine),
            "passes": params.get("passes", stack.get("passes", config.preprocessing.ocr_passes)),
            "lang": params.get("lang", config.preprocessing.ocr_lang),
            "psm": params.get("psm", stack.get("psm", config.preprocessing.ocr_psm)),
            "oem": params.get("oem", config.preprocessing.ocr_oem),
            "dpi": params.get("dpi", config.preprocessing.ocr_dpi),
            "alt_psm": params.get("alt_psm", config.preprocessing.ocr_alt_psm),
            "route_bin": dae_output.route_bin,
            "specialization": specialization,
        }
    if operator == "preprocess.deskew":
        params = actions.get("preprocess", {}).get("deskew", {})
        stack = operator_stack.get("deskew", {})
        return {"enabled": params.get("enabled", stack.get("enabled", True))}
    if operator == "preprocess.denoise":
        params = actions.get("preprocess", {}).get("denoise", {})
        stack = operator_stack.get("denoise", {})
        return {
            "enabled": params.get("enabled", stack.get("enabled", True)),
            "strength": params.get("strength", stack.get("strength", "standard")),
        }
    if operator == "preprocess.table_extract":
        params = actions.get("preprocess", {}).get("table_extract", {})
        stack = operator_stack.get("table_extract", {})
        return {
            "type": params.get("type", stack.get("type", config.preprocessing.table_mode)),
            "enabled": params.get("enabled", True),
        }
    if operator == "structuring.extract":
        params = actions.get("extraction", {})
        return {
            "model_tier": params.get("model_tier", config.llm.default_mode),
            "explicit_entities": params.get("explicit_entities", []),
            "field_descriptions": params.get("field_descriptions", {}),
            "field_templates": field_templates,
            "rag_hints": rag_hints,
            "ruleset": params.get("ruleset", "config"),
        }
    if operator == "validation":
        return {"min_confidence": config.validation.min_confidence}
    if operator == "recovery":
        params = actions.get("recovery", {})
        return {
            "strategy": params.get("strategy", "regex"),
            "rag_hints": rag_hints,
            "operator_stack": operator_stack,
        }
    if operator == "escalation":
        params = actions.get("escalation", {})
        return {
            "tier": params.get("tier", "tier2"),
            "target_model": params.get("target_model", config.escalation.flagship_model),
        }
    if operator == "chunking":
        params = actions.get("chunking", {})
        stack = operator_stack.get("chunking", {})
        return {
            "chunk_size": params.get("chunk_size", stack.get("chunk_size", config.chunking.chunk_size)),
            "chunk_overlap": params.get("chunk_overlap", stack.get("chunk_overlap", config.chunking.chunk_overlap)),
            "max_chunks": params.get("max_chunks", stack.get("max_chunks", config.chunking.max_chunks)),
            "mode": stack.get("mode", "standard"),
        }
    return {}


def _specialization_for_doc(dae_output: DAEOutput, config: PipelineConfig) -> str:
    struct = dae_output.structural_features or {}
    table_score = struct.get("table_density_proxy", dae_output.signals.get("table_density_proxy", 0.0))
    form_score = struct.get("form_pattern_proxy", dae_output.signals.get("form_pattern_proxy", 0.0))
    image_score = dae_output.signals.get("image_ratio", 0.0)
    if table_score >= config.routing.table_specialization_threshold:
        return "table-heavy"
    if form_score >= config.routing.form_specialization_threshold:
        return "form-centric"
    if image_score >= config.routing.image_specialization_threshold:
        return "image-dominant"
    return "text-dominant"


def _operator_stack(dae_output: DAEOutput, specialization: str) -> Dict[str, Any]:
    if dae_output.route_bin == "heavy":
        ocr_passes = 3
        denoise_strength = "aggressive"
        chunk_mode = "small_chunks"
    elif dae_output.route_bin == "light":
        ocr_passes = 1
        denoise_strength = "light"
        chunk_mode = "large_chunks"
    else:
        ocr_passes = 2
        denoise_strength = "standard"
        chunk_mode = "standard"

    stack = {
        "ocr": {"passes": ocr_passes, "psm": 6 if specialization != "table-heavy" else 4},
        "denoise": {"enabled": dae_output.route_bin != "light", "strength": denoise_strength},
        "deskew": {"enabled": dae_output.route_bin in {"standard", "heavy"}},
        "table_extract": {"type": "heuristic", "enabled": specialization in {"table-heavy", "form-centric"}},
        "chunking": {"mode": chunk_mode},
    }
    return stack


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    if not override:
        return dict(base)
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged
