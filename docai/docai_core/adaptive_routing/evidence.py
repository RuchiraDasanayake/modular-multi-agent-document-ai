"""Evidence collection for Review-Based Adaptive Routing.

Only reviewed learning samples are counted as evidence.
No automatic learning or mutation is performed here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SUCCESS_DECISIONS = {"correct", "correctly_skipped"}
FAILURE_DECISIONS = {"wrong_value", "missed_field", "hallucinated_field"}
VALID_DECISIONS = SUCCESS_DECISIONS | FAILURE_DECISIONS


@dataclass(slots=True)
class EvidenceSample:
    schema_id: str | None
    field_name: str
    decision: str
    created_at: datetime | None


@dataclass(slots=True)
class FieldArmEvidence:
    """Aggregated evidence for one schema+field arm."""

    arm_id: str
    schema_id: str | None
    field_name: str
    successes: int = 0
    failures: int = 0
    samples: list[EvidenceSample] = field(default_factory=list)

    @property
    def total_samples(self) -> int:
        return self.successes + self.failures

    @property
    def correction_rate(self) -> float:
        if self.total_samples == 0:
            return 0.0
        return self.failures / self.total_samples


@dataclass(slots=True)
class ProjectEvidence:
    project_id: str
    arms: dict[str, FieldArmEvidence] = field(default_factory=dict)
    reviewed_sample_count: int = 0

    def add_sample(self, sample: EvidenceSample) -> None:
        arm_id = f"{sample.schema_id}:{sample.field_name}" if sample.schema_id else sample.field_name
        arm = self.arms.get(arm_id)
        if arm is None:
            arm = FieldArmEvidence(
                arm_id=arm_id,
                schema_id=sample.schema_id,
                field_name=sample.field_name,
            )
            self.arms[arm_id] = arm

        if sample.decision in SUCCESS_DECISIONS:
            arm.successes += 1
        elif sample.decision in FAILURE_DECISIONS:
            arm.failures += 1
        else:
            return

        arm.samples.append(sample)
        self.reviewed_sample_count += 1


def parse_sample_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def collect_evidence_from_samples(project_id: str, learning_samples: list[dict[str, Any]]) -> ProjectEvidence:
    """Build project evidence from review-derived learning samples."""

    evidence = ProjectEvidence(project_id=project_id)
    for row in learning_samples:
        field_name = str(row.get("field_name", "")).strip()
        decision = str(row.get("decision", "")).strip()
        if not field_name or decision not in VALID_DECISIONS:
            continue

        sample = EvidenceSample(
            schema_id=row.get("schema_id"),
            field_name=field_name,
            decision=decision,
            created_at=parse_sample_timestamp(row.get("created_at")),
        )
        evidence.add_sample(sample)

    return evidence

