"""Serialization utilities for converting pipeline results to dictionaries."""

from __future__ import annotations

from typing import Any

from idpo.core.types import Chunk, Document, Entity, Page, Section, StageSignal, ValidationIssue
from idpo.pipeline.orchestrator import PipelineResult

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

def section_to_dict(section: Section) -> dict[str, Any]:
    return section.__dict__

def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return chunk.__dict__

def issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return issue.__dict__

def signal_to_dict(signal: StageSignal) -> dict[str, Any]:
    return signal.__dict__

def result_to_dict(result: PipelineResult) -> dict[str, Any]:
    return {
        "doc_id": result.doc_id,
        "path": result.path,
        "source": result.source,
        "doc_type": result.doc_type,
        "vendor_cluster": result.vendor_cluster,
        "quality_bin": result.quality_bin,
        "complexity_bin": result.complexity_bin,
        "content_profile": result.content_profile,
        "profile": result.profile,
        "category": result.category,
        "bin": result.bin,
        "quality_score": result.quality_score,
        "complexity_score": result.complexity_score,
        "entities": [entity_to_dict(entity) for entity in result.entities],
        "explicit_entities": [entity_to_dict(entity) for entity in result.explicit_entities],
        "default_entities": [entity_to_dict(entity) for entity in result.default_entities],
        "explicit_source": result.explicit_source,
        "sections": [section_to_dict(section) for section in result.sections],
        "chunks": [chunk_to_dict(chunk) for chunk in result.chunks],
        "summary": result.summary,
        "normalized_entities": result.normalized_entities,
        "validation_issues": [issue_to_dict(issue) for issue in result.validation_issues],
        "recovered_fields": result.recovered_fields,
        "escalated": result.escalated,
        "field_confidence": result.field_confidence,
        "stage_signals": [signal_to_dict(signal) for signal in result.stage_signals],
        "chunk_artifact_id": result.chunk_artifact_id,
        "preprocess_route": result.preprocess_route,
        "preprocess_artifacts": result.preprocess_artifacts,
        "policy_id": result.policy_id,
        "policy_name": result.policy_name,
        "policy_reason": result.policy_reason,
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
    }
