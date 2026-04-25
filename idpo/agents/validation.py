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

        doc_text = "\n".join(page.text for page in doc.pages if page.text).lower()

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

            grounding_issue = self._grounding_issue(entity.key, str(entity.value or ""), doc_text)
            if grounding_issue:
                issues.append(grounding_issue)
                confidences[entity.key] = max(
                    confidences[entity.key] - self._severity_penalty(grounding_issue.severity),
                    0.1,
                )
                meta = entity.metadata if isinstance(entity.metadata, dict) else {}
                meta["ungrounded"] = True

        arithmetic_issues = self._check_receipt_arithmetic(normalized)
        for issue in arithmetic_issues:
            issues.append(issue)
            confidences[issue.field] = max(confidences.get(issue.field, 0.5) - 0.25, 0.1)

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
        _DATE_PATTERNS = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}",
            r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}",
            r"\d{1,2}[\s\-]+[A-Za-z]{3,9}[\s\-]+\d{2,4}",
            r"[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}",
            r"[A-Za-z]{3,9}\s+\d{4}",
        ]
        for pattern in _DATE_PATTERNS:
            if re.fullmatch(pattern, text, re.IGNORECASE):
                return True
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
            try:
                datetime.strptime(text, fmt)
                return True
            except Exception:
                pass
        return False

    def _looks_like_amount(self, value: str) -> bool:
        # Accept: 70,000 / 379.500 / 1,234.56 / -50 / 6.000 (dot-thousands)
        text = value.strip().lstrip("-").replace(",", "").replace(".", "")
        return bool(text) and text.isdigit()

    def _looks_like_phone(self, value: str) -> bool:
        digits = re.sub(r"\D", "", value)
        return len(digits) >= 10

    def _grounding_issue(self, field: str, value: str, doc_text_lower: str) -> ValidationIssue | None:
        """Flag values that do not appear in the source document — likely hallucinated."""
        if not value or not doc_text_lower:
            return None
        # Short tokens (≤3 chars) are too common to reliably ground
        tokens = [t for t in re.split(r"[\s,.\-/]+", value.lower()) if len(t) > 3]
        if not tokens:
            return None
        # Pass if ANY meaningful token appears in the document text
        if any(token in doc_text_lower for token in tokens):
            return None
        return ValidationIssue(
            field=field,
            issue="ungrounded_value",
            severity="high",
            details={"value": value[:120]},
        )

    def _check_receipt_arithmetic(self, normalized: dict[str, str]) -> list[ValidationIssue]:
        """Check that total = subtotal + tax (5% tolerance). Catches per-field swap errors."""
        issues: list[ValidationIssue] = []
        amount_fields = {
            "total": None, "total_amount": None, "subtotal": None, "subtotal_amount": None,
            "tax": None, "tax_amount": None,
        }
        for field in amount_fields:
            raw = normalized.get(field, "")
            if raw:
                try:
                    amount_fields[field] = float(raw.replace(",", ""))
                except ValueError:
                    pass
        total = amount_fields.get("total") or amount_fields.get("total_amount")
        subtotal = amount_fields.get("subtotal") or amount_fields.get("subtotal_amount")
        tax = amount_fields.get("tax") or amount_fields.get("tax_amount")
        if total is not None and subtotal is not None and tax is not None and total > 0:
            expected = subtotal + tax
            if abs(expected - total) / total > 0.05:
                issues.append(ValidationIssue(
                    field="total_amount",
                    issue="arithmetic_inconsistency",
                    severity="high",
                    details={"total": total, "subtotal": subtotal, "tax": tax, "expected_total": round(expected, 2)},
                ))
        return issues

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
