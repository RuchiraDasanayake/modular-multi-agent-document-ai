"""Reward and policy-gate helpers for pipeline execution.

This module keeps reward scoring and policy threshold evaluation out of the main
orchestrator so the document runtime path stays easier to follow and test.
"""

from __future__ import annotations

from idpo.core.types import Document, Entity, ExecutionPlan
from idpo.pipeline.executor import ExecutionState


def compute_reward(
    doc: Document,
    plan: ExecutionPlan,
    state: ExecutionState,
) -> tuple[str, float, dict[str, object]]:
    expected_fields = _expected_fields_for_reward(plan, state)
    schema_details = _schema_quality_from_state(expected_fields, state)
    if expected_fields:
        extracted_expected = {
            key
            for key in expected_fields
            if _has_field_value(key, state.requested_field_status, state.entities)
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
        min(
            validation_component
            + recovery_component
            + (confidence_component * 0.4)
            - unresolved_penalty
            - escalation_penalty,
            1.0,
        ),
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


def evaluate_policy_gates(
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


def _schema_quality_from_state(
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
            if _entity_is_grounded(entity):
                grounded_target_keys.add(key)

    for key in target_fields:
        if _has_field_value(key, state.requested_field_status, state.entities):
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


def _entity_is_grounded(entity: Entity) -> bool:
    if entity.page is not None or entity.span is not None:
        return True
    bbox = (entity.metadata or {}).get("bbox")
    return isinstance(bbox, list) and len(bbox) >= 4


def _expected_fields_for_reward(plan: ExecutionPlan, state: ExecutionState) -> list[str]:
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
    key: str,
    requested_field_status: dict[str, dict[str, object]],
    entities: list[Entity],
) -> bool:
    status = requested_field_status.get(key) or {}
    value = str(status.get("value", "") or "").strip()
    if value:
        return _is_concrete_value(value)
    if "status" in status:
        return False
    return any(entity.key == key and str(entity.value).strip() for entity in entities)


def _is_concrete_value(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.upper() not in {"N/A", "NA"}
