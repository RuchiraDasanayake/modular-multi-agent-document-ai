"""Review record endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request

from docai_core.api.route_helpers import (
    ensure_run_document_mapping,
    read_doc_artifact,
    resolve_run_for_review,
    validate_and_build_corrections,
    final_output_field_snapshot_by_name,
)
from docai_core.api.schemas import ReviewRecordCreate, ReviewRecordOut

router = APIRouter()


@router.post("/runs/{run_id}/documents/{doc_id}/review-record", response_model=ReviewRecordOut)
def create_review_record(
    run_id: str,
    doc_id: str,
    body: ReviewRecordCreate,
    request: Request,
) -> ReviewRecordOut:
    """Create a review record for a document."""
    store, run = resolve_run_for_review(request, run_id)
    ensure_run_document_mapping(store, run_id, doc_id)

    final_output = read_doc_artifact(request, run_id, doc_id, "final_output.json")
    snapshot_by_field = final_output_field_snapshot_by_name(final_output)
    corrections = validate_and_build_corrections(body, snapshot_by_field)

    record = store.create_review_record(
        run_id=run_id,
        job_id=run.job_id,
        document_id=doc_id,
        schema_id=run.schema_id,
        review_status=body.review_status,
        reviewer_id=body.reviewer_id,
        review_note=body.review_note,
        source="human_review",
        corrections=corrections,
    )
    return ReviewRecordOut(**record)


@router.get("/runs/{run_id}/documents/{doc_id}/review-records", response_model=list[ReviewRecordOut])
def list_review_records(run_id: str, doc_id: str, request: Request) -> list[ReviewRecordOut]:
    """List all review records for a document."""
    store, _ = resolve_run_for_review(request, run_id)
    ensure_run_document_mapping(store, run_id, doc_id)
    records = store.list_review_records(run_id, doc_id)
    return [ReviewRecordOut(**record) for record in records]


@router.get("/runs/{run_id}/documents/{doc_id}/latest-review-record", response_model=ReviewRecordOut)
def get_latest_review_record(run_id: str, doc_id: str, request: Request) -> ReviewRecordOut:
    """Get the latest review record for a document."""
    from fastapi import HTTPException
    store, _ = resolve_run_for_review(request, run_id)
    ensure_run_document_mapping(store, run_id, doc_id)
    record = store.get_latest_review_record(run_id, doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No review records found for run={run_id} doc={doc_id}")
    return ReviewRecordOut(**record)
