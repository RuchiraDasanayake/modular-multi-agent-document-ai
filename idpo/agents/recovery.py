from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from idpo.agents.base import Agent, AgentContext
from idpo.agents.preprocess import mock_ocr
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, StageSignal, ValidationIssue


class RecoveryAgent(Agent):
    name = "recovery"
    version = "v2"
    input_contract = {
        "document": "Document",
        "entities": "list",
        "issues": "list",
        "failing_fields": "list|None",
        "strategy": "str|None",
        "rag_hints": "dict|None",
        "max_retries": "int|None",
    }
    output_contract = {
        "entities": "list",
        "recovered_fields": "dict",
        "failed_fields": "list",
        "retry_log": "list",
        "signal": "StageSignal",
    }

    def run(
        self,
        payload: AgentMessage,
        ctx: AgentContext,
    ) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        entities: List[Entity] = payload.get("entities", [])
        issues: List[ValidationIssue] = payload.get("issues", [])
        strategy = payload.get("strategy") or "regex"
        rag_hints = payload.get("rag_hints") if isinstance(payload.get("rag_hints"), dict) else {}
        max_retries = int(payload.get("max_retries", ctx.config.preprocessing.max_retries))

        issue_fields = [issue.field for issue in issues]
        failing_fields = payload.get("failing_fields") or issue_fields
        failing_fields = [field for field in failing_fields if field]

        raw_text = "\n".join((page.raw_text or page.text) for page in doc.pages)
        updated_entities = {entity.key: entity for entity in entities}
        recovered_fields: Dict[str, str] = {}
        retry_log: List[Dict[str, object]] = []
        failed_fields: List[str] = []

        for field in failing_fields:
            if field in recovered_fields:
                continue
            found_value = None
            attempts = self._retry_sequence(strategy, max_retries)
            for attempt_idx, attempt_strategy in enumerate(attempts, start=1):
                candidate_text = raw_text
                if attempt_strategy == "alternate_ocr":
                    candidate_text = mock_ocr(raw_text, passes=2)
                pattern = self._pattern_for_field(field, attempt_strategy, rag_hints)
                match = re.search(pattern, candidate_text, re.IGNORECASE)
                log_item = {
                    "field": field,
                    "attempt": attempt_idx,
                    "strategy": attempt_strategy,
                    "pattern": pattern,
                    "success": bool(match),
                }
                retry_log.append(log_item)
                if not match:
                    continue
                found_value = match.group(1).strip()
                span = match.span(1)
                updated_entities[field] = Entity(
                    key=field,
                    value=found_value,
                    confidence=0.66,
                    confidence_type="heuristic",
                    extraction_method="rule_based",
                    span=span,
                    metadata={
                        "recovered": True,
                        "pattern": pattern,
                        "strategy": attempt_strategy,
                    },
                )
                recovered_fields[field] = found_value
                break
            if not found_value:
                failed_fields.append(field)

        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_recovery.json",
            {
                "failing_fields": failing_fields,
                "recovered_fields": recovered_fields,
                "failed_fields": failed_fields,
                "retry_log": retry_log,
            },
            kind="recovery",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if recovered_fields else 0.35,
            uncertainty=0.3 if recovered_fields else 0.65,
            metadata={"recovered_count": len(recovered_fields), "failed_count": len(failed_fields)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues), "failing_fields": failing_fields},
            outputs={"recovered": list(recovered_fields.keys()), "failed": failed_fields, "artifact_id": artifact.artifact_id},
            parameters={"max_retries": max_retries, "strategy": strategy},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
            event_type="RecoveryAction",
        )
        return AgentResult(
            artifacts={
                "entities": list(updated_entities.values()),
                "recovered_fields": recovered_fields,
                "failed_fields": failed_fields,
                "retry_log": retry_log,
                "signal": signal,
                "recovery_artifact": artifact,
            }
        )

    def _retry_sequence(self, strategy: str, max_retries: int) -> List[str]:
        options = [strategy, "alternate_ocr", "alternate_rules"]
        ordered = []
        for item in options:
            if item not in ordered:
                ordered.append(item)
        return ordered[: max(1, max_retries)]

    def _pattern_for_field(self, field: str, strategy: Optional[str], rag_hints: Dict[str, object]) -> str:
        label = field.replace("_", " ")
        aliases = rag_hints.get(field) if isinstance(rag_hints.get(field), list) else []
        if aliases:
            joined = "|".join(re.escape(str(item)) for item in [label] + [str(item) for item in aliases])
        else:
            joined = re.escape(label)
        if strategy == "alternate_rules":
            return rf"(?:{joined})\s*[:=\-]\s*(.+)"
        return rf"(?:{joined})[:\s]+(.+)"
