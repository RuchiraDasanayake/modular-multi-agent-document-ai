from __future__ import annotations

import re
import time
from typing import Any, Dict, List

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
        "field_details": "dict",
        "signal": "StageSignal",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        entities: List[Entity] = payload.get("entities", [])
        stage: str = payload.get("stage", "initial")
        issues: List[ValidationIssue] = []
        normalized: Dict[str, str] = {}
        confidences: Dict[str, float] = {}
        field_details: Dict[str, Dict[str, Any]] = {}
        min_conf_input = payload.get("min_confidence")
        min_conf = float(ctx.config.validation.min_confidence if min_conf_input is None else min_conf_input)

        rules = ctx.config.validation.rules
        for entity in entities:
            confidences[entity.key] = max(confidences.get(entity.key, 0.0), entity.confidence)
            rule = self._match_rule(entity.key, rules)
            normalized_value = self._normalize(entity.value, rule.normalize if rule else "strip")
            normalized[entity.key] = normalized_value
            field_details[entity.key] = {
                "confidence": entity.confidence,
                "confidence_type": entity.confidence_type,
                "extraction_method": entity.extraction_method,
                "span": entity.span,
                "page": entity.page,
            }

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

            if entity.confidence < min_conf:
                issues.append(
                    ValidationIssue(
                        field=entity.key,
                        issue="low_confidence",
                        severity="medium",
                        details={"confidence": entity.confidence, "min_confidence": min_conf},
                    )
                )

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
                "field_details": field_details,
            },
            kind="validation",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version, "stage": stage},
        )
        confidence_score = sum(confidences.values()) / len(confidences) if confidences else 0.4
        signal = StageSignal(
            stage=self.name,
            confidence=confidence_score,
            uncertainty=1.0 - confidence_score,
            metadata={
                "issue_count": len(issues),
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
                "field_details": field_details,
                "signal": signal,
                "validation_artifact": artifact,
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
