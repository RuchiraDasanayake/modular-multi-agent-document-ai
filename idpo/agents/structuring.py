from __future__ import annotations

import re
import time
from typing import List

from idpo.agents.base import Agent, AgentContext
from idpo.agents.llm_extraction import LLMExtractionAgent
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Entity, Section, StageSignal


class EntityExtractionAgent(Agent):
    name = "entity_extraction"
    version = "v1"
    input_contract = {"document": "Document"}
    output_contract = {"entities": "list", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        entities: List[Entity] = []
        full_text = "\n".join(page.text for page in doc.pages)

        rules = ctx.config.structuring.extraction_rules
        for rule in rules:
            match = re.search(rule.pattern, full_text, re.IGNORECASE)
            if match:
                entities.append(
                    Entity(
                        key=rule.key,
                        value=match.group(1).strip(),
                        confidence=0.82,
                        metadata={"pattern": rule.pattern, "label": rule.label},
                    )
                )

        if ctx.config.structuring.allow_generic_kv:
            entities.extend(self._generic_kv_entities(doc))

        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_entities.json",
            {"entities": [entity.__dict__ for entity in entities]},
            kind="entities",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if entities else 0.4,
            uncertainty=0.3 if entities else 0.6,
            metadata={"entity_count": len(entities)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"entity_count": len(entities), "artifact_id": artifact.artifact_id},
            parameters={"rule_count": len(rules), "generic_kv": ctx.config.structuring.allow_generic_kv},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"entities": entities, "entities_artifact": artifact, "signal": signal})

    def _generic_kv_entities(self, doc: Document) -> List[Entity]:
        entities: List[Entity] = []
        lines = []
        for page in doc.pages:
            lines.extend(page.text.splitlines())
        for line in lines:
            if ":" not in line:
                continue
            key_part, value_part = line.split(":", 1)
            key = key_part.strip().lower().replace(" ", "_")
            value = value_part.strip()
            if not key or not value:
                continue
            entities.append(
                Entity(
                    key=key,
                    value=value,
                    confidence=0.55,
                    metadata={"generic_kv": True},
                )
            )
        return entities


class SectioningAgent(Agent):
    name = "sectioning"
    version = "v1"
    input_contract = {"document": "Document"}
    output_contract = {"sections": "list", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        sections: List[Section] = []
        current = {"name": "section_1", "text": []}
        max_words = ctx.config.structuring.heading_max_words

        for page in doc.pages:
            for line in page.text.splitlines():
                if self._is_heading(line, max_words):
                    if current["text"]:
                        sections.append(
                            Section(
                                name=current["name"],
                                text="\n".join(current["text"]).strip(),
                                page_start=page.number,
                                page_end=page.number,
                                confidence=0.7,
                            )
                        )
                    current = {"name": self._normalize_heading(line), "text": []}
                else:
                    current["text"].append(line)
        if current["text"]:
            sections.append(
                Section(
                    name=current["name"],
                    text="\n".join(current["text"]).strip(),
                    page_start=doc.pages[0].number if doc.pages else 1,
                    page_end=doc.pages[-1].number if doc.pages else 1,
                    confidence=0.6,
                )
            )
        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_sections.json",
            {"sections": [section.__dict__ for section in sections]},
            kind="sections",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if sections else 0.4,
            uncertainty=0.3 if sections else 0.6,
            metadata={"section_count": len(sections)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"section_count": len(sections), "artifact_id": artifact.artifact_id},
            parameters={},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"sections": sections, "sections_artifact": artifact, "signal": signal})

    def _is_heading(self, line: str, max_words: int) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        words = stripped.split()
        if len(words) > max_words:
            return False
        if stripped.endswith(":"):
            return True
        if stripped == stripped.title() and len(stripped) <= 40:
            return True
        upper_ratio = sum(1 for ch in stripped if ch.isupper()) / max(len(stripped), 1)
        return upper_ratio > 0.6

    def _normalize_heading(self, line: str) -> str:
        stripped = line.strip().strip(":").lower()
        key = re.sub(r"[^a-z0-9]+", "_", stripped).strip("_")
        return key or "section"


class ClassificationAgent(Agent):
    name = "classification"
    version = "v1"
    input_contract = {"document": "Document", "analysis": "dict"}
    output_contract = {"doc_type": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        analysis = payload.get("analysis", {})
        doc_type = "text_document"
        profile = analysis.get("profile") or doc.profile or ""
        if "table" in profile:
            doc_type = "table_document"
        elif "form" in profile:
            doc_type = "form_document"
        elif doc.source == "scanned":
            doc_type = "scanned_document"
        doc.metadata["doc_type"] = doc_type

        signal = StageSignal(stage=self.name, confidence=0.65, uncertainty=0.35, metadata={"doc_type": doc_type})
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"doc_type": doc_type},
            parameters={},
            started=started,
        )
        return AgentResult(artifacts={"doc_type": doc_type, "signal": signal})


class SummarizationAgent(Agent):
    name = "summarization"
    version = "v1"
    input_contract = {"document": "Document"}
    output_contract = {"summary": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        sentences = []
        for page in doc.pages:
            sentences.extend([s.strip() for s in page.text.split(".") if s.strip()])
        summary = ". ".join(sentences[:3]).strip()
        artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_summary.txt",
            summary,
            kind="summary",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.6 if summary else 0.3,
            uncertainty=0.4 if summary else 0.7,
            metadata={"summary_length": len(summary)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"summary_length": len(summary), "artifact_id": artifact.artifact_id},
            parameters={},
            artifacts=[artifact.artifact_id],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"summary": summary, "summary_artifact": artifact, "signal": signal})


class StructuringRouter(Agent):
    name = "structuring_router"
    version = "v1"
    input_contract = {
        "document": "Document",
        "analysis": "dict",
        "policy": "ExtractionPolicy|None",
        "model": "ModelDecision|None",
        "input_artifact_id": "str|None",
    }
    output_contract = {
        "entities": "list",
        "explicit_entities": "list",
        "default_entities": "list",
        "sections": "list",
        "summary": "str",
        "signals": "list",
    }

    def __init__(self) -> None:
        self.entity = LLMExtractionAgent()
        self.section = SectioningAgent()
        self.summary = SummarizationAgent()

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        analysis = payload.get("analysis", {})
        result = AgentResult()
        signals = []
        policy = payload.get("policy")
        model = payload.get("model")
        input_artifact_id = payload.get("input_artifact_id")
        entity_result = self.entity.run(
            {"document": doc, "policy": policy, "model": model, "input_artifact_id": input_artifact_id},
            ctx,
        )
        result = result.merge(entity_result)
        signals.append(entity_result.artifacts.get("signal"))
        section_result = self.section.run({"document": doc}, ctx)
        result = result.merge(section_result)
        signals.append(section_result.artifacts.get("signal"))
        summary_result = self.summary.run({"document": doc}, ctx)
        result = result.merge(summary_result)
        signals.append(summary_result.artifacts.get("signal"))

        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={
                "explicit_entities": len(entity_result.artifacts.get("explicit_entities", [])),
                "default_entities": len(entity_result.artifacts.get("default_entities", [])),
            },
            parameters={"policy_id": policy.policy_id if policy else None},
            started=started,
        )
        result.artifacts["signals"] = [signal for signal in signals if signal]
        return result
