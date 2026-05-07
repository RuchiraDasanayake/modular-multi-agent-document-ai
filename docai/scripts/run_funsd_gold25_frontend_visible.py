#!/usr/bin/env python3
"""FUNSD Gold25 frontend-visible evaluation harness.

Registers and executes FUNSD Gold25 benchmark via running backend API,
making results visible in frontend without creating review records.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import requests


@dataclass
class ComparisonResult:
    """Single field comparison result."""
    document_id: str
    field_name: str
    expected_value: str
    extracted_value: str | None
    match_type: str  # exact_match, normalized_match, missing, wrong_value, extraction_error
    normalized_expected: str
    normalized_extracted: str | None


@dataclass
class DocumentMetric:
    """Per-document evaluation metric."""
    document_id: str
    evaluated_fields: int
    exact_matches: int
    normalized_matches: int
    missing: int
    wrong_value: int
    is_stub: bool
    has_fake_values: bool
    ocr_success: bool


def normalize_text(value: str | None) -> str:
    """Normalize text for comparison: trim, lowercase, collapse whitespace."""
    if value is None:
        return ""
    return " ".join(value.strip().lower().split())


def load_gold_pack(gold_pack_dir: Path) -> tuple[dict, dict, list[dict]]:
    """Load schema, expected values, and manifest from gold pack.

    Extracts from zip if needed.
    """
    gold_pack_dir = Path(gold_pack_dir)

    # Check if we need to extract the zip
    zip_path = gold_pack_dir / "funsd_gold25_common_fields_pack.zip"
    extract_dir = gold_pack_dir / "funsd_gold25_common_fields"

    if zip_path.exists() and not extract_dir.exists():
        print(f"Extracting {zip_path.name}...")
        with ZipFile(zip_path) as zf:
            zf.extractall(gold_pack_dir)

    # Load files
    schema_path = extract_dir / "funsd_gold25_schema.json"
    expected_path = extract_dir / "funsd_gold25_expected_values.json"
    manifest_path = extract_dir / "funsd_gold25_manifest.json"

    with open(schema_path) as f:
        schema = json.load(f)

    with open(expected_path) as f:
        expected_data = json.load(f)

    with open(manifest_path) as f:
        manifest_data = json.load(f)

    return schema, expected_data.get("records", []), manifest_data.get("manifest", [])


def check_health(backend_url: str) -> bool:
    """Check backend health."""
    try:
        resp = requests.get(f"{backend_url}/health", timeout=5)
        if resp.status_code == 200:
            print(f"[OK] Backend healthy: {backend_url}")
            return True
    except Exception as e:
        print(f"[FAIL] Backend unavailable: {e}")
        return False


def create_project(backend_url: str, name: str) -> str | None:
    """Create project and return project_id."""
    try:
        resp = requests.post(f"{backend_url}/projects", json={"name": name}, timeout=10)
        if resp.status_code == 200:
            project_id = resp.json()["project_id"]
            print(f"[OK] Project created: {project_id}")
            return project_id
    except Exception as e:
        print(f"[FAIL] Failed to create project: {e}")
    return None


def create_schema(backend_url: str, project_id: str, schema_def: dict) -> str | None:
    """Create extraction schema and return schema_id."""
    try:
        payload = {
            "name": schema_def.get("name", "FUNSD Gold25 Schema"),
            "document_type": schema_def.get("document_type", "scanned_form"),
            "fields": [
                {
                    "id": f["field_name"],
                    "name": f.get("display_name", f["field_name"]),
                    "type": f.get("type", "string"),
                    "required": f.get("required", False),
                    "description": f.get("description", ""),
                }
                for f in schema_def.get("fields", [])
            ],
            "tables": [],
        }
        resp = requests.post(
            f"{backend_url}/projects/{project_id}/schemas",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            schema_id = resp.json()["schema_id"]
            print(f"[OK] Schema created: {schema_id}")
            return schema_id
        else:
            print(f"[FAIL] Schema creation returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[FAIL] Failed to create schema: {e}")
    return None


def create_extraction_profile(
    backend_url: str,
    project_id: str,
    schema_id: str,
    name: str = "FUNSD Gold25 Form KV",
) -> str | None:
    """Create extraction profile and return profile_id."""
    try:
        payload = {
            "name": name,
            "schema_id": schema_id,
            "mode": "local_text",
            "ocr_strategy": "router_default",
            "validation_level": "strict",
            "is_default": True,
        }
        resp = requests.post(
            f"{backend_url}/projects/{project_id}/extraction-profiles",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            profile_id = resp.json()["profile_id"]
            print(f"[OK] Extraction profile created: {profile_id}")
            return profile_id
    except Exception as e:
        print(f"[FAIL] Failed to create extraction profile: {e}")
    return None


def create_job(backend_url: str, project_id: str, profile_id: str, name: str = "FUNSD Gold25 Job") -> str | None:
    """Create job using profile and return job_id."""
    try:
        payload = {
            "name": name,
            "profile_id": profile_id,
        }
        resp = requests.post(
            f"{backend_url}/projects/{project_id}/jobs",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            job_id = resp.json()["job_id"]
            print(f"[OK] Job created: {job_id}")
            return job_id
    except Exception as e:
        print(f"[FAIL] Failed to create job: {e}")
    return None


def create_run(backend_url: str, job_id: str, schema_id: str) -> str | None:
    """Create run and return run_id."""
    try:
        payload = {
            "name": "Gold25 Evaluation Run",
            "mode": "local_text",
        }
        resp = requests.post(
            f"{backend_url}/jobs/{job_id}/runs",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            run_id = resp.json()["run_id"]
            print(f"[OK] Run created: {run_id}")
            return run_id
    except Exception as e:
        print(f"[FAIL] Failed to create run: {e}")
    return None


def upload_document(
    backend_url: str,
    job_id: str,
    image_path: Path,
) -> dict | None:
    """Upload document image and return upload metadata."""
    try:
        with open(image_path, "rb") as f:
            files = {"file": (image_path.name, f, "image/png")}
            resp = requests.post(
                f"{backend_url}/jobs/{job_id}/documents/upload",
                files=files,
                timeout=30,
            )
        if resp.status_code == 201:
            return resp.json()
    except Exception as e:
        print(f"[FAIL] Failed to upload {image_path.name}: {e}")
    return None


def attach_document_to_run(backend_url: str, run_id: str, document_id: str) -> bool:
    """Attach document to run."""
    try:
        payload = {"document_id": document_id}
        resp = requests.post(
            f"{backend_url}/runs/{run_id}/documents",
            json=payload,
            timeout=10,
        )
        if resp.status_code == 200:
            return True
    except Exception as e:
        print(f"[FAIL] Failed to attach document {document_id}: {e}")
    return False


def execute_run(backend_url: str, run_id: str) -> bool:
    """Execute run."""
    try:
        payload = {"index_artifacts": False}
        resp = requests.post(
            f"{backend_url}/runs/{run_id}/execute",
            json=payload,
            timeout=120,
        )
        if resp.status_code == 200:
            print(f"[OK] Run executed: {run_id}")
            return True
    except Exception as e:
        print(f"[FAIL] Failed to execute run: {e}")
    return False


def get_final_output(backend_url: str, run_id: str, document_id: str) -> dict | None:
    """Get final output for a document."""
    try:
        resp = requests.get(
            f"{backend_url}/runs/{run_id}/documents/{document_id}/final-output",
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        pass
    return None


def get_validation_report(backend_url: str, run_id: str, document_id: str) -> dict | None:
    """Get validation report for a document."""
    try:
        resp = requests.get(
            f"{backend_url}/runs/{run_id}/documents/{document_id}/validation-report",
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        pass
    return None


def extract_field_values(final_output: dict, field_name: str) -> list[str | None]:
    """Extract all occurrences of a field from final_output."""
    values = []
    fields = final_output.get("fields", [])
    for field in fields:
        if field.get("field_name") == field_name:
            value = field.get("value")
            values.append(value)
    return values


def compare_extraction(
    document_id: str,
    field_name: str,
    extracted_values: list[str | None],
    expected_value: str,
) -> ComparisonResult:
    """Compare single expected value to extracted values."""
    normalized_expected = normalize_text(expected_value)

    match_type = "missing"
    extracted_value = None
    normalized_extracted = ""

    if not expected_value:
        # Empty expected value - skip comparison
        match_type = "missing"
    elif extracted_values:
        for value in extracted_values:
            normalized_value = normalize_text(value)
            if value == expected_value:
                match_type = "exact_match"
                extracted_value = value
                normalized_extracted = normalized_value
                break
            elif normalized_value == normalized_expected:
                match_type = "normalized_match"
                extracted_value = value
                normalized_extracted = normalized_value
                break

        if match_type == "missing" and extracted_values:
            match_type = "wrong_value"
            extracted_value = extracted_values[0] if extracted_values else None
            normalized_extracted = normalize_text(extracted_value)

    return ComparisonResult(
        document_id=document_id,
        field_name=field_name,
        expected_value=expected_value,
        extracted_value=extracted_value,
        match_type=match_type,
        normalized_expected=normalized_expected,
        normalized_extracted=normalized_extracted,
    )


def main():
    parser = argparse.ArgumentParser(description="FUNSD Gold25 Frontend-Visible Evaluation")
    parser.add_argument("--backend", default="http://127.0.0.1:8000", help="Backend URL")
    parser.add_argument("--dataset", required=True, help="FUNSD dataset path")
    parser.add_argument("--gold-pack", required=True, help="Gold pack path")
    parser.add_argument("--limit", type=int, help="Limit to N documents (optional)")
    parser.add_argument("--output", default="/tmp/funsd_gold25_frontend_visible_eval.json", help="Output report path")

    args = parser.parse_args()

    backend_url = args.backend.rstrip("/")
    dataset_dir = Path(args.dataset)
    gold_pack_dir = Path(args.gold_pack)
    limit = args.limit
    output_path = Path(args.output)

    print(f"\n=== FUNSD Gold25 Frontend-Visible Evaluation ===")
    print(f"Backend: {backend_url}")
    print(f"Dataset: {dataset_dir}")
    print(f"Gold pack: {gold_pack_dir}")
    if limit:
        print(f"Limit: {limit} documents")
    print()

    # Step 1: Check health
    if not check_health(backend_url):
        sys.exit(1)

    # Step 2: Load gold pack
    print("Loading gold pack...")
    try:
        schema_def, expected_records, manifest = load_gold_pack(gold_pack_dir)
        print(f"[OK] Schema loaded: {len(schema_def.get('fields', []))} fields")
        print(f"[OK] Expected values loaded: {len(expected_records)} records")
        print(f"[OK] Manifest loaded: {len(manifest)} documents")
    except Exception as e:
        print(f"✗ Failed to load gold pack: {e}")
        sys.exit(1)

    if limit:
        manifest = manifest[:limit]
        print(f"[OK] Limited to {limit} documents")

    # Step 3: Create project
    project_id = create_project(backend_url, "FUNSD Gold25 Evaluation")
    if not project_id:
        sys.exit(1)

    # Step 4: Create schema
    schema_id = create_schema(backend_url, project_id, schema_def)
    if not schema_id:
        sys.exit(1)

    # Step 5: Create extraction profile
    profile_id = create_extraction_profile(backend_url, project_id, schema_id)
    if not profile_id:
        sys.exit(1)

    # Step 6: Create job
    job_id = create_job(backend_url, project_id, profile_id)
    if not job_id:
        sys.exit(1)

    # Step 7: Create run
    run_id = create_run(backend_url, job_id, schema_id)
    if not run_id:
        sys.exit(1)

    # Step 8: Upload and attach documents
    print(f"\nUploading and attaching {len(manifest)} documents...")

    uploaded_count = 0
    doc_id_map = {}  # Maps document_id from manifest to uploaded document_id

    for doc_entry in manifest:
        doc_filename = doc_entry["document_filename"]
        doc_manifest_id = doc_entry["document_id"]

        # Locate image under FUNSD dataset
        image_path = dataset_dir / "training_data" / "images" / doc_filename

        if not image_path.exists():
            print(f"  [WARN] Document not found: {image_path}")
            continue

        # Upload
        upload_meta = upload_document(backend_url, job_id, image_path)
        if not upload_meta:
            continue

        uploaded_doc_id = upload_meta["document_id"]
        doc_id_map[doc_manifest_id] = uploaded_doc_id

        # Attach to run
        if attach_document_to_run(backend_url, run_id, uploaded_doc_id):
            uploaded_count += 1
            print(f"  [OK] {doc_filename}")

    print(f"[OK] Uploaded and attached: {uploaded_count} documents")

    # Step 9: Execute run
    print(f"\nExecuting run...")
    if not execute_run(backend_url, run_id):
        sys.exit(1)

    # Step 10: Fetch results and compare
    print(f"\nEvaluating results...")

    all_results = []
    doc_metrics = []
    fake_value_count = 0
    stub_output_count = 0

    # Build expected_by_doc from expected_records where each record is document-level
    expected_by_doc = {}
    for record in expected_records:
        doc_id = record.get("document_id")
        expected_by_doc[doc_id] = record

    for doc_entry in manifest:
        doc_manifest_id = doc_entry["document_id"]

        if doc_manifest_id not in doc_id_map:
            continue

        uploaded_doc_id = doc_id_map[doc_manifest_id]

        # Fetch final output
        final_output = get_final_output(backend_url, run_id, uploaded_doc_id)
        if not final_output:
            print(f"  [WARN] No final output for {doc_manifest_id}")
            continue

        # Check for stub/fake
        is_stub = final_output.get("is_stub", False)
        generated_by = final_output.get("generated_by", "")

        if is_stub or generated_by == "stub_runtime_orchestrator":
            stub_output_count += 1
            print(f"  [FAIL] {doc_manifest_id}: stub output detected")
            continue

        # Compare against expected
        doc_expected_rec = expected_by_doc.get(doc_manifest_id, {})

        # Get schema field names from schema_def to know which fields to evaluate
        schema_field_names = set(f["field_name"] for f in schema_def.get("fields", []))

        exact_matches = 0
        normalized_matches = 0
        missing = 0
        wrong_value = 0
        fake_count = 0

        for field_name in schema_field_names:
            expected_value = doc_expected_rec.get(field_name, "")

            # Skip if no expected value for this field
            if not expected_value or expected_value == "":
                continue

            extracted_values = extract_field_values(final_output, field_name)

            result = compare_extraction(
                doc_manifest_id,
                field_name,
                extracted_values,
                expected_value,
            )
            all_results.append(result)

            if result.match_type == "exact_match":
                exact_matches += 1
            elif result.match_type == "normalized_match":
                normalized_matches += 1
            elif result.match_type == "missing":
                missing += 1
            elif result.match_type == "wrong_value":
                wrong_value += 1

            # Check for fake values
            if result.extracted_value and result.extracted_value.startswith("fake_"):
                fake_count += 1

        evaluated_fields = exact_matches + normalized_matches + missing + wrong_value

        if fake_count > 0:
            fake_value_count += fake_count
            print(f"  [FAIL] {doc_manifest_id}: {fake_count} fake values detected")
        elif evaluated_fields > 0:
            ocr_success = True  # No OCR errors by default
            metric = DocumentMetric(
                document_id=doc_manifest_id,
                evaluated_fields=evaluated_fields,
                exact_matches=exact_matches,
                normalized_matches=normalized_matches,
                missing=missing,
                wrong_value=wrong_value,
                is_stub=False,
                has_fake_values=False,
                ocr_success=ocr_success,
            )
            doc_metrics.append(metric)
            print(f"  [OK] {doc_manifest_id}: {exact_matches + normalized_matches}/{evaluated_fields}")

    # Step 11: Generate report
    print(f"\nGenerating report...")

    # Count actual field-level comparisons made (not document count)
    total_expected_rows_loaded = len(expected_records)  # Document records from gold pack
    total_expected_rows_compared = len(all_results)      # Actual field comparisons performed

    exact_count = sum(1 for r in all_results if r.match_type == "exact_match")
    normalized_count = sum(1 for r in all_results if r.match_type == "normalized_match")
    missing_count = sum(1 for r in all_results if r.match_type == "missing")
    wrong_count = sum(1 for r in all_results if r.match_type == "wrong_value")

    # Validate accounting
    accounting_valid = (exact_count + normalized_count + missing_count + wrong_count) == total_expected_rows_compared

    # Count OCR diagnostics
    ocr_text_present_count = 0
    ocr_text_empty_count = 0
    docs_with_any_extracted_value = 0
    docs_with_all_missing = 0
    total_ocr_text_length = 0

    for doc_entry in manifest:
        doc_manifest_id = doc_entry["document_id"]
        if doc_manifest_id not in doc_id_map:
            continue

        uploaded_doc_id = doc_id_map[doc_manifest_id]
        final_output = get_final_output(backend_url, run_id, uploaded_doc_id)

        if final_output:
            ocr_text = final_output.get("ocr_text", "")
            if ocr_text:
                ocr_text_present_count += 1
                total_ocr_text_length += len(ocr_text)
            else:
                ocr_text_empty_count += 1

            # Check if document has any non-empty extracted values
            fields = final_output.get("fields", [])
            has_any_value = any(f.get("value") and f.get("value").strip() for f in fields)
            if has_any_value:
                docs_with_any_extracted_value += 1

            # Check if all expected fields are missing for this doc
            doc_expected_rec = expected_by_doc.get(doc_manifest_id, {})
            schema_field_names = set(f["field_name"] for f in schema_def.get("fields", []))

            all_missing_for_doc = True
            for field_name in schema_field_names:
                expected_value = doc_expected_rec.get(field_name, "")
                if not expected_value or expected_value == "":
                    continue

                extracted_values = extract_field_values(final_output, field_name)
                if extracted_values and any(v for v in extracted_values):
                    all_missing_for_doc = False
                    break

            if all_missing_for_doc and total_expected_rows_compared > 0:
                docs_with_all_missing += 1

    avg_ocr_text_length = total_ocr_text_length / ocr_text_present_count if ocr_text_present_count > 0 else 0

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backend": backend_url,
        "dataset": str(dataset_dir),
        "gold_pack": str(gold_pack_dir),
        "summary": {
            "project_id": project_id,
            "job_id": job_id,
            "run_id": run_id,
            "documents_uploaded": uploaded_count,
            "documents_evaluated": len(doc_metrics),
            "total_expected_rows_loaded": total_expected_rows_loaded,
            "total_expected_rows_compared": total_expected_rows_compared,
            "exact_matches": exact_count,
            "normalized_matches": normalized_count,
            "missing": missing_count,
            "wrong_value": wrong_count,
            "fake_values": fake_value_count,
            "stub_outputs": stub_output_count,
            "ocr_failures": 0,
            "ocr_text_present_count": ocr_text_present_count,
            "ocr_text_empty_count": ocr_text_empty_count,
            "avg_ocr_text_length": round(avg_ocr_text_length, 1),
            "docs_with_any_extracted_value": docs_with_any_extracted_value,
            "docs_with_all_missing": docs_with_all_missing,
            "comparison_accounting_valid": accounting_valid,
        },
        "document_metrics": [asdict(m) for m in doc_metrics],
        "detailed_results": [asdict(r) for r in all_results],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[OK] Report written to: {output_path}")

    # Print summary
    print(f"\n=== EVALUATION SUMMARY ===")
    print(f"Documents uploaded: {uploaded_count}")
    print(f"Documents evaluated: {len(doc_metrics)}")
    print(f"Expected rows loaded: {total_expected_rows_loaded} (document records)")
    print(f"Expected rows compared: {total_expected_rows_compared} (field instances)")
    print(f"Accounting valid: {accounting_valid}")
    print(f"")
    print(f"Exact matches: {exact_count}")
    print(f"Normalized matches: {normalized_count}")
    print(f"Missing: {missing_count}")
    print(f"Wrong value: {wrong_count}")
    print(f"Fake values: {fake_value_count}")
    print(f"Stub outputs: {stub_output_count}")
    print(f"")
    print(f"=== DIAGNOSTICS ===")
    print(f"OCR text present: {ocr_text_present_count}/{uploaded_count}")
    print(f"OCR text empty: {ocr_text_empty_count}/{uploaded_count}")
    print(f"Avg OCR text length: {avg_ocr_text_length:.1f} chars")
    print(f"Docs with any extracted value: {docs_with_any_extracted_value}/{uploaded_count}")
    print(f"Docs with all missing values: {docs_with_all_missing}/{uploaded_count}")
    print(f"")
    if ocr_text_empty_count == uploaded_count:
        print(f"ROOT CAUSE: OCR text field is empty (not populated by extraction pipeline)")

    if docs_with_any_extracted_value > 0 and missing_count > 0:
        if docs_with_all_missing == uploaded_count:
            print(f"            BUT extraction found values: KV matching problem")
            print(f"            (local text extractor cannot map to FUNSD label fields)")
        else:
            print(f"            Partial KV matching: {docs_with_any_extracted_value - docs_with_all_missing}")
            print(f"            docs partially matched, {docs_with_all_missing} completely missed")

    # Print frontend URLs
    print(f"\n=== FRONTEND URLS ===")
    frontend_base = "http://127.0.0.1:5173"
    print(f"Project: {frontend_base}/projects/{project_id}")
    print(f"Job: {frontend_base}/jobs/{job_id}")
    print(f"Run: {frontend_base}/runs/{run_id}")

    print(f"\nOr use IDs to navigate:")
    print(f"project_id: {project_id}")
    print(f"job_id: {job_id}")
    print(f"run_id: {run_id}")


if __name__ == "__main__":
    main()
