from __future__ import annotations

from dataclasses import dataclass, field

from docai_core.metrics.policy_performance import PolicyPerformanceRecord


@dataclass(slots=True)
class AHMNPolicyRecommendation:
    """A read-only recommendation produced by AHMNPolicyAdvisor.

    Never mutates policy state. Never triggers automatic policy selection.
    """

    policy_id: str
    policy_version: str
    document_type: str
    quality_bin: str
    score: float | None
    reason: str
    evidence_document_count: int
    field_f1: float | None
    field_accuracy: float | None
    missing_rate: float | None
    correction_rate: float | None


def _score(rec: PolicyPerformanceRecord) -> float:
    base = rec.field_f1 if rec.field_f1 is not None else rec.field_accuracy
    if base is None:
        return 0.0
    s = base
    if rec.missing_rate is not None:
        s -= 0.10 * rec.missing_rate
    if rec.correction_rate is not None:
        s -= 0.10 * rec.correction_rate
    return max(0.0, min(1.0, s))


@dataclass(slots=True)
class AHMNPolicyAdvisor:
    """Recommends the best policy for a document profile from reviewed evidence.

    Read-only. Does not mutate policies, write artifacts, call models, or
    implement Thompson Sampling / RABI / DAAF / automatic learning.
    Requires at least min_document_count reviewed documents before recommending.
    """

    min_document_count: int = 10

    def recommend(
        self,
        records: list[PolicyPerformanceRecord],
        document_type: str,
        quality_bin: str,
    ) -> AHMNPolicyRecommendation | None:
        eligible = [
            r for r in records
            if r.document_type == document_type
            and r.quality_bin == quality_bin
            and r.document_count >= self.min_document_count
        ]

        if not eligible:
            return None

        best = max(eligible, key=_score)
        metric_label = "F1" if best.field_f1 is not None else "accuracy"
        metric_value = best.field_f1 if best.field_f1 is not None else best.field_accuracy
        value_str = f"{metric_value:.3f}" if metric_value is not None else "N/A"

        reason = (
            f"Selected {best.policy_id} because it has the highest reviewed "
            f"{metric_label} ({value_str}) for {document_type}/{quality_bin} "
            f"over {best.document_count} documents."
        )

        return AHMNPolicyRecommendation(
            policy_id=best.policy_id,
            policy_version=best.policy_version,
            document_type=best.document_type,
            quality_bin=best.quality_bin,
            score=round(_score(best), 6),
            reason=reason,
            evidence_document_count=best.document_count,
            field_f1=best.field_f1,
            field_accuracy=best.field_accuracy,
            missing_rate=best.missing_rate,
            correction_rate=best.correction_rate,
        )
