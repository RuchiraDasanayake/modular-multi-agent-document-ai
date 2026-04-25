"""Per-document artifact writers for inbox processing.

This module owns the document-local file layout under ``runs/<run_id>/docs/<doc_id>``.
It keeps file persistence details out of ``inbox.py`` so the inbox path can stay
focused on orchestration instead of path and JSON boilerplate.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from idpo.pipeline.serialization import (
    chunk_to_dict,
    extracted_field_to_dict,
    issue_to_dict,
    section_to_dict,
    signal_to_dict,
)


def prepare_doc_input(doc, file_path: Path, doc_dir: Path) -> None:
    _ensure_doc_dirs(doc_dir)
    original_path = _copy_original_input(file_path, doc_dir)
    _write_doc_manifest(doc, file_path, doc_dir, original_path)
    _write_hashes(original_path, doc_dir)


def build_run_provenance_index(run_dir: Path) -> dict[str, list[dict[str, object]]]:
    """Index run-level provenance events by doc_id once for O(1) per-doc lookup.

    Without this, _materialize_doc_provenance_from_run scans the full events.jsonl
    for every document — O(N*M) for N docs and M total events.
    """
    source_events = run_dir / "provenance" / "events.jsonl"
    index: dict[str, list[dict[str, object]]] = {}
    if not source_events.exists():
        return index
    with source_events.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except Exception:
                continue
            doc_id = str((payload.get("inputs") or {}).get("doc_id") or "").strip()
            if doc_id:
                index.setdefault(doc_id, []).append(payload)
    return index


def write_doc_outputs(
    run_dir: Path,
    doc,
    result,
    doc_dir: Path,
    events_path: Path,
    *,
    run_provenance_index: dict[str, list[dict[str, object]]] | None = None,
) -> None:
    _ensure_doc_dirs(doc_dir)
    _write_dae_output(result, doc_dir)
    _write_plan_output(result, doc_dir)
    _write_structuring(result, doc_dir)
    _write_validation(result, doc_dir)
    _write_recovery(result, doc_dir)
    _write_reward(result, doc_dir)
    _write_decision_chain(result, doc_dir)
    _write_chunking(result, doc_dir)
    _write_ocr_output(doc, result, doc_dir)
    _materialize_doc_provenance_from_run(run_dir, result.doc_id, doc_dir, run_provenance_index)
    _write_transparency(result, doc_dir)
    _append_events(events_path, result, doc_dir)


def fallback_path(llm_diag: dict[str, object]) -> str:
    local_attempted = bool(llm_diag.get("local_attempted"))
    cloud_attempted = bool(llm_diag.get("cloud_attempted"))
    flagship_attempted = bool(llm_diag.get("flagship_attempted"))
    cloud_succeeded = bool(llm_diag.get("cloud_succeeded"))
    local_succeeded = bool(llm_diag.get("local_succeeded"))
    requested_mode = str(llm_diag.get("requested_mode", "") or "").strip().lower()
    if flagship_attempted:
        return "local_or_cloud->flagship" if (local_attempted or cloud_attempted) else "flagship_only"
    if local_attempted and cloud_attempted:
        if requested_mode == "cloud" and local_succeeded and not cloud_succeeded:
            return "cloud->local"
        return "local->cloud"
    if cloud_attempted and cloud_succeeded:
        return "cloud"
    if local_attempted and local_succeeded:
        return "local"
    return "none"


def _ensure_doc_dirs(doc_dir: Path) -> None:
    required_dirs = [
        doc_dir / "input",
        doc_dir / "dae",
        doc_dir / "plan",
        doc_dir / "preprocessing" / "ocr",
        doc_dir / "structuring",
        doc_dir / "validation",
        doc_dir / "recovery",
        doc_dir / "chunking",
        doc_dir / "embeddings" / "index",
        doc_dir / "provenance",
        doc_dir / "provenance" / "artifacts",
    ]
    for path in required_dirs:
        path.mkdir(parents=True, exist_ok=True)


def _copy_original_input(file_path: Path, doc_dir: Path) -> Path:
    target = doc_dir / "input" / f"original{file_path.suffix.lower()}"
    shutil.copy2(file_path, target)
    return target


def _write_doc_manifest(doc, file_path: Path, doc_dir: Path, original_path: Path) -> None:
    payload = {
        "doc_id": str(doc.doc_id),
        "path": str(file_path),
        "copied_input_path": str(original_path),
        "source": str(getattr(doc, "source", "") or ""),
        "page_count": len(getattr(doc, "pages", []) or []),
        "metadata": getattr(doc, "metadata", {}) or {},
    }
    _write_json(doc_dir / "input" / "manifest.json", payload)


def _write_hashes(original_path: Path, doc_dir: Path) -> None:
    content = original_path.read_bytes()
    payload = {
        "path": str(original_path),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "md5": hashlib.md5(content).hexdigest(),
        "mime_type": mimetypes.guess_type(original_path.name)[0] or "application/octet-stream",
    }
    _write_json(doc_dir / "input" / "hashes.json", payload)


def _write_dae_output(result, doc_dir: Path) -> None:
    payload = {
        "doc_id": result.doc_id,
        "doc_type": result.doc_type,
        "vendor_cluster": result.vendor_cluster,
        "layout_cluster_id": getattr(result, "layout_cluster_id", "unknown"),
        "route_bin": getattr(result, "route_bin", "standard"),
        "quality_bin": result.quality_bin,
        "complexity_bin": result.complexity_bin,
        "content_profile": result.content_profile,
        "quality_score": result.quality_score,
        "complexity_score": result.complexity_score,
        "analysis_confidence": float(getattr(result, "analysis_confidence", 0.0) or 0.0),
        "confidence_type": getattr(result, "analysis_confidence_type", "heuristic"),
        "quality_features": getattr(result, "quality_features", {}) or {},
        "structural_features": getattr(result, "structural_features", {}) or {},
        "signals": getattr(result, "dae_signals", {}) or {},
    }
    _write_json(doc_dir / "dae" / "output.json", payload)


def _write_plan_output(result, doc_dir: Path) -> None:
    payload = getattr(result, "plan_payload", {}) or {}
    if not payload:
        payload = {
            "plan_id": result.plan_id,
            "policy_id": result.policy_id,
            "policy_name": result.policy_name,
            "source": result.plan_source,
            "budgets": getattr(result, "plan_budgets", {}) or {},
            "retrieval": getattr(result, "plan_retrieval", {}) or {},
            "token_budget": getattr(result, "plan_token_budget", {}) or {},
        }
    _write_json(doc_dir / "plan" / "primary.json", payload)


def _write_structuring(result, doc_dir: Path) -> None:
    extracted_fields = getattr(result, "extracted_fields", None) or result.entities
    extracted_payload = {
        "doc_id": result.doc_id,
        "entities": [extracted_field_to_dict(entity) for entity in extracted_fields],
        "requested_field_status": getattr(result, "field_details", {}) or {},
        "llm_diagnostics": getattr(result, "llm_diagnostics", {}) or {},
        "recovered_fields": getattr(result, "recovered_fields", {}) or {},
    }
    _write_json(doc_dir / "structuring" / "extracted.json", extracted_payload)
    _write_json(
        doc_dir / "structuring" / "sections.json",
        {"sections": [section_to_dict(section) for section in (result.sections or [])]},
    )
    _write_json(
        doc_dir / "structuring" / "summaries.json",
        {"doc_id": result.doc_id, "summary": result.summary},
    )


def _write_validation(result, doc_dir: Path) -> None:
    issues = [issue_to_dict(issue) for issue in (result.validation_issues or [])]
    _write_json(
        doc_dir / "validation" / "results.json",
        {
            "doc_id": result.doc_id,
            "issues": issues,
            "issue_count": len(issues),
        },
    )
    _write_json(
        doc_dir / "validation" / "normalized.json",
        {
            "doc_id": result.doc_id,
            "normalized": result.normalized_entities or {},
            "confidence": result.field_confidence or {},
        },
    )


def _write_recovery(result, doc_dir: Path) -> None:
    recovery_log = getattr(result, "recovery_log", []) or []
    _write_jsonl(doc_dir / "recovery" / "attempts.jsonl", recovery_log)
    escalation_info = getattr(result, "escalation_info", {}) or {}
    escalation_rows = [escalation_info] if escalation_info else []
    _write_jsonl(doc_dir / "recovery" / "escalations.jsonl", escalation_rows)
    _write_json(
        doc_dir / "recovery_trace.json",
        {
            "doc_id": result.doc_id,
            "recovered_fields": result.recovered_fields or {},
            "failed_recovery_fields": getattr(result, "failed_recovery_fields", []) or [],
            "recovery_log": recovery_log,
            "escalation_status": getattr(result, "escalation_status", "not_needed"),
            "escalation_info": escalation_info,
            "escalated": bool(getattr(result, "escalated", False)),
        },
    )


def _write_reward(result, doc_dir: Path) -> None:
    _write_json(
        doc_dir / "reward.json",
        {
            "doc_id": result.doc_id,
            "reward": float(getattr(result, "reward", 0.0) or 0.0),
            "reward_type": getattr(result, "reward_type", "proxy"),
            "reward_details": getattr(result, "reward_details", {}) or {},
            "spent_budget_units": float(getattr(result, "spent_budget_units", 0.0) or 0.0),
            "feedback_logged": bool(getattr(result, "feedback_logged", False)),
            "feedback_error": getattr(result, "feedback_error", None),
        },
    )


def _write_decision_chain(result, doc_dir: Path) -> None:
    llm_diag = getattr(result, "llm_diagnostics", {}) or {}
    payload = {
        "doc_id": result.doc_id,
        "policy": {
            "policy_id": result.policy_id,
            "policy_name": result.policy_name,
            "plan_id": result.plan_id,
            "plan_source": result.plan_source,
            "static_policy_id": getattr(result, "static_policy_id", None),
            "static_policy_name": getattr(result, "static_policy_name", None),
            "static_policy_reason": getattr(result, "static_policy_reason", None),
            "advice_source": getattr(result, "advice_source", ""),
            "advice_status": getattr(result, "advice_status", "static"),
            "advice_id": getattr(result, "advice_id", None),
            "advice_confidence": float(getattr(result, "advice_confidence", 0.0) or 0.0),
            "retrieval_source": getattr(result, "retrieval_source", None),
            "rabi_used": bool(getattr(result, "rabi_used", False)),
            "n_neighbors": getattr(result, "n_neighbors", None),
            "advisor_recommendation": getattr(result, "advisor_recommendation", None),
            "fallback_candidates": getattr(result, "fallback_candidates", []) or [],
            "fallback_reason": getattr(result, "fallback_reason", None),
            "advice_accepted": bool(getattr(result, "advice_accepted", False)),
            "policy_changed": bool(getattr(result, "policy_changed", False)),
            "route_specialization": getattr(result, "route_specialization", None),
            "operator_stack": getattr(result, "operator_stack", []) or [],
            "blocked_policy": bool(getattr(result, "blocked_policy", False)),
            "rollback_triggered": bool(getattr(result, "rollback_triggered", False)),
            "rollback_reason": getattr(result, "rollback_reason", None),
            "defer_status": getattr(result, "defer_status", "not_needed"),
            "defer_reason": getattr(result, "defer_reason", None),
        },
        "model": {
            "model_used": result.model_used,
            "model_mode": result.model_mode,
            "model_reason": result.model_reason,
            "fallback_path": fallback_path(llm_diag),
        },
        "reward": {
            "reward": float(getattr(result, "reward", 0.0) or 0.0),
            "reward_type": getattr(result, "reward_type", "proxy"),
            "reward_details": getattr(result, "reward_details", {}) or {},
            "spent_budget_units": float(getattr(result, "spent_budget_units", 0.0) or 0.0),
            "feedback_logged": bool(getattr(result, "feedback_logged", False)),
            "feedback_error": getattr(result, "feedback_error", None),
        },
        "feedback_status": {
            "logged": bool(getattr(result, "feedback_logged", False)),
            "error": getattr(result, "feedback_error", None),
            "advice_id": getattr(result, "advice_id", None),
        },
        "safety_status": {
            "blocked_policy": bool(getattr(result, "blocked_policy", False)),
            "rollback_triggered": bool(getattr(result, "rollback_triggered", False)),
            "rollback_reason": getattr(result, "rollback_reason", None),
            "policy_blocked_count": int(getattr(result, "policy_blocked_count", 0) or 0),
            "defer_status": getattr(result, "defer_status", "not_needed"),
            "defer_reason": getattr(result, "defer_reason", None),
        },
    }
    _write_json(doc_dir / "decision_chain.json", payload)


def _write_chunking(result, doc_dir: Path) -> None:
    _write_jsonl(doc_dir / "chunking" / "chunks.jsonl", [chunk_to_dict(chunk) for chunk in (result.chunks or [])])


def _write_ocr_output(doc, result, doc_dir: Path) -> None:
    ocr_signal = None
    for signal in getattr(result, "stage_signals", []) or []:
        if getattr(signal, "stage", "") == "ocr":
            ocr_signal = signal
            break
    ocr_meta = getattr(ocr_signal, "metadata", {}) or {}
    pages = []
    for page in getattr(doc, "pages", []) or []:
        pages.append(
            {
                "number": page.number,
                "text": page.text,
                "raw_text": page.raw_text,
                "image_path": page.image_path,
                "metadata": page.metadata,
            }
        )
    _write_json(
        doc_dir / "preprocessing" / "ocr" / "text.json",
        {
            "doc_id": result.doc_id,
            "confidence": float(ocr_meta.get("avg_ocr_confidence", 0.0) or 0.0),
            "engine": str(ocr_meta.get("engine", "")),
            "rerun_attempted_pages": int(ocr_meta.get("rerun_attempted_pages", 0) or 0),
            "rerun_used_pages": int(ocr_meta.get("rerun_used_pages", 0) or 0),
            "pages": pages,
        },
    )


def _write_transparency(result, doc_dir: Path) -> None:
    llm_diag = getattr(result, "llm_diagnostics", {}) or {}
    requested_field_status = getattr(result, "field_details", {}) or {}
    unresolved_count = sum(
        1
        for item in requested_field_status.values()
        if str((item or {}).get("status", "")).strip() != "extracted"
    )
    schema_quality = _schema_quality_summary(result, requested_field_status)
    ocr_signal = None
    for signal in getattr(result, "stage_signals", []) or []:
        if getattr(signal, "stage", "") == "ocr":
            ocr_signal = signal
            break
    ocr_meta = getattr(ocr_signal, "metadata", {}) or {}
    payload = {
        "doc_id": result.doc_id,
        "latency_ms": float(getattr(result, "latency_ms", 0.0) or 0.0),
        "ocr_route": {
            "engine": str(ocr_meta.get("engine", "")),
            "avg_confidence": float(ocr_meta.get("avg_ocr_confidence", 0.0) or 0.0),
            "rerun_attempted_pages": int(ocr_meta.get("rerun_attempted_pages", 0) or 0),
            "rerun_used_pages": int(ocr_meta.get("rerun_used_pages", 0) or 0),
        },
        "model_route": {
            "model_used": result.model_used,
            "model_mode": result.model_mode,
            "model_reason": result.model_reason,
            "fallback_path": fallback_path(llm_diag),
        },
        "routing": {
            "advice_source": getattr(result, "advice_source", ""),
            "advice_status": getattr(result, "advice_status", "static"),
            "advice_id": getattr(result, "advice_id", None),
            "advice_confidence": float(getattr(result, "advice_confidence", 0.0) or 0.0),
            "retrieval_source": getattr(result, "retrieval_source", None),
            "rabi_used": bool(getattr(result, "rabi_used", False)),
            "n_neighbors": getattr(result, "n_neighbors", None),
            "fallback_reason": getattr(result, "fallback_reason", None),
            "static_policy_id": getattr(result, "static_policy_id", None),
            "static_policy_name": getattr(result, "static_policy_name", None),
            "static_policy_reason": getattr(result, "static_policy_reason", None),
            "advice_accepted": bool(getattr(result, "advice_accepted", False)),
            "policy_changed": bool(getattr(result, "policy_changed", False)),
            "route_specialization": getattr(result, "route_specialization", None),
            "blocked_policy": bool(getattr(result, "blocked_policy", False)),
            "rollback_triggered": bool(getattr(result, "rollback_triggered", False)),
            "rollback_reason": getattr(result, "rollback_reason", None),
            "policy_blocked_count": int(getattr(result, "policy_blocked_count", 0) or 0),
            "advisor_recommendation": getattr(result, "advisor_recommendation", None),
            "fallback_candidates": getattr(result, "fallback_candidates", []) or [],
            "operator_stack": getattr(result, "operator_stack", []) or [],
            "defer_status": getattr(result, "defer_status", "not_needed"),
            "defer_reason": getattr(result, "defer_reason", None),
        },
        "field_resolution": {
            "requested": len(requested_field_status),
            "unresolved_count": unresolved_count,
        },
        "schema_quality": schema_quality,
        "reward": {
            "reward": float(getattr(result, "reward", 0.0) or 0.0),
            "reward_type": getattr(result, "reward_type", "proxy"),
            "spent_budget_units": float(getattr(result, "spent_budget_units", 0.0) or 0.0),
            "feedback_logged": bool(getattr(result, "feedback_logged", False)),
            "feedback_error": getattr(result, "feedback_error", None),
        },
        "feedback_status": {
            "logged": bool(getattr(result, "feedback_logged", False)),
            "error": getattr(result, "feedback_error", None),
            "advice_id": getattr(result, "advice_id", None),
        },
        "safety_status": {
            "blocked_policy": bool(getattr(result, "blocked_policy", False)),
            "rollback_triggered": bool(getattr(result, "rollback_triggered", False)),
            "rollback_reason": getattr(result, "rollback_reason", None),
            "policy_blocked_count": int(getattr(result, "policy_blocked_count", 0) or 0),
            "defer_status": getattr(result, "defer_status", "not_needed"),
            "defer_reason": getattr(result, "defer_reason", None),
        },
        "stage_signals": [signal_to_dict(signal) for signal in (getattr(result, "stage_signals", []) or [])],
    }
    _write_json(doc_dir / "provenance" / "transparency.json", payload)


def _append_events(events_path: Path, result, doc_dir: Path) -> None:
    event = {
        "doc_id": result.doc_id,
        "status": "success",
        "timestamp_hint": "doc_artifacts_written",
        "artifacts": {
            "decision_chain": str(doc_dir / "decision_chain.json"),
            "reward": str(doc_dir / "reward.json"),
            "recovery_trace": str(doc_dir / "recovery_trace.json"),
            "transparency": str(doc_dir / "provenance" / "transparency.json"),
        },
    }
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


def _materialize_doc_provenance_from_run(
    run_dir: Path,
    doc_id: str,
    doc_dir: Path,
    run_provenance_index: dict[str, list[dict[str, object]]] | None = None,
) -> None:
    provenance_dir = doc_dir / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)

    if run_provenance_index is not None:
        doc_events = run_provenance_index.get(str(doc_id), [])
    else:
        # Fallback: scan full file (only happens when called outside the normal batch path).
        source_events = run_dir / "provenance" / "events.jsonl"
        doc_events = []
        if source_events.exists():
            with source_events.open("r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        payload = json.loads(stripped)
                    except Exception:
                        continue
                    event_doc_id = str((payload.get("inputs") or {}).get("doc_id") or "").strip()
                    if event_doc_id == str(doc_id):
                        doc_events.append(payload)
    _write_jsonl(provenance_dir / "events.jsonl", doc_events)

    source_graph = run_dir / "provenance" / "provenance_graph.json"
    graph_payload: dict[str, Any] = {"nodes": [], "edges": []}
    if source_graph.exists():
        try:
            graph_payload = json.loads(source_graph.read_text(encoding="utf-8"))
        except Exception:
            graph_payload = {"nodes": [], "edges": []}
    _write_json(provenance_dir / "graph.json", _normalize_doc_layout(graph_payload, doc_id))


def _normalize_doc_layout(graph_payload: dict[str, Any], doc_id: str) -> dict[str, Any]:
    doc_node_id = f"doc:{doc_id}"
    nodes = graph_payload.get("nodes")
    edges = graph_payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return {"nodes": [], "edges": []}

    allowed_nodes = {doc_node_id}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source == doc_node_id or target == doc_node_id:
            allowed_nodes.add(source)
            allowed_nodes.add(target)

    filtered_nodes = [
        node
        for node in nodes
        if isinstance(node, dict) and str(node.get("id") or "") in allowed_nodes
    ]
    filtered_edges = [
        edge
        for edge in edges
        if isinstance(edge, dict)
        and str(edge.get("source") or "") in allowed_nodes
        and str(edge.get("target") or "") in allowed_nodes
    ]
    return {"nodes": filtered_nodes, "edges": filtered_edges}


def _schema_quality_summary(result, requested_field_status: dict[str, dict[str, object]]) -> dict[str, object]:
    expected_keys = [str(key).strip() for key in requested_field_status.keys() if str(key).strip()]
    expected_set = set(expected_keys)
    extracted_keys = {str(entity.key).strip() for entity in (result.entities or []) if str(entity.key).strip()}
    extracted_required = {
        key
        for key in expected_keys
        if key in extracted_keys or _is_concrete_value((requested_field_status.get(key) or {}).get("value", ""))
    }
    grounded_required = {
        str(entity.key).strip()
        for entity in (result.entities or [])
        if str(entity.key).strip() in expected_set and _entity_is_grounded(entity)
    }
    required_field_count = len(expected_set)
    extracted_required_count = len(extracted_required)
    missing_required_count = max(required_field_count - extracted_required_count, 0)
    hallucinated_field_count = len([key for key in extracted_keys if key not in expected_set]) if expected_set else 0
    grounded_field_count = len(grounded_required)
    schema_coverage = round(extracted_required_count / required_field_count, 4) if required_field_count else 0.0
    schema_grounding_coverage = (
        round(grounded_field_count / extracted_required_count, 4) if extracted_required_count else 0.0
    )
    schema_valid = (
        required_field_count > 0
        and missing_required_count == 0
        and hallucinated_field_count == 0
        and len(getattr(result, "validation_issues", []) or []) == 0
    )
    return {
        "required_field_count": required_field_count,
        "extracted_required_count": extracted_required_count,
        "missing_required_count": missing_required_count,
        "hallucinated_field_count": hallucinated_field_count,
        "grounded_field_count": grounded_field_count,
        "schema_coverage": schema_coverage,
        "schema_grounding_coverage": schema_grounding_coverage,
        "schema_valid": schema_valid,
    }


def _is_concrete_value(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.upper() not in {"N/A", "NA"}


def _entity_is_grounded(entity) -> bool:
    # Spatial grounding: OCR bbox or character span
    if getattr(entity, "page", None) is not None:
        return True
    if getattr(entity, "span", None):
        return True
    metadata = getattr(entity, "metadata", {}) or {}
    bbox = metadata.get("bbox")
    if isinstance(bbox, list) and len(bbox) >= 4:
        return True
    # Text grounding: value token appears in source document (set by validation grounding check)
    if metadata.get("text_grounded") is True:
        return True
    # Default: treat as grounded unless explicitly flagged as ungrounded by validation
    # This is the correct default for LLM-extracted entities that passed grounding checks
    return not metadata.get("ungrounded", False)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
