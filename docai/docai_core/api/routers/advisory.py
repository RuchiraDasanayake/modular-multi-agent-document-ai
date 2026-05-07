"""Advisory and adaptive routing endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from docai_core.api.route_helpers import get_db_path
from docai_core.api.schemas import (
    AdvisoryRecommendationOut,
    AdvisoryRequest,
    AdvisoryResponse,
    AdaptiveRoutingAdviceOut,
    AdaptiveRoutingRecommendationOut,
)
from docai_core.persistence import SQLiteStore

router = APIRouter()


@router.post("/advisory/recommend", response_model=AdvisoryResponse)
def advisory_recommend(body: AdvisoryRequest) -> AdvisoryResponse:
    """Read-only advisory endpoint.

    Accepts reviewed PolicyPerformanceRecord evidence and returns a policy
    recommendation. Does not mutate policies, create run artifacts, or affect
    runtime selection. Thompson Sampling / RABI / DAAF are not implemented here.
    """
    from docai_core.application.ahmn_advisory_service import (
        AHMNAdvisoryRequest,
        AHMNAdvisoryService,
    )
    from docai_core.metrics.policy_performance import PolicyPerformanceRecord

    records = [
        PolicyPerformanceRecord(
            policy_id=r.policy_id,
            policy_version=r.policy_version,
            document_type=r.document_type,
            quality_bin=r.quality_bin,
            document_count=r.document_count,
            field_accuracy=r.field_accuracy,
            field_precision=r.field_precision,
            field_recall=r.field_recall,
            field_f1=r.field_f1,
            missing_rate=r.missing_rate,
            correction_rate=r.correction_rate,
            evaluated_at=r.evaluated_at,
        )
        for r in body.records
    ]
    result = AHMNAdvisoryService().recommend(
        AHMNAdvisoryRequest(
            records=records,
            document_type=body.document_type,
            quality_bin=body.quality_bin,
            min_document_count=body.min_document_count,
        )
    )
    rec_out = None
    if result.recommendation is not None:
        rec = result.recommendation
        rec_out = AdvisoryRecommendationOut(
            policy_id=rec.policy_id,
            policy_version=rec.policy_version,
            document_type=rec.document_type,
            quality_bin=rec.quality_bin,
            score=rec.score,
            reason=rec.reason,
            evidence_document_count=rec.evidence_document_count,
            field_f1=rec.field_f1,
            field_accuracy=rec.field_accuracy,
            missing_rate=rec.missing_rate,
            correction_rate=rec.correction_rate,
        )
    return AdvisoryResponse(status=result.status, reason=result.reason, recommendation=rec_out)


@router.get("/projects/{project_id}/adaptive-routing/advice", response_model=AdaptiveRoutingAdviceOut)
def get_adaptive_routing_advice(
    project_id: str,
    request: Request,
    min_evidence: int = 10,
    strategy: str | None = None,
    apply_drift_decay: bool = True,
    half_life_days: int = 30,
) -> AdaptiveRoutingAdviceOut:
    """Get read-only Review-Based Adaptive Routing advice from reviewed evidence."""
    from docai_core.adaptive_routing.advisor import AdaptiveRoutingAdvisor
    from docai_core.adaptive_routing.advisor import ALLOWED_STRATEGIES
    from docai_core.adaptive_routing.evidence import collect_evidence_from_samples

    if strategy is not None and strategy not in ALLOWED_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"strategy must be one of: {', '.join(sorted(ALLOWED_STRATEGIES))}",
        )

    db_path: Path = get_db_path(request)
    store = SQLiteStore(db_path)

    try:
        store.get_project(project_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")

    all_runs = []
    for job in store.list_jobs(project_id):
        all_runs.extend(store.list_runs_for_job(job.job_id))
    all_learning_samples: list[dict[str, Any]] = []

    for run in all_runs:
        run_id = run.run_id
        reviews = store.list_reviews_for_run(run_id)
        run_schema_id = run.schema_id

        for review in reviews:
            review_id = review["review_id"]
            document_id = review["document_id"]
            corrections = review.get("corrections", [])
            for correction in corrections:
                all_learning_samples.append({
                    "sample_id": f"{review_id}_{correction['correction_id']}",
                    "run_id": run_id,
                    "document_id": document_id,
                    "review_id": review_id,
                    "field_name": correction.get("field_name", ""),
                    "decision": correction.get("decision", ""),
                    "schema_id": run_schema_id,
                    "created_at": correction.get("created_at"),
                })

    evidence = collect_evidence_from_samples(project_id, all_learning_samples)

    advisor = AdaptiveRoutingAdvisor(
        min_evidence=min_evidence,
        apply_drift_decay=apply_drift_decay,
        half_life_days=half_life_days,
    )
    advice = advisor.advise(evidence, strategy=strategy, evaluation_time=datetime.now(timezone.utc))

    recommendations = [
        AdaptiveRoutingRecommendationOut(
            recommendation_id=rec.recommendation_id,
            type=rec.type,
            severity=rec.severity,
            schema_id=rec.schema_id,
            field_name=rec.field_name,
            evidence_count=rec.evidence_count,
            correction_rate=rec.correction_rate,
            message=rec.message,
            suggested_action=rec.suggested_action,
            automatic_action_taken=rec.automatic_action_taken,
        )
        for rec in advice.recommendations
    ]

    return AdaptiveRoutingAdviceOut(
        project_id=advice.project_id,
        evidence_count=advice.evidence_count,
        minimum_required=advice.minimum_required,
        status=advice.status,
        generated_by=advice.generated_by,
        is_read_only=advice.is_read_only,
        automatic_action_taken=advice.automatic_action_taken,
        recommendations=recommendations,
        diagnostics=advice.diagnostics,
    )
