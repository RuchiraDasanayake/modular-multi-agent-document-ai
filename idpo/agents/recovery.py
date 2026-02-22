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
    version = "v1"
    input_contract = {"document": "Document", "entities": "list", "issues": "list", "strategy": "str|None"}
    output_contract = {"entities": "list", "recovered_fields": "dict", "signal": "StageSignal"}

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

        raw_text = "\n".join((page.raw_text or page.text) for page in doc.pages)
        alternate_text = raw_text
        if strategy == "alternate_ocr":
            alternate_text = mock_ocr(raw_text, passes=2)
        updated_entities = {entity.key: entity for entity in entities}
        recovered_fields: Dict[str, str] = {}

        for issue in issues:
            pattern = self._pattern_for_field(issue.field, strategy)
            match = re.search(pattern, raw_text, re.IGNORECASE) or re.search(pattern, alternate_text, re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip()
            updated_entities[issue.field] = Entity(
                key=issue.field,
                value=value,
                confidence=0.6,
                metadata={"recovered": True, "pattern": pattern, "strategy": strategy},
            )
            recovered_fields[issue.field] = value

        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_recovery.json",
            {"recovered_fields": recovered_fields},
            kind="recovery",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.65 if recovered_fields else 0.35,
            uncertainty=0.35 if recovered_fields else 0.65,
            metadata={"recovered_count": len(recovered_fields)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues)},
            outputs={"recovered": list(recovered_fields.keys()), "artifact_id": artifact.artifact_id},
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
                "signal": signal,
                "recovery_artifact": artifact,
            }
        )

    def _pattern_for_field(self, field: str, strategy: Optional[str]) -> str:
        label = field.replace("_", " ")
        if strategy == "alternate_rules":
            return rf"{re.escape(label)}\s*[:=\-]\s*(.+)"
        return rf"{re.escape(label)}[:\s]+(.+)"
