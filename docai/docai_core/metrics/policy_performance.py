from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NamedTuple

from docai_core.metrics.evaluator import DocumentMetrics


@dataclass(slots=True)
class DocumentPolicyProfile:
    """Maps a document to the policy that processed it."""

    policy_id: str
    policy_version: str = "v1"
    document_type: str = "unknown"
    quality_bin: str = "unknown"


@dataclass(slots=True)
class PolicyPerformanceRecord:
    """Aggregated extraction performance for one (policy, version, document_type, quality_bin) group."""

    policy_id: str
    policy_version: str
    document_type: str
    quality_bin: str
    document_count: int
    field_accuracy: float | None
    field_precision: float | None
    field_recall: float | None
    field_f1: float | None
    missing_rate: float | None
    correction_rate: float | None
    evaluated_at: datetime


class _GroupKey(NamedTuple):
    policy_id: str
    policy_version: str
    document_type: str
    quality_bin: str


def _avg(values: list[float | None]) -> float | None:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    return round(sum(non_null) / len(non_null), 6)


@dataclass(slots=True)
class PolicyPerformanceAggregator:
    """Groups DocumentMetrics by policy profile and computes per-group performance records.

    Does not read or write artifacts, call models, or mutate policy state.
    """

    def aggregate(
        self,
        document_metrics: list[DocumentMetrics],
        profile_by_document_id: dict[str, DocumentPolicyProfile],
    ) -> list[PolicyPerformanceRecord]:
        groups: dict[_GroupKey, list[DocumentMetrics]] = {}

        for dm in document_metrics:
            profile = profile_by_document_id.get(dm.document_id)
            if profile is None:
                key = _GroupKey("unknown", "unknown", "unknown", "unknown")
            else:
                key = _GroupKey(
                    profile.policy_id,
                    profile.policy_version,
                    profile.document_type,
                    profile.quality_bin,
                )
            groups.setdefault(key, []).append(dm)

        now = datetime.now(timezone.utc)
        records: list[PolicyPerformanceRecord] = []

        for key, metrics in groups.items():
            field_total = sum(m.field_total for m in metrics)
            missing_rate = (
                round(sum(m.missing_expected_field_count for m in metrics) / field_total, 6)
                if field_total > 0
                else None
            )
            correction_rate = (
                round(sum(m.corrected_field_count for m in metrics) / field_total, 6)
                if field_total > 0
                else None
            )
            records.append(
                PolicyPerformanceRecord(
                    policy_id=key.policy_id,
                    policy_version=key.policy_version,
                    document_type=key.document_type,
                    quality_bin=key.quality_bin,
                    document_count=len(metrics),
                    field_accuracy=_avg([m.field_accuracy for m in metrics]),
                    field_precision=_avg([m.field_precision for m in metrics]),
                    field_recall=_avg([m.field_recall for m in metrics]),
                    field_f1=_avg([m.field_f1 for m in metrics]),
                    missing_rate=missing_rate,
                    correction_rate=correction_rate,
                    evaluated_at=now,
                )
            )

        return records
