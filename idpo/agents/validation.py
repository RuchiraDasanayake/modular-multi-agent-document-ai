"""Entity validation agent for verifying extracted data quality."""

from __future__ import annotations

import re
import time
from datetime import datetime
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
            normalize_mode = rule.normalize if rule else self._default_normalize_mode(entity.key)
            normalized_value = self._normalize(entity.value, normalize_mode)
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
                if not re.fullmatch(rule.value_pattern, normalized_value):
                    issues.append(
                        ValidationIssue(
                            field=entity.key,
                            issue="pattern_mismatch",
                            severity=rule.severity,
                            details={"value": entity.value, "pattern": rule.value_pattern},
                        )
                    )
                    confidences[entity.key] = max(
                        confidences[entity.key] - self._severity_penalty(rule.severity),
                        0.1,
                    )

            semantic_issue = self._semantic_issue(entity.key, normalized_value)
            if semantic_issue:
                issues.append(semantic_issue)
                confidences[entity.key] = max(
                    confidences[entity.key] - self._severity_penalty(semantic_issue.severity),
                    0.1,
                )

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
        min_conf = max(0.0, min(1.0, ctx.config.validation.min_confidence))
        low_conf_min = max(0.3, min_conf - 0.25)
        confirmed_entities = [k for k, c in confidences.items() if c >= min_conf]
        low_confidence_entities = [k for k, c in confidences.items() if low_conf_min <= c < min_conf]
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

    def _match_rule(self, field: str, rules: list[Any]) -> Any:
        for rule in rules:
            if re.match(rule.field_pattern, field):
                return rule
        return None

    def _default_normalize_mode(self, field: str) -> str:
        lowered = field.lower()
        if "amount" in lowered or "total" in lowered or lowered.endswith("_price"):
            return "numeric"
        if "date" in lowered:
            return "date"
        if lowered.endswith("_id") or lowered.endswith("_number"):
            return "upper"
        return "strip"

    def _severity_penalty(self, severity: str) -> float:
        level = (severity or "").lower()
        if level == "high":
            return 0.2
        if level == "low":
            return 0.08
        return 0.15

    def _semantic_issue(self, field: str, value: str) -> ValidationIssue | None:
        lowered = field.lower()
        if "date" in lowered and not self._looks_like_date(value):
            return ValidationIssue(
                field=field,
                issue="semantic_date_mismatch",
                severity="medium",
                details={"value": value},
            )
        if ("amount" in lowered or "total" in lowered) and not self._looks_like_amount(value):
            return ValidationIssue(
                field=field,
                issue="semantic_amount_mismatch",
                severity="medium",
                details={"value": value},
            )
        if ("phone" in lowered or "fax" in lowered or "tel" in lowered) and not self._looks_like_phone(value):
            return ValidationIssue(
                field=field,
                issue="semantic_phone_mismatch",
                severity="low",
                details={"value": value},
            )
        return None

    def _looks_like_date(self, value: str) -> bool:
        text = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return True
        if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text):
            return True
        try:
            datetime.strptime(text, "%b %d, %Y")
            return True
        except Exception:
            pass
        try:
            datetime.strptime(text, "%B %d, %Y")
            return True
        except Exception:
            return False

    def _looks_like_amount(self, value: str) -> bool:
        return bool(re.fullmatch(r"-?\d+(?:\.\d{1,2})?", value.strip()))

    def _looks_like_phone(self, value: str) -> bool:
        digits = re.sub(r"\D", "", value)
        return len(digits) >= 10

    def _normalize(self, value: str, mode: str) -> str:
        text = value.strip()
        if mode == "strip":
            return text
        if mode == "numeric":
            compact = text.replace(",", "")
            compact = re.sub(r"[^\d.\-]", "", compact)
            compact = re.sub(r"(?<!^)-", "", compact)
            return compact
        if mode == "upper":
            return re.sub(r"\s+", "", text).upper()
        if mode == "date":
            cleaned = text.strip()
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%b %d, %Y", "%B %d, %Y"):
                try:
                    return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
                except Exception:
                    continue
            return cleaned
        return text
