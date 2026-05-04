"""Inbox-based document processing with batch orchestration and result export."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from idpo.agents.intake import IntakeAgent
from idpo.core.config import PipelineConfig, load_config
from idpo.core.preflight import run_preflight
from idpo.pipeline.orchestrator import Pipeline

SUPPORTED_INPUT_EXTS = {".json", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

BASE_DOC_HEADERS = [
    "doc_id",
    "source",
    "doc_type",
    "vendor_cluster",
    "quality_bin",
    "complexity_bin",
    "content_profile",
    "quality_score",
    "complexity_score",
    "policy_id",
    "policy_name",
    "plan_id",
    "plan_source",
    "preprocess_route",
    "entity_count",
    "explicit_entity_count",
    "default_entity_count",
    "validation_issue_count",
    "recovered_fields_count",
    "escalated",
    "chunk_count",
    "summary",
    "input_original_path",
    "input_manifest_path",
    "input_hashes_path",
    "dae_output_path",
    "plan_path",
    "ocr_path",
    "structuring_extracted_path",
    "structuring_sections_path",
    "structuring_summary_path",
    "validation_results_path",
    "validation_normalized_path",
    "recovery_attempts_path",
    "recovery_escalations_path",
    "chunking_path",
    "embeddings_index_path",
    "provenance_graph_path",
    "provenance_events_path",
    "artifacts_path",
]

def process_inbox(
    root: Path,
    config_path: str | None = None,
    extraction_fields: Optional[list[dict[str, str]]] = None,
    run_id: str | None = None,
    file_paths: list[str] | None = None,
) -> dict[str, Any]:
    config = load_config(config_path)
    config.shadow.enabled = False
    preflight_warnings = run_preflight(config)

    root = Path(root)
    inbox_dir = root / "inputs" / "inbox"
    processed_dir = root / "inputs" / "processed"
    runs_dir = root / "runs"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    if file_paths:
        files = [Path(p) for p in file_paths if Path(p).exists() and Path(p).suffix.lower() in SUPPORTED_INPUT_EXTS]
    else:
        files = [
            path for path in inbox_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_INPUT_EXTS
        ]
    if not files:
        raise ValueError(f"No supported files found in {inbox_dir}. Drop files there and retry.")

    resolved_run_id = run_id or uuid.uuid4().hex
    run_dir = runs_dir / resolved_run_id
    docs_dir = run_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    expected_fields = _normalize_fields(extraction_fields or [])
    if expected_fields:
        _write_fields_schema(run_dir, expected_fields)
        _apply_field_overrides(config, run_dir, expected_fields)

    events_path = run_dir / "events.jsonl"
    errors_path = run_dir / "errors.jsonl"
    start_time = time.time()
    run_payload = {
        "run_id": resolved_run_id,
        "started_at": start_time,
        "config_path": config_path,
        "policy_store_path": config.knowledge.policy_store_path,
        "preflight_warnings": " | ".join(preflight_warnings),
    }
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2), encoding="utf-8")

    intake = IntakeAgent()
    failed: list[dict[str, str]] = []
    doc_records: list[dict[str, object]] = []
    for file_path in files:
        try:
            docs = intake.ingest(str(file_path))
            for doc in docs:
                doc_dir = docs_dir / doc.doc_id
                _ensure_doc_dirs(doc_dir)
                _copy_original_input(file_path, doc_dir)
                _write_doc_manifest(doc, doc_dir)
                _write_hashes(file_path, doc, doc_dir)

                pipeline = Pipeline(config=config, run_dir=str(doc_dir))
                results = pipeline.process_documents([doc])
                pipeline.build_index(results, directory=str(doc_dir / "embeddings" / "index"))

                result = results[0]
                _write_dae_output(result, doc_dir)
                _write_plan_output(result, doc_dir)
                _write_structuring(result, doc_dir)
                _write_validation(result, doc_dir)
                _write_recovery(result, doc_dir)
                _write_chunking(result, doc_dir)
                _write_ocr_output(doc, result, doc_dir)
                _write_provenance(doc_dir)
                _append_events(doc_dir, events_path)
                _normalize_doc_layout(doc_dir)
                doc_records.append(_doc_record(result, doc_dir, expected_fields, doc))

            shutil.move(str(file_path), str(processed_dir / file_path.name))
        except Exception as exc:
            error_msg = str(exc)
            failed.append({"file": file_path.name, "error": error_msg})
            errors_path.parent.mkdir(parents=True, exist_ok=True)
            with errors_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"file": str(file_path), "error": error_msg}) + "\n")
            # Move failed files out of inbox to prevent re-processing on next run
            failed_dir = root / "inputs" / "failed"
            failed_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(file_path), str(failed_dir / file_path.name))
            except Exception:
                pass

    metrics_payload = {
        "doc_count": len(files),
        "failed_count": len(failed),
        "ended_at": time.time(),
        "duration_ms": (time.time() - start_time) * 1000,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")
    _write_docs_excel(run_dir, doc_records)
    _write_entities_excel(run_dir, doc_records, expected_fields)
    _write_run_excel(run_dir, run_payload, metrics_payload)

    return {
        "run_id": resolved_run_id,
        "run_dir": str(run_dir),
        "doc_records": doc_records,
        "entity_records": _entity_records(doc_records, expected_fields),
        "metrics": metrics_payload,
        "run_payload": run_payload,
        "preflight_warnings": preflight_warnings,
        "failed": failed,
    }

def _apply_field_overrides(config: PipelineConfig, run_dir: Path, fields: list[dict[str, str]]) -> None:
    names = [field["key"] for field in fields]
    descriptions = {field["key"]: field.get("description", "") for field in fields if field.get("description")}
    override = {
        "default_policy_id": "custom_fields",
        "policies": [
            {
                "policy_id": "custom_fields",
                "name": "Custom Fields",
                "conditions": {},
                "actions": {
                    "extraction": {
                        "explicit_entities": names,
                        "field_descriptions": descriptions,
                    }
                },
            }
        ],
    }
    policy_path = run_dir / "policy_override.json"
    policy_path.write_text(json.dumps(override, indent=2), encoding="utf-8")
    config.knowledge.policy_store_path = str(policy_path)
    config.llm.use_extraction = True

def _normalize_fields(fields: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for field in fields:
        name = str(field.get("name", "")).strip()
        description = str(field.get("description", "")).strip()
        if not name:
            continue
        key = _normalize_key(name)
        normalized.append({"name": name, "key": key, "description": description})
    return normalized

def _write_fields_schema(run_dir: Path, fields: list[dict[str, str]]) -> None:
    schema = {"fields": fields}
    (run_dir / "fields.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

def _normalize_key(raw: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in raw).strip("_")

def _ensure_doc_dirs(doc_dir: Path) -> None:
    for folder in [
        doc_dir / "input",
        doc_dir / "dae",
        doc_dir / "plan" / "shadow",
        doc_dir / "preprocessing" / "ocr",
        doc_dir / "preprocessing" / "layout",
        doc_dir / "structuring",
        doc_dir / "validation",
        doc_dir / "recovery",
        doc_dir / "chunking",
        doc_dir / "embeddings",
        doc_dir / "retrieval",
        doc_dir / "qa",
        doc_dir / "provenance",
    ]:
        folder.mkdir(parents=True, exist_ok=True)

def _copy_original_input(file_path: Path, doc_dir: Path) -> None:
    if not file_path.exists():
        return
    dest = doc_dir / "input" / f"original{file_path.suffix.lower()}"
    shutil.copy2(file_path, dest)

def _write_doc_manifest(doc, doc_dir: Path) -> None:
    payload = {
        "doc_id": doc.doc_id,
        "source": doc.source,
        "path": doc.path,
        "metadata": doc.metadata,
    }
    (doc_dir / "input" / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def _write_hashes(file_path: Path, doc, doc_dir: Path) -> None:
    sha256 = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha256.update(chunk)
    mime = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    payload = {
        "sha256": sha256.hexdigest(),
        "size_bytes": file_path.stat().st_size,
        "mime_type": mime,
        "pages": len(getattr(doc, "pages", []) or []),
    }
    (doc_dir / "input" / "hashes.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def _write_dae_output(result, doc_dir: Path) -> None:
    payload = {
        "doc_type": result.doc_type,
        "vendor_cluster": result.vendor_cluster,
        "quality_bin": result.quality_bin,
        "complexity_bin": result.complexity_bin,
        "content_profile": result.content_profile,
        "quality_score": result.quality_score,
        "complexity_score": result.complexity_score,
        "signals": result.dae_signals,
    }
    (doc_dir / "dae" / "output.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def _write_plan_output(result, doc_dir: Path) -> None:
    payload = result.plan_payload or {}
    (doc_dir / "plan" / "primary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def _write_structuring(result, doc_dir: Path) -> None:
    extracted = {
        "entities": [entity.__dict__ for entity in result.entities],
        "explicit_entities": [entity.__dict__ for entity in result.explicit_entities],
        "default_entities": [entity.__dict__ for entity in result.default_entities],
        "explicit_source": result.explicit_source,
    }
    (doc_dir / "structuring" / "extracted.json").write_text(json.dumps(extracted, indent=2), encoding="utf-8")
    sections = {"sections": [section.__dict__ for section in result.sections]}
    (doc_dir / "structuring" / "sections.json").write_text(json.dumps(sections, indent=2), encoding="utf-8")
    (doc_dir / "structuring" / "summaries.json").write_text(
        json.dumps({"summary": result.summary}, indent=2),
        encoding="utf-8",
    )

def _write_validation(result, doc_dir: Path) -> None:
    (doc_dir / "validation" / "results.json").write_text(
        json.dumps({"issues": [issue.__dict__ for issue in result.validation_issues]}, indent=2),
        encoding="utf-8",
    )
    (doc_dir / "validation" / "normalized.json").write_text(
        json.dumps(result.normalized_entities, indent=2),
        encoding="utf-8",
    )

def _write_recovery(result, doc_dir: Path) -> None:
    (doc_dir / "recovery" / "attempts.jsonl").write_text(
        json.dumps(result.recovered_fields, indent=2),
        encoding="utf-8",
    )
    (doc_dir / "recovery" / "escalations.jsonl").write_text(
        json.dumps({"escalated": result.escalated}, indent=2),
        encoding="utf-8",
    )

def _write_chunking(result, doc_dir: Path) -> None:
    chunks_path = doc_dir / "chunking" / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in result.chunks:
            handle.write(json.dumps(chunk.__dict__) + "\n")

def _write_provenance(doc_dir: Path) -> None:
    graph_path = doc_dir / "provenance_graph.json"
    if graph_path.exists():
        target = doc_dir / "provenance" / "graph.json"
        shutil.copy2(graph_path, target)

def _write_ocr_output(doc, result, doc_dir: Path) -> None:
    ocr_signal = None
    for signal in result.stage_signals:
        if signal.stage == "ocr":
            ocr_signal = signal
            break
    pages = []
    for page in doc.pages:
        pages.append(
            {
                "number": page.number,
                "text": page.text,
                "confidence": ocr_signal.confidence if ocr_signal else None,
            }
        )
    payload = {"pages": pages, "confidence": ocr_signal.confidence if ocr_signal else None}
    (doc_dir / "preprocessing" / "ocr" / "text.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

def _append_events(doc_dir: Path, events_path: Path) -> None:
    src = doc_dir / "provenance.jsonl"
    if not src.exists():
        return
    with src.open("r", encoding="utf-8") as handle, events_path.open("a", encoding="utf-8") as out:
        for line in handle:
            if line.strip():
                out.write(line)

def _normalize_doc_layout(doc_dir: Path) -> None:
    provenance_dir = doc_dir / "provenance"
    provenance_dir.mkdir(parents=True, exist_ok=True)
    moves = {
        doc_dir / "provenance_graph.json": provenance_dir / "graph.json",
        doc_dir / "provenance.jsonl": provenance_dir / "events.jsonl",
        doc_dir / "run_metadata.json": provenance_dir / "run_metadata.json",
        doc_dir / "policy_rollbacks.json": provenance_dir / "policy_rollbacks.json",
    }
    for src, dest in moves.items():
        if src.exists():
            shutil.move(str(src), str(dest))
    artifacts_dir = doc_dir / "artifacts"
    if artifacts_dir.exists():
        shutil.move(str(artifacts_dir), str(provenance_dir / "artifacts"))

def _doc_record(result, doc_dir: Path, expected_fields: list[dict[str, str]], doc=None) -> dict[str, object]:
    # Build extracted full text from document pages
    extracted_text = ""
    if doc and hasattr(doc, "pages") and doc.pages:
        extracted_text = "\n\n".join(
            f"--- Page {page.number} ---\n{page.text}"
            for page in doc.pages
            if page.text
        )

    # Build structured entities dict for the frontend
    entities_dict: dict[str, object] = {}
    entity_details: list[dict[str, object]] = []
    for entity in result.entities:
        key = _normalize_key(entity.key)
        entities_dict[key] = entity.value
        entity_details.append({
            "key": key,
            "label": entity.key,
            "value": entity.value,
            "confidence": round(entity.confidence, 3) if entity.confidence is not None else 0,
            "page": entity.page,
            "source": (entity.metadata or {}).get("source", "unknown"),
            "is_explicit": bool((entity.metadata or {}).get("explicit")),
        })

    # Build sections list for the frontend
    sections_list = [
        {"name": s.name, "text": s.text[:500], "confidence": round(s.confidence, 3)}
        for s in (result.sections or [])
    ]

    # Build validation issues for the frontend
    validation_list = [
        {"field": vi.field, "issue": vi.issue, "severity": vi.severity}
        for vi in (result.validation_issues or [])
    ]

    # Determine original filename from path
    original_path = Path(result.path)
    filename = original_path.name

    record = {
        "doc_id": result.doc_id,
        "filename": filename,
        "source": result.source,
        "status": "success",
        "category": result.doc_type or result.category or "",
        "doc_type": result.doc_type,
        "vendor_cluster": result.vendor_cluster,
        "quality_bin": result.quality_bin,
        "complexity_bin": result.complexity_bin,
        "content_profile": result.content_profile,
        "quality_score": result.quality_score,
        "complexity_score": result.complexity_score,
        "policy_id": result.policy_id,
        "policy_name": result.policy_name,
        "plan_id": result.plan_id,
        "plan_source": result.plan_source,
        "model_used": getattr(result, "model_used", ""),
        "model_mode": getattr(result, "model_mode", ""),
        "preprocess_route": ",".join(result.preprocess_route),
        "entity_count": len(result.entities),
        "explicit_entity_count": len(result.explicit_entities),
        "default_entity_count": len(result.default_entities),
        "validation_issue_count": len(result.validation_issues),
        "recovered_fields_count": len(result.recovered_fields),
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
        "chunking_path": str(doc_dir / "chunking" / "chunks.jsonl"),
        "embeddings_index_path": str(doc_dir / "embeddings" / "index"),
        "provenance_graph_path": str(doc_dir / "provenance" / "graph.json"),
        "provenance_events_path": str(doc_dir / "provenance" / "events.jsonl"),
        "artifacts_path": str(doc_dir / "provenance" / "artifacts"),
    }

    field_map = _map_entities(result.entities)
    for field in expected_fields:
        key = field["key"]
        value, confidence, page, span, source = field_map.get(key, ("", "", "", "", ""))
        record[f"field_{key}"] = value
        record[f"field_{key}_confidence"] = confidence
        record[f"field_{key}_page"] = page
        record[f"field_{key}_span"] = span
        record[f"field_{key}_source"] = source

    return record

def _map_entities(entities) -> dict[str, tuple[str, str, str, str, str]]:
    mapped: dict[str, tuple[str, str, str, str, str]] = {}
    for entity in entities:
        key = _normalize_key(entity.key)
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

def _find_original_path(doc_dir: Path) -> str:
    input_dir = doc_dir / "input"
    matches = list(input_dir.glob("original.*"))
    if matches:
        return str(matches[0])
    return str(input_dir / "original")

def _write_docs_excel(run_dir: Path, records: list[dict[str, object]]) -> None:
    if not records:
        return
    headers = _collect_headers(records)
    try:
        import openpyxl
    except Exception:
        csv_path = run_dir / "docs.csv"
        with csv_path.open("w", encoding="utf-8") as handle:
            handle.write(",".join(headers) + "\n")
            for record in records:
                row = [str(record.get(header, "")).replace(",", " ") for header in headers]
                handle.write(",".join(row) + "\n")
        return
    path = run_dir / "docs.xlsx"
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "docs"
    sheet.append(headers)
    for record in records:
        sheet.append([_excel_safe(record.get(header, "")) for header in headers])
    wb.save(path)

def _collect_headers(records: list[dict[str, object]]) -> list[str]:
    if not records:
        return []
    keys = set()
    for record in records:
        keys.update(record.keys())
    ordered = [key for key in BASE_DOC_HEADERS if key in keys]
    remaining = sorted(key for key in keys if key not in ordered)
    return ordered + remaining

def _entity_records(records: list[dict[str, object]], expected_fields: list[dict[str, str]]) -> list[dict[str, object]]:
    if not expected_fields:
        return []
    field_keys = [field["key"] for field in expected_fields]
    entity_records = []
    for record in records:
        row = {"doc_id": record.get("doc_id", "")}
        for key in field_keys:
            row[key] = record.get(f"field_{key}", "")
        entity_records.append(row)
    return entity_records

def _write_entities_excel(
    run_dir: Path,
    records: list[dict[str, object]],
    expected_fields: list[dict[str, str]],
) -> None:
    entity_records = _entity_records(records, expected_fields)
    if not entity_records:
        return
    headers = ["doc_id"] + [field["key"] for field in expected_fields]
    try:
        import openpyxl
    except Exception:
        csv_path = run_dir / "entities.csv"
        with csv_path.open("w", encoding="utf-8") as handle:
            handle.write(",".join(headers) + "\n")
            for record in entity_records:
                row = [str(record.get(header, "")).replace(",", " ") for header in headers]
                handle.write(",".join(row) + "\n")
        return
    path = run_dir / "entities.xlsx"
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "entities"
    sheet.append(headers)
    for record in entity_records:
        sheet.append([record.get(header, "") for header in headers])
    wb.save(path)

def _write_run_excel(run_dir: Path, run_payload: dict[str, object], metrics_payload: dict[str, object]) -> None:
    try:
        import openpyxl
    except Exception:
        csv_path = run_dir / "run.csv"
        payload = {**run_payload, **metrics_payload}
        headers = sorted(payload.keys())
        with csv_path.open("w", encoding="utf-8") as handle:
            handle.write(",".join(headers) + "\n")
            handle.write(",".join(str(payload.get(header, "")) for header in headers))
        return
    path = run_dir / "run.xlsx"
    wb = openpyxl.Workbook()
    sheet = wb.active
    sheet.title = "run"
    payload = {**run_payload, **metrics_payload}
    headers = sorted(payload.keys())
    sheet.append(headers)
    sheet.append([_excel_safe(payload.get(header, "")) for header in headers])
    wb.save(path)

def _excel_safe(value: object) -> object:
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value
