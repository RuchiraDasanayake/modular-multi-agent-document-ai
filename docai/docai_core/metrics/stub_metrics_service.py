from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone

from docai_core.contracts.domain import FinalOutput


@dataclass(slots=True)
class JobMetricsSummary:
    job_id: str
    document_count: int
    validation_pass_count: int
    validation_pass_rate: float | None
    recovery_attempted_count: int
    recovery_success_count: int
    recovery_success_rate: float | None
    # Review-dependent metrics — None until ReviewRecord evidence is available.
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    field_accuracy: float | None = None
    table_accuracy: float | None = None
    grounding_coverage: float | None = None
    metrics_status: str = "partial_stub"
    computed_at: datetime = dc_field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class StubMetricsService:
    """Computes computable metrics from FinalOutput objects.

    Fills validation_pass_rate and recovery_success_rate, which are derivable
    from the runtime spine. Leaves review-dependent metrics (precision/recall/f1/
    field_accuracy/table_accuracy) as None — those require ReviewRecord evidence.
    """

    def compute_job_metrics(
        self,
        job_id: str,
        final_outputs: list[FinalOutput],
    ) -> JobMetricsSummary:
        document_count = len(final_outputs)

        validation_pass_count = sum(
            1 for fo in final_outputs if fo.validation_report.pass_status
        )
        validation_pass_rate = (
            round(validation_pass_count / document_count, 4) if document_count > 0 else None
        )

        recovery_attempted_count = sum(
            1 for fo in final_outputs if fo.recovery_report.attempted
        )
        recovery_success_count = sum(
            1
            for fo in final_outputs
            if fo.recovery_report.attempted and fo.recovery_report.status == "recovered"
        )
        recovery_success_rate = (
            round(recovery_success_count / recovery_attempted_count, 4)
            if recovery_attempted_count > 0
            else None
        )

        return JobMetricsSummary(
            job_id=job_id,
            document_count=document_count,
            validation_pass_count=validation_pass_count,
            validation_pass_rate=validation_pass_rate,
            recovery_attempted_count=recovery_attempted_count,
            recovery_success_count=recovery_success_count,
            recovery_success_rate=recovery_success_rate,
        )
