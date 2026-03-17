"""Error recovery agent for re-extracting failed or low-confidence fields."""

from __future__ import annotations

import re
import time

from idpo.agents.base import Agent, AgentContext
from idpo.agents.preprocess import mock_ocr
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, StageSignal, ValidationIssue

class RecoveryAgent(Agent):
    name = "recovery"
    version = "v1"
    input_contract = {"document": "Document", "entities": "list", "issues": "list", "strategy": "str|None"}
    output_contract = {"entities": "list", "recovered_fields": "dict", "recovery_trace": "list", "signal": "StageSignal"}

    def run(
        self,
        payload: AgentMessage,
        ctx: AgentContext,
    ) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        entities: list[Entity] = payload.get("entities", [])
        issues: list[ValidationIssue] = payload.get("issues", [])
        strategy = payload.get("strategy") or "regex"

        raw_text = "\n".join((page.raw_text or page.text) for page in doc.pages)
        alternate_text = raw_text
        if strategy == "alternate_ocr":
            alternate_text = mock_ocr(raw_text, passes=2)
        updated_entities = {entity.key: entity for entity in entities}
        recovered_fields: dict[str, str] = {}
        recovery_trace: list[dict[str, object]] = []

        for issue in issues:
            if not self._is_recoverable_issue(issue):
                continue
            pattern = self._pattern_for_field(issue.field, strategy)
            match = re.search(pattern, raw_text, re.IGNORECASE) or re.search(pattern, alternate_text, re.IGNORECASE)
            before_value = updated_entities.get(issue.field).value if issue.field in updated_entities else ""
            trace = {
                "field": issue.field,
                "issue_type": issue.issue,
                "strategy": strategy,
                "before_value": before_value,
                "after_value": "",
                "success": False,
                "reason": "no_match",
            }
            if not match:
                recovery_trace.append(trace)
                continue
            value = match.group(1).strip()
            if not value:
                trace["reason"] = "empty_match"
                recovery_trace.append(trace)
                continue
            if not self._passes_validation(issue.field, value, ctx):
                trace["after_value"] = value
                trace["reason"] = "candidate_failed_validation"
                recovery_trace.append(trace)
                continue
            updated_entities[issue.field] = Entity(
                key=issue.field,
                value=value,
                confidence=ctx.config.preprocessing.recovery_confidence,
                metadata={
                    "recovered": True,
                    "pattern": pattern,
                    "strategy": strategy,
                    "validated_recovery": True,
                },
            )
            recovered_fields[issue.field] = value
            trace["after_value"] = value
            trace["success"] = True
            trace["reason"] = "recovered"
            recovery_trace.append(trace)

        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_recovery.json",
            {"recovered_fields": recovered_fields, "recovery_trace": recovery_trace},
            kind="recovery",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.65 if recovered_fields else 0.35,
            uncertainty=0.35 if recovered_fields else 0.65,
            metadata={"recovered_count": len(recovered_fields), "attempt_count": len(recovery_trace)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues)},
            outputs={
                "recovered": list(recovered_fields.keys()),
                "artifact_id": artifact.artifact_id,
                "attempt_count": len(recovery_trace),
            },
            parameters={"max_retries": ctx.config.preprocessing.max_retries, "strategy": strategy},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
            event_type="RecoveryAction",
        )
        return AgentResult(
            artifacts={
                "entities": list(updated_entities.values()),
                "recovered_fields": recovered_fields,
                "recovery_trace": recovery_trace,
                "signal": signal,
                "recovery_artifact": artifact,
            }
        )

    def _pattern_for_field(self, field: str, strategy: str | None) -> str:
        label = field.replace("_", r"[\s_]")
        if strategy == "alternate_rules":
            # More restrictive: capture only up to the next line break or common delimiter
            return rf"(?i){label}\s*[:=\-]\s*([^\n;|]+?)(?:\s*[\n;|]|$)"
        # Default: capture value after the label, stop at line break or common separators
        return rf"(?i){label}[:\s]+([^\n;|]+?)(?:\s*[\n;|]|$)"

    def _is_recoverable_issue(self, issue: ValidationIssue) -> bool:
        tag = (issue.issue or "").strip().lower()
        if not tag:
            return False
        if tag in {"missing_field", "empty_value", "pattern_mismatch", "low_confidence"}:
            return True
        if tag.startswith("semantic_"):
            return True
        return False

    def _passes_validation(self, field: str, value: str, ctx: AgentContext) -> bool:
        normalized = value.strip()
        if not normalized:
            return False

        matched_rule = None
        for rule in ctx.config.validation.rules:
            if re.match(rule.field_pattern, field):
                matched_rule = rule
                break
        if matched_rule:
            candidate = self._normalize_for_mode(normalized, matched_rule.normalize)
            if matched_rule.value_pattern and not re.fullmatch(matched_rule.value_pattern, candidate):
                return False
        return self._semantic_plausible(field, normalized)

    def _normalize_for_mode(self, value: str, mode: str) -> str:
        text = value.strip()
        if mode == "numeric":
            compact = text.replace(",", "")
            compact = re.sub(r"[^\d.\-]", "", compact)
            compact = re.sub(r"(?<!^)-", "", compact)
            return compact
        if mode == "upper":
            return re.sub(r"\s+", "", text).upper()
        return text

    def _semantic_plausible(self, field: str, value: str) -> bool:
        lowered = field.lower()
        if "date" in lowered:
            return bool(
                re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
                or re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", value)
            )
        if "amount" in lowered or "total" in lowered:
            compact = value.replace(",", "")
            compact = re.sub(r"[^\d.\-]", "", compact)
            return bool(re.fullmatch(r"-?\d+(?:\.\d{1,2})?", compact))
        return True
