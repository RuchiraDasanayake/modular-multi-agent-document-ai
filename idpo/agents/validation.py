"""Entity validation agent for verifying extracted data quality."""

from __future__ import annotations

import re
import time
from typing import Any

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, StageSignal, ValidationIssue

class ValidationAgent(Agent):
    name = "validation"
    version = "v1"
    input_contract = {"document": "Document", "entities": "list", "stage": "str"}
    output_contract = {
        "issues": "list",
        "normalized": "dict",
        "confidence": "dict",
        "signal": "StageSignal",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        entities: list[Entity] = payload.get("entities", [])
        stage: str = payload.get("stage", "initial")
        issues: list[ValidationIssue] = []
        normalized: dict[str, str] = {}
        confidences: dict[str, float] = {}

        rules = ctx.config.validation.rules
        for entity in entities:
            confidences[entity.key] = max(confidences.get(entity.key, 0.0), entity.confidence)
            rule = self._match_rule(entity.key, rules)
            normalized_value = self._normalize(entity.value, rule.normalize if rule else "strip")
            normalized[entity.key] = normalized_value

            if not normalized_value:
                issues.append(
                    ValidationIssue(
                        field=entity.key,
                        issue="empty_value",
                        severity="high",
                    )
                )
                confidences[entity.key] = max(confidences[entity.key] - 0.2, 0.1)
                continue

            if rule and rule.value_pattern:
                if not re.match(rule.value_pattern, normalized_value):
                    issues.append(
                        ValidationIssue(
                            field=entity.key,
                            issue="pattern_mismatch",
                            severity=rule.severity,
                            details={"value": entity.value, "pattern": rule.value_pattern},
                        )
                    )
                    confidences[entity.key] = max(confidences[entity.key] - 0.15, 0.1)

        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_validation_{stage}.json",
            {
                "issues": [issue.__dict__ for issue in issues],
                "normalized": normalized,
                "confidence": confidences,
            },
            kind="validation",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version, "stage": stage},
        )
        confidence_score = sum(confidences.values()) / len(confidences) if confidences else 0.4

        # Categorize entities by confidence tier
        confirmed_entities = [k for k, c in confidences.items() if c >= 0.55]
        low_confidence_entities = [k for k, c in confidences.items() if 0.30 <= c < 0.55]
        rejected_entities = [k for k, c in confidences.items() if c < 0.30]

        signal = StageSignal(
            stage=self.name,
            confidence=confidence_score,
            uncertainty=1.0 - confidence_score,
            metadata={
                "issue_count": len(issues),
                "confirmed_count": len(confirmed_entities),
                "low_confidence_count": len(low_confidence_entities),
                "rejected_count": len(rejected_entities),
                "calibration": {
                    "enabled": ctx.config.calibration.enabled,
                    "method": ctx.config.calibration.method,
                    "version": ctx.config.calibration.version,
                },
            },
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"issue_count": len(issues), "artifact_id": artifact.artifact_id},
            parameters={"min_confidence": ctx.config.validation.min_confidence},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
            event_type="ValidationResult",
        )
        return AgentResult(
            artifacts={
                "validation_issues": issues,
                "normalized_entities": normalized,
                "field_confidence": confidences,
                "signal": signal,
                "validation_artifact": artifact,
                "entity_tiers": {
                    "confirmed": confirmed_entities,
                    "low_confidence": low_confidence_entities,
                    "rejected": rejected_entities,
                },
            }
        )

    def _match_rule(self, field: str, rules: List) -> Any:
        for rule in rules:
            if re.match(rule.field_pattern, field):
                return rule
        return None

    def _normalize(self, value: str, mode: str) -> str:
        text = value.strip()
        if mode == "strip":
            return text
        if mode == "numeric":
            return re.sub(r"[^\d.]", "", text)
        return text
