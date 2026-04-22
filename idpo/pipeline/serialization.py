"""Serialization utilities for converting pipeline results to dictionaries."""

from __future__ import annotations

from typing import Any

from idpo.core.types import Chunk, Document, Entity, Page, Section, StageSignal, ValidationIssue
from idpo.pipeline.results import PipelineResult

def page_to_dict(page: Page) -> dict[str, Any]:
    return {
        "number": page.number,
        "text": page.text,
        "raw_text": page.raw_text,
        "image_path": page.image_path,
        "metadata": page.metadata,
    }

def document_to_dict(doc: Document) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "source": doc.source,
        "path": doc.path,
        "pages": [page_to_dict(page) for page in doc.pages],
        "metadata": doc.metadata,
        "profile": doc.profile,
        "quality_score": doc.quality_score,
        "complexity_score": doc.complexity_score,
        "doc_type": doc.doc_type,
        "vendor_cluster": doc.vendor_cluster,
        "quality_bin": doc.quality_bin,
        "complexity_bin": doc.complexity_bin,
        "content_profile": doc.content_profile,
        "dae_signals": doc.dae_signals,
    }

def entity_to_dict(entity: Entity) -> dict[str, Any]:
    return entity.__dict__

def extracted_field_to_dict(entity: Entity) -> dict[str, Any]:
    metadata = entity.metadata or {}
    bbox = metadata.get("bbox")
    if not isinstance(bbox, list):
        bbox = None
    return {
        "key": entity.key,
        "value": entity.value,
        "confidence": entity.confidence,
        "confidence_type": metadata.get("confidence_type", "heuristic"),
        "extraction_method": metadata.get("extraction_method", "unknown"),
        "page": entity.page,
        "span": list(entity.span) if entity.span else None,
        "bbox": bbox,
        "source": metadata.get("source"),
        "discovered": bool(metadata.get("discovered", False)),
        "metadata": metadata,
    }

def section_to_dict(section: Section) -> dict[str, Any]:
    return section.__dict__

def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return chunk.__dict__

def issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return issue.__dict__

def signal_to_dict(signal: StageSignal) -> dict[str, Any]:
    return signal.__dict__

def result_to_dict(result: PipelineResult) -> dict[str, Any]:
    def _attr(name: str, default: Any = None) -> Any:
        return getattr(result, name, default)

    return {
        "doc_id": result.doc_id,
        "path": result.path,
        "source": result.source,
        "doc_type": result.doc_type,
        "vendor_cluster": result.vendor_cluster,
        "layout_cluster_id": _attr("layout_cluster_id", "unknown"),
        "quality_bin": result.quality_bin,
        "complexity_bin": result.complexity_bin,
        "route_bin": _attr("route_bin", "standard"),
        "content_profile": result.content_profile,
        "profile": result.profile,
        "category": result.category,
        "bin": result.bin,
        "quality_score": result.quality_score,
        "complexity_score": result.complexity_score,
        "analysis_confidence": _attr("analysis_confidence", result.quality_score),
        "analysis_confidence_type": _attr("analysis_confidence_type", "heuristic"),
        "quality_features": _attr("quality_features", {}),
        "structural_features": _attr("structural_features", {}),
        "entities": [entity_to_dict(entity) for entity in result.entities],
        "extracted_fields": [extracted_field_to_dict(field) for field in _attr("extracted_fields", [])],
        "explicit_entities": [entity_to_dict(entity) for entity in result.explicit_entities],
        "default_entities": [entity_to_dict(entity) for entity in result.default_entities],
        "explicit_source": result.explicit_source,
        "sections": [section_to_dict(section) for section in result.sections],
        "chunks": [chunk_to_dict(chunk) for chunk in result.chunks],
        "summary": result.summary,
        "normalized_entities": result.normalized_entities,
        "validation_issues": [issue_to_dict(issue) for issue in result.validation_issues],
        "field_details": _attr("field_details", {}),
        "llm_diagnostics": _attr("llm_diagnostics", {}),
        "recovered_fields": result.recovered_fields,
        "failed_recovery_fields": _attr("failed_recovery_fields", []),
        "recovery_log": _attr("recovery_log", []),
        "escalated": result.escalated,
        "escalation_info": _attr("escalation_info", {"escalated": result.escalated}),
        "field_confidence": result.field_confidence,
        "stage_signals": [signal_to_dict(signal) for signal in result.stage_signals],
        "chunk_artifact_id": result.chunk_artifact_id,
        "preprocess_route": result.preprocess_route,
        "preprocess_artifacts": result.preprocess_artifacts,
        "policy_id": result.policy_id,
        "policy_name": result.policy_name,
        "policy_reason": result.policy_reason,
        "static_policy_id": _attr("static_policy_id", None),
        "static_policy_name": _attr("static_policy_name", None),
        "static_policy_reason": _attr("static_policy_reason", None),
        "advice_source": _attr("advice_source", result.plan_source),
        "advice_status": _attr("advice_status", "static"),
        "advice_id": _attr("advice_id", None),
        "advice_confidence": _attr("advice_confidence", 0.0),
        "retrieval_source": _attr("retrieval_source", None),
        "rabi_used": _attr("rabi_used", False),
        "n_neighbors": _attr("n_neighbors", None),
        "advisor_recommendation": _attr("advisor_recommendation", None),
        "fallback_candidates": _attr("fallback_candidates", []),
        "ranked_policies_legacy": _attr("ranked_policies", []),
        "route_specialization": _attr("route_specialization", None),
        "fallback_reason": _attr("fallback_reason", None),
        "advice_accepted": _attr("advice_accepted", False),
        "policy_changed": _attr("policy_changed", False),
        "blocked_policy": _attr("blocked_policy", False),
        "rollback_triggered": _attr("rollback_triggered", False),
        "rollback_reason": _attr("rollback_reason", None),
        "defer_status": _attr("defer_status", "not_needed"),
        "defer_reason": _attr("defer_reason", None),
        "policy_blocked_count": _attr("policy_blocked_count", 0),
        "operator_stack": _attr("operator_stack", []),
        "plan_id": result.plan_id,
        "plan_source": result.plan_source,
        "plan_budgets": result.plan_budgets,
        "plan_retrieval": result.plan_retrieval,
        "plan_token_budget": result.plan_token_budget,
        "plan_payload": result.plan_payload,
        "model_used": result.model_used,
        "model_mode": result.model_mode,
        "model_reason": result.model_reason,
        "dae_signals": result.dae_signals,
        "queue_partition": result.queue_partition,
        "queue_wait_ms": result.queue_wait_ms,
        "artifacts": result.artifacts,
        "latency_ms": result.latency_ms,
        "spent_budget_units": _attr("spent_budget_units", 0.0),
        "feedback_logged": _attr("feedback_logged", False),
        "feedback_error": _attr("feedback_error", None),
        "shadow_comparisons": _attr("shadow_comparisons", []),
    }
