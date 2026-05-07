"""Learning samples endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request

from docai_core.api.route_helpers import resolve_run_for_review
from docai_core.api.schemas import LearningSampleListOut, LearningSampleOut

router = APIRouter()


@router.get("/runs/{run_id}/learning-samples", response_model=LearningSampleListOut)
def list_learning_samples(run_id: str, request: Request) -> LearningSampleListOut:
    """Get learning samples derived from human review corrections for a run.

    Each correction in a review record becomes one learning sample for future
    training/evaluation. Samples are derived evidence only; no automatic
    training or model updates occur.

    Returns empty list if no reviews exist for the run.
    """
    store, _ = resolve_run_for_review(request, run_id)

    reviews = store.list_reviews_for_run(run_id)

    samples: list[LearningSampleOut] = []

    for review in reviews:
        review_id = review["review_id"]
        document_id = review["document_id"]
        corrections = review.get("corrections", [])

        for correction in corrections:
            correction_id = correction["correction_id"]
            field_name = correction["field_name"]
            extracted_value_snapshot = correction["extracted_value_snapshot"]
            corrected_value = correction["corrected_value"]
            decision = correction["decision"]
            evidence_text_snapshot = correction["evidence_text_snapshot"]
            validation_status_snapshot = correction["validation_status_snapshot"]
            created_at = correction["created_at"]

            sample = LearningSampleOut(
                sample_id=f"{review_id}_{correction_id}",
                run_id=run_id,
                document_id=document_id,
                review_id=review_id,
                field_name=field_name,
                decision=decision,
                original_value=extracted_value_snapshot,
                corrected_value=corrected_value,
                evidence_text=evidence_text_snapshot,
                validation_status=validation_status_snapshot,
                source="human_review",
                created_at=created_at,
            )
            samples.append(sample)

    return LearningSampleListOut(run_id=run_id, samples=samples)
