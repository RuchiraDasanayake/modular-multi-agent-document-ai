"""Document record shaping for inbox processing.

This module converts a pipeline result plus doc artifact paths into the flat
record structure consumed by reports, telemetry, and the frontend.
"""

from __future__ import annotations

from pathlib import Path

from idpo.pipeline.doc_artifacts import fallback_path, _is_concrete_value, _entity_is_grounded


def normalize_key(raw: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in raw).strip("_")


def create_doc_record(result, doc_dir: Path, expected_fields: list[dict[str, str]], doc=None) -> dict[str, object]:
    extracted_text = ""
    if doc and hasattr(doc, "pages") and doc.pages:
        extracted_text = "\n\n".join(
            f"--- Page {page.number} ---\n{page.text}"
            for page in doc.pages
            if page.text
        )

    entities_dict: dict[str, object] = {}
    entity_details: list[dict[str, object]] = []
    for entity in result.entities:
        key = normalize_key(entity.key)
        entities_dict[key] = entity.value
        entity_details.append(
            {
                "key": key,
                "label": entity.key,
                "value": entity.value,
                "confidence": round(entity.confidence, 3) if entity.confidence is not None else 0,
                "page": entity.page,
                "source": (entity.metadata or {}).get("source", "unknown"),
                "is_explicit": bool((entity.metadata or {}).get("explicit")),
            }
        )

    expected_keys = [field["key"] for field in expected_fields]
    requested_field_status = getattr(result, "field_details", {}) or {}
    llm_diagnostics = getattr(result, "llm_diagnostics", {}) or {}
    advisor_recommendation = getattr(result, "advisor_recommendation", None)
    fallback_candidates = getattr(result, "fallback_candidates", []) or []
    recovery_log = getattr(result, "recovery_log", []) or []
    escalation_info = getattr(result, "escalation_info", {}) or {}
    ocr_signal = None
    for signal in getattr(result, "stage_signals", []) or []:
        if getattr(signal, "stage", "") == "ocr":
            ocr_signal = signal
            break
    ocr_meta = getattr(ocr_signal, "metadata", {}) or {}
    llm_fallback_path = fallback_path(llm_diagnostics) if isinstance(llm_diagnostics, dict) else "none"
    unresolved_field_count = sum(
        1 for item in requested_field_status.values() if str((item or {}).get("status", "")).strip() != "extracted"
    )
    schema_metrics = _schema_quality_metrics(
        expected_keys,
        requested_field_status,
        result.entities,
        result.validation_issues,
    )
    for key in expected_keys:
        entities_dict.setdefault(key, "N/A")

    sections_list = [
        {"name": s.name, "text": s.text[:500], "confidence": round(s.confidence, 3)}
        for s in (result.sections or [])
    ]
    validation_list = [
        {"field": vi.field, "issue": vi.issue, "severity": vi.severity}
        for vi in (result.validation_issues or [])
    ]

    filename = Path(result.path).name
    record = {
        "doc_id": result.doc_id,
        "filename": filename,
        "source": result.source,
        "status": "success",
        "category": result.doc_type or result.category or "",
        "doc_type": result.doc_type,
        "vendor_cluster": result.vendor_cluster,
        "routing_family": getattr(result, "routing_family", getattr(result, "semantic_doc_type", "unknown")),
        "semantic_doc_type": getattr(result, "semantic_doc_type", "unknown"),
        "layout_cluster_id": result.layout_cluster_id,
        "route_bin": result.route_bin,
        "route_specialization": result.route_specialization,
        "quality_bin": result.quality_bin,
        "complexity_bin": result.complexity_bin,
        "content_profile": result.content_profile,
        "quality_score": result.quality_score,
        "complexity_score": result.complexity_score,
        "analysis_confidence": round(float(getattr(result, "analysis_confidence", 0.0) or 0.0), 4),
        "analysis_confidence_type": getattr(result, "analysis_confidence_type", "heuristic"),
        "policy_id": result.policy_id,
        "policy_name": result.policy_name,
        "static_policy_id": getattr(result, "static_policy_id", None),
        "static_policy_name": getattr(result, "static_policy_name", None),
        "static_policy_reason": getattr(result, "static_policy_reason", None),
        "advice_source": getattr(result, "advice_source", ""),
        "advice_status": getattr(result, "advice_status", "static"),
        "advice_id": getattr(result, "advice_id", None),
        "advice_confidence": round(float(getattr(result, "advice_confidence", 0.0) or 0.0), 4),
        "retrieval_source": getattr(result, "retrieval_source", None),
        "rabi_used": bool(getattr(result, "rabi_used", False)),
        "n_neighbors": getattr(result, "n_neighbors", None),
        "fallback_reason": getattr(result, "fallback_reason", None),
        "advice_accepted": bool(getattr(result, "advice_accepted", False)),
        "policy_changed": bool(getattr(result, "policy_changed", False)),
        "advisor_recommendation": advisor_recommendation,
        "fallback_candidates": fallback_candidates,
        "defer_status": getattr(result, "defer_status", "not_needed"),
        "defer_reason": getattr(result, "defer_reason", None),
        "blocked_policy": bool(getattr(result, "blocked_policy", False)),
        "rollback_triggered": bool(getattr(result, "rollback_triggered", False)),
        "rollback_reason": getattr(result, "rollback_reason", None),
        "policy_blocked_count": int(getattr(result, "policy_blocked_count", 0) or 0),
        "operator_stack": getattr(result, "operator_stack", []) or [],
        "plan_id": result.plan_id,
        "plan_source": result.plan_source,
        "model_used": getattr(result, "model_used", ""),
        "model_mode": getattr(result, "model_mode", ""),
        "model_reason": getattr(result, "model_reason", ""),
        "latency_ms": round(float(getattr(result, "latency_ms", 0.0) or 0.0), 2),
        "stage_timings_ms": {
            str(k): round(float(v), 2)
            for k, v in (getattr(result, "stage_timings_ms", {}) or {}).items()
        },
        "preprocess_route": ",".join(result.preprocess_route),
        "ocr_engine_used": str(ocr_meta.get("engine", "")),
        "ocr_avg_confidence": round(float(ocr_meta.get("avg_ocr_confidence", 0.0) or 0.0), 2),
        "ocr_rerun_attempted_pages": int(ocr_meta.get("rerun_attempted_pages", 0) or 0),
        "ocr_rerun_used_pages": int(ocr_meta.get("rerun_used_pages", 0) or 0),
        "fallback_path": llm_fallback_path,
        "unresolved_field_count": unresolved_field_count,
        "schema_required_field_count": schema_metrics["required_field_count"],
        "schema_extracted_required_count": schema_metrics["extracted_required_count"],
        "schema_missing_required_count": schema_metrics["missing_required_count"],
        "schema_hallucinated_field_count": schema_metrics["hallucinated_field_count"],
        "schema_grounded_field_count": schema_metrics["grounded_field_count"],
        "schema_coverage": schema_metrics["schema_coverage"],
        "schema_grounding_coverage": schema_metrics["schema_grounding_coverage"],
        "schema_valid": schema_metrics["schema_valid"],
        "entity_count": len(result.entities),
        "explicit_entity_count": len(result.explicit_entities),
        "default_entity_count": len(result.default_entities),
        "validation_issue_count": len(result.validation_issues),
        "recovered_fields_count": len(result.recovered_fields),
        "reward": round(float(getattr(result, "reward", 0.0) or 0.0), 4),
        "reward_type": getattr(result, "reward_type", "proxy"),
        "reward_details": getattr(result, "reward_details", {}) or {},
        "spent_budget_units": round(float(getattr(result, "spent_budget_units", 0.0) or 0.0), 4),
        "feedback_logged": bool(getattr(result, "feedback_logged", False)),
        "feedback_error": getattr(result, "feedback_error", None),
        "recovery_log": recovery_log,
        "escalation_info": escalation_info,
        "escalation_status": getattr(result, "escalation_status", "not_needed"),
        "escalated": result.escalated,
        "chunk_count": len(result.chunks),
        "summary": result.summary,
        "extracted_text": extracted_text,
        "entities": entities_dict,
        "entity_details": entity_details,
        "sections": sections_list,
        "validation_issues": validation_list,
        "field_confidence": result.field_confidence or {},
        "recovered_fields": result.recovered_fields or {},
        "requested_field_status": requested_field_status,
        "llm_diagnostics": llm_diagnostics,
        "structured_fields": {},
        "missing_fields": [],
        "transparency": {
            "ocr_route": {
                "engine": str(ocr_meta.get("engine", "")),
                "avg_confidence": float(ocr_meta.get("avg_ocr_confidence", 0.0) or 0.0),
                "rerun_attempted_pages": int(ocr_meta.get("rerun_attempted_pages", 0) or 0),
                "rerun_used_pages": int(ocr_meta.get("rerun_used_pages", 0) or 0),
            },
            "model_route": {
                "model_used": getattr(result, "model_used", ""),
                "model_mode": getattr(result, "model_mode", ""),
                "model_reason": getattr(result, "model_reason", ""),
                "fallback_path": llm_fallback_path,
            },
            "routing": {
                "advice_source": getattr(result, "advice_source", ""),
                "advice_status": getattr(result, "advice_status", "static"),
                "advice_id": getattr(result, "advice_id", None),
                "advice_confidence": round(float(getattr(result, "advice_confidence", 0.0) or 0.0), 4),
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
                "advisor_recommendation": advisor_recommendation,
                "fallback_candidates": fallback_candidates,
                "operator_stack": getattr(result, "operator_stack", []) or [],
                "defer_status": getattr(result, "defer_status", "not_needed"),
                "defer_reason": getattr(result, "defer_reason", None),
            },
            "field_resolution": {
                "requested": len(requested_field_status),
                "unresolved": unresolved_field_count,
            },
            "schema_quality": schema_metrics,
            "reward": {
                "reward": round(float(getattr(result, "reward", 0.0) or 0.0), 4),
                "reward_type": getattr(result, "reward_type", "proxy"),
                "spent_budget_units": round(float(getattr(result, "spent_budget_units", 0.0) or 0.0), 4),
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
        },
        "input_original_path": _find_original_path(doc_dir),
        "input_manifest_path": str(doc_dir / "input" / "manifest.json"),
        "input_hashes_path": str(doc_dir / "input" / "hashes.json"),
        "dae_output_path": str(doc_dir / "dae" / "output.json"),
        "plan_path": str(doc_dir / "plan" / "primary.json"),
        "ocr_path": str(doc_dir / "preprocessing" / "ocr" / "text.json"),
        "structuring_extracted_path": str(doc_dir / "structuring" / "extracted.json"),
        "structuring_sections_path": str(doc_dir / "structuring" / "sections.json"),
        "structuring_summary_path": str(doc_dir / "structuring" / "summaries.json"),
        "validation_results_path": str(doc_dir / "validation" / "results.json"),
        "validation_normalized_path": str(doc_dir / "validation" / "normalized.json"),
        "recovery_attempts_path": str(doc_dir / "recovery" / "attempts.jsonl"),
        "recovery_escalations_path": str(doc_dir / "recovery" / "escalations.jsonl"),
        "decision_chain_path": str(doc_dir / "decision_chain.json"),
        "reward_path": str(doc_dir / "reward.json"),
        "recovery_trace_path": str(doc_dir / "recovery_trace.json"),
        "chunking_path": str(doc_dir / "chunking" / "chunks.jsonl"),
        "embeddings_index_path": str(doc_dir / "embeddings" / "index"),
        "provenance_graph_path": str(doc_dir / "provenance" / "graph.json"),
        "provenance_events_path": str(doc_dir / "provenance" / "events.jsonl"),
        "transparency_path": str(doc_dir / "provenance" / "transparency.json"),
        "artifacts_path": str(doc_dir / "provenance" / "artifacts"),
    }

    field_map = _map_entities(result.entities)
    for field in expected_fields:
        key = field["key"]
        status = requested_field_status.get(key, {})
        value = str(status.get("value", "")).strip()
        confidence = ""
        if status:
            raw_conf = status.get("confidence")
            if isinstance(raw_conf, (int, float)):
                confidence = f"{float(raw_conf):.3f}"
            elif raw_conf is not None:
                confidence = str(raw_conf)
        page = ""
        span = ""
        source = str(status.get("source", "")).strip() if status else ""

        if not value:
            value, confidence, page, span, source = field_map.get(key, ("", "", "", "", ""))

        record[f"field_{key}"] = value
        record[f"field_{key}_confidence"] = confidence
        record[f"field_{key}_page"] = page
        record[f"field_{key}_span"] = span
        record[f"field_{key}_source"] = source

    if expected_keys:
        record["structured_fields"] = {key: record.get(f"field_{key}", "") for key in expected_keys}
        record["missing_fields"] = [
            key
            for key in expected_keys
            if str((requested_field_status.get(key) or {}).get("status", "")).strip() == "missing"
            or not _is_concrete_value(record.get(f"field_{key}", ""))
        ]
    else:
        record["structured_fields"] = dict(entities_dict)
        record["missing_fields"] = []

    return record


def _map_entities(entities) -> dict[str, tuple[str, str, str, str, str]]:
    mapped: dict[str, tuple[str, str, str, str, str]] = {}
    for entity in entities:
        key = normalize_key(entity.key)
        value = str(entity.value)
        confidence = f"{entity.confidence:.3f}" if entity.confidence is not None else ""
        page = str(entity.page) if entity.page is not None else ""
        span = ""
        if entity.span:
            span = f"{entity.span[0]}:{entity.span[1]}"
        source = ""
        if entity.metadata:
            source = str(entity.metadata.get("source") or entity.metadata.get("explicit") or "")
        existing = mapped.get(key)
        if existing:
            value = f"{existing[0]} | {value}"
        mapped[key] = (value, confidence, page, span, source)
    return mapped


def _schema_quality_metrics(
    expected_keys: list[str],
    requested_field_status: dict[str, dict[str, object]],
    entities,
    validation_issues,
) -> dict[str, object]:
    # Normalize both sides so key comparison is consistent with extraction output
    expected = [normalize_key(str(key)) for key in expected_keys if str(key).strip()]
    expected_set = set(expected)
    extracted_keys: set[str] = set()
    extracted_required_keys: set[str] = set()
    grounded_required_keys: set[str] = set()

    for entity in entities or []:
        key = normalize_key(getattr(entity, "key", ""))
        if not key:
            continue
        extracted_keys.add(key)
        if key in expected_set:
            extracted_required_keys.add(key)
            if _entity_is_grounded(entity):
                grounded_required_keys.add(key)

    # Also credit keys present in requested_field_status with a concrete value
    for raw_key in (requested_field_status or {}):
        key = normalize_key(str(raw_key))
        if key not in expected_set:
            continue
        status = requested_field_status.get(raw_key) or {}
        if _is_concrete_value(status.get("value", "")):
            extracted_required_keys.add(key)

    grounded_field_count = len(grounded_required_keys)
    required_field_count = len(expected_set)
    extracted_required_count = len(extracted_required_keys)
    missing_required_count = max(required_field_count - extracted_required_count, 0)
    hallucinated_field_count = len([key for key in extracted_keys if key not in expected_set]) if expected_set else 0
    schema_coverage = round(extracted_required_count / required_field_count, 4) if required_field_count else 0.0
    schema_grounding_coverage = (
        round(grounded_field_count / extracted_required_count, 4) if extracted_required_count else 0.0
    )
    schema_valid = (
        required_field_count > 0
        and missing_required_count == 0
        and hallucinated_field_count == 0
        and len(validation_issues or []) == 0
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




def _find_original_path(doc_dir: Path) -> str:
    input_dir = doc_dir / "input"
    matches = list(input_dir.glob("original.*"))
    if matches:
        return str(matches[0])
    return str(input_dir / "original")
