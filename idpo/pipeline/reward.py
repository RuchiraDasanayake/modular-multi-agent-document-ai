"""Reward and policy-gate helpers for pipeline execution.

Reward design:
  - When the policy declares explicit fields (from the pack's requested fields),
    score against ONLY those fields. This ensures F1 reflects what was actually
    asked for, not generic canonical fields for the doc_type.
  - Canonical fields are used as a fallback ONLY when no explicit fields are
    declared (i.e. no pack ground truth). This prevents false negatives caused
    by doc_type misclassification inflating the denominator.
  - TP requires a populated field value (see _has_field_value). Grounding is
    captured separately in schema_details.grounding_coverage.
  - If neither explicit fields nor canonical fields are available, falls back to
    the proxy branch (validation + recovery + confidence).
"""

from __future__ import annotations

from typing import Optional

from idpo.core.config import PipelineConfig
from idpo.core.types import DAEOutput, Document, Entity, ExecutionPlan
from idpo.pipeline.executor import ExecutionState


def compute_reward(
    doc: Document,
    plan: ExecutionPlan,
    state: ExecutionState,
    dae_output: Optional[DAEOutput] = None,
    config: Optional[PipelineConfig] = None,
) -> tuple[str, float, dict[str, object]]:
    policy_fields = _policy_declared_fields(plan, state)
    # Policy-declared fields (from pack's requested fields) take full priority.
    # Only fall back to canonical when no fields were explicitly declared.
    if policy_fields:
        expected_fields = sorted(set(policy_fields))
    else:
        canonical_fields = _canonical_fields_for_doc(dae_output, config)
        expected_fields = sorted(set(canonical_fields))
    schema_details = _schema_quality_from_state(expected_fields, state)
    if expected_fields:
        extracted_expected = {
            key
            for key in expected_fields
            if _has_field_value(key, state.requested_field_status, state.entities)
        }
        # Only count entities whose value is concrete; placeholder/empty
        # extractions must not inflate the false-positive denominator.
        all_extracted_keys = {
            entity.key
            for entity in state.entities
            if _is_concrete_value(str(entity.value), entity.key)
        }
        tp = len(extracted_expected)
        fn = max(len(expected_fields) - tp, 0)
        fp = len([key for key in all_extracted_keys if key not in expected_fields])
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        reward_type = "policy_declared" if policy_fields else "canonical_fallback"
        details = {
            "doc_id": doc.doc_id,
            "expected_fields": expected_fields,
            "policy_fields": policy_fields,
            "extracted_field_count": len(all_extracted_keys),
            "true_positive_count": tp,
            "false_positive_count": fp,
            "false_negative_count": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            **schema_details,
        }
        return reward_type, round(f1, 4), details

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
        # Only count entities whose value passes the strict concrete-value
        # check — empty/placeholder/type-violating values are not real extractions.
        if not _is_concrete_value(str(entity.value), key):
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
    metadata = entity.metadata or {}
    if metadata.get("text_grounded") is True:
        return True
    bbox = metadata.get("bbox")
    return isinstance(bbox, list) and len(bbox) >= 4


def _policy_declared_fields(plan: ExecutionPlan, state: ExecutionState) -> list[str]:
    """Fields that the active policy explicitly declared it would extract."""
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


def _canonical_fields_for_doc(
    dae_output: Optional[DAEOutput],
    config: Optional[PipelineConfig],
) -> list[str]:
    """Canonical expected fields for the detected doc_type.

    Policy-independent: breaks the circularity where the reward measures
    whether the policy found the fields the same policy asked for.
    """
    if dae_output is None or config is None:
        return []
    registry = getattr(config.structuring, "canonical_fields_by_doc_type", None) or {}
    doc_type = str(getattr(dae_output, "doc_type", "") or "").strip().lower()
    if not doc_type:
        return []
    fields = registry.get(doc_type) or registry.get(doc_type.replace(" ", "_")) or []
    return [str(item).strip() for item in fields if str(item).strip()]


# Kept as a thin shim in case external callers import the old name.
def _expected_fields_for_reward(plan: ExecutionPlan, state: ExecutionState) -> list[str]:
    return _policy_declared_fields(plan, state)


def _has_field_value(
    key: str,
    requested_field_status: dict[str, dict[str, object]],
    entities: list[Entity],
) -> bool:
    status = requested_field_status.get(key) or {}
    value = str(status.get("value", "") or "").strip()
    if value:
        return _is_concrete_value(value, key)
    if "status" in status:
        return False
    return any(
        entity.key == key and _is_concrete_value(str(entity.value), key)
        for entity in entities
    )


# Placeholders that should never count as a real extraction.
_PLACEHOLDER_TOKENS = frozenset({
    "", "-", "--", "—", "?", "??", "???", "N/A", "NA", "NONE",
    "NULL", "NIL", "TBD", "TBA", "UNKNOWN", "UNSPECIFIED", "NOT SPECIFIED",
    "NOT APPLICABLE", "NOT AVAILABLE", "NOT FOUND", "MISSING", "EMPTY",
    "PENDING", "PLACEHOLDER", "XXX", "XXXX", "...", ".",
})

# Coarse field-type inference from field names for lightweight format validation.
_MONEY_KEYS = {"total_amount", "subtotal", "tax", "total_value", "amount", "price"}
_DATE_KEYS = {"date", "document_date", "effective_date", "due_date", "invoice_date"}
_ID_KEYS = {"invoice_number", "record_id", "reference", "receipt_number"}


def _is_concrete_value(value: str, key: str | None = None) -> bool:
    """Decide whether a raw extraction counts as a real field value.

    Rejects empty strings, placeholder tokens, and values that obviously
    violate the field's expected type. This keeps the F1 TP count honest:
    extracting "unknown" for total_amount must not be treated as success.
    """
    text = str(value or "").strip()
    if not text:
        return False
    normalized = text.upper()
    # Strip surrounding punctuation for placeholder check (e.g. "(N/A)" -> "N/A")
    stripped = normalized.strip("()[]{}\"'`,.:;")
    if stripped in _PLACEHOLDER_TOKENS:
        return False
    # Single-char tokens are never a legitimate extraction for a named field.
    if len(text) < 2:
        return False

    if key:
        normalized_key = str(key).strip().lower()
        if normalized_key in _MONEY_KEYS:
            # Require at least one digit for monetary amounts.
            if not any(ch.isdigit() for ch in text):
                return False
        elif normalized_key in _DATE_KEYS:
            # Require at least one digit for dates.
            if not any(ch.isdigit() for ch in text):
                return False
        elif normalized_key in _ID_KEYS:
            # IDs must contain at least one alphanumeric character.
            if not any(ch.isalnum() for ch in text):
                return False

    return True
