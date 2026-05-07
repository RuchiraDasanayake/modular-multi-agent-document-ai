"""Error recovery agent — re-extracts failed fields via LLM."""

from __future__ import annotations

import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, StageSignal, ValidationIssue


_RECOVERABLE_TAGS = {"missing_field", "empty_value", "pattern_mismatch", "low_confidence"}


class RecoveryAgent(Agent):
    name = "recovery"
    version = "v2"
    input_contract = {"document": "Document", "entities": "list", "issues": "list"}
    output_contract = {"entities": "list", "recovered_fields": "dict", "recovery_trace": "list", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        entities: list[Entity] = payload.get("entities", [])
        issues: list[ValidationIssue] = payload.get("issues", [])

        failing_fields = list(dict.fromkeys(
            issue.field for issue in issues
            if issue.field and self._is_recoverable(issue)
        ))

        updated_entities = {entity.key: entity for entity in entities}
        recovered_fields: dict[str, str] = {}
        recovery_trace: list[dict[str, object]] = []

        if failing_fields:
            new_entities = self._llm_recover(doc, failing_fields, ctx, recovery_trace)
            recovery_confidence = float(
                getattr(getattr(ctx.config, "recovery", object()), "confidence", ctx.config.preprocessing.recovery_confidence)
            )
            for entity in new_entities:
                if entity.key in failing_fields and str(entity.value or "").strip():
                    updated_entities[entity.key] = Entity(
                        key=entity.key,
                        value=entity.value,
                        confidence=min(entity.confidence, recovery_confidence),
                        metadata={**(entity.metadata or {}), "recovered": True, "source": "llm_recovery"},
                    )
                    recovered_fields[entity.key] = str(entity.value)

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
            metadata={"recovered_count": len(recovered_fields), "attempt_count": len(failing_fields)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "issue_count": len(issues), "failing_fields": failing_fields},
            outputs={"recovered": list(recovered_fields.keys()), "artifact_id": artifact.artifact_id},
            parameters={"strategy": "llm_reextraction"},
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

    def _is_recoverable(self, issue: ValidationIssue) -> bool:
        tag = (issue.issue or "").strip().lower()
        return tag in _RECOVERABLE_TAGS or tag.startswith("semantic_")

    def _llm_recover(
        self,
        doc: Document,
        failing_fields: list[str],
        ctx: AgentContext,
        recovery_trace: list[dict[str, object]],
    ) -> list[Entity]:
        try:
            from idpo.agents.llm_extraction import LLMExtractionAgent
            agent = LLMExtractionAgent()
            result = agent.run(
                {
                    "document": doc,
                    "explicit_keys": failing_fields,
                    "field_descriptions": dict(ctx.config.structuring.field_descriptions),
                    "recovery_pass": True,
                },
                ctx,
            )
            entities: list[Entity] = result.artifacts.get("entities", [])
            recovery_trace.append({
                "strategy": "llm_reextraction",
                "fields_attempted": failing_fields,
                "fields_recovered": [e.key for e in entities if str(e.value or "").strip()],
            })
            return entities
        except Exception as exc:
            recovery_trace.append({"strategy": "llm_reextraction", "error": str(exc), "fields_attempted": failing_fields})
            return []
