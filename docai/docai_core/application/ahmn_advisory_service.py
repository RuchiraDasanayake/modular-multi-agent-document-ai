from __future__ import annotations

from dataclasses import dataclass, field

from docai_core.metrics.policy_performance import PolicyPerformanceRecord
from docai_core.policies.ahmn_policy_advisor import AHMNPolicyAdvisor, AHMNPolicyRecommendation


@dataclass(slots=True)
class AHMNAdvisoryRequest:
    records: list[PolicyPerformanceRecord]
    document_type: str
    quality_bin: str
    min_document_count: int = 10


@dataclass(slots=True)
class AHMNAdvisoryResult:
    recommendation: AHMNPolicyRecommendation | None
    status: str
    reason: str


@dataclass(slots=True)
class AHMNAdvisoryService:
    """Read-only application wrapper over AHMNPolicyAdvisor.

    Accepts PolicyPerformanceRecord evidence and returns a recommendation.
    Does not mutate policies, write artifacts, call models, or affect runtime
    policy selection. Thompson Sampling / RABI / DAAF are not implemented here.
    """

    def recommend(self, request: AHMNAdvisoryRequest) -> AHMNAdvisoryResult:
        advisor = AHMNPolicyAdvisor(min_document_count=request.min_document_count)
        rec = advisor.recommend(
            records=request.records,
            document_type=request.document_type,
            quality_bin=request.quality_bin,
        )

        if rec is not None:
            return AHMNAdvisoryResult(
                recommendation=rec,
                status="recommended",
                reason=rec.reason,
            )

        return AHMNAdvisoryResult(
            recommendation=None,
            status="no_recommendation",
            reason=(
                f"No eligible reviewed policy evidence found for "
                f"{request.document_type}/{request.quality_bin} "
                f"with min_document_count={request.min_document_count}."
            ),
        )
