"""Entity extraction, sectioning, and document summarization agents."""

from __future__ import annotations

import re
import time

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
        entities: list[Entity] = []
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

    def _generic_kv_entities(self, doc: Document) -> list[Entity]:
        entities: list[Entity] = []
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
        sections: list[Section] = []
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
        full_text = "\n".join(page.text for page in doc.pages)

        # Pre-process: join broken lines into proper sentences
        # Replace single newlines (not paragraph breaks) with spaces
        cleaned_text = re.sub(r'(?<!\n)\n(?!\n)', ' ', full_text)
        # Collapse multiple spaces
        cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)
        # Remove bullet markers
        cleaned_text = re.sub(r'[○●■□▪▸►▶•]', '', cleaned_text)

        # Extract meaningful sentences
        sentences = []
        for s in re.split(r'(?<=[.!?])\s+', cleaned_text):
            s = s.strip()
            if len(s) > 20 and len(s.split()) >= 4:
                sentences.append(s)

        if not sentences:
            # Fallback: split by periods
            sentences = [s.strip() for s in full_text.split(".") if len(s.strip()) > 15]

        # Use extractive summarization: pick the most informative sentences
        # using a simple TF-IDF-like scoring approach
        summary_sentences = self._extract_key_sentences(sentences, max_sentences=5)
        summary = " ".join(summary_sentences).strip()

        # Truncate if too long but preserve complete sentences
        if len(summary) > 800:
            truncated = summary[:800]
            last_period = truncated.rfind(".")
            if last_period > 400:
                summary = truncated[:last_period + 1]

        artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_summary.txt",
            summary,
            kind="summary",
            raw=False,
            metadata={"doc_id": doc.doc_id, "agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if summary else 0.3,
            uncertainty=0.3 if summary else 0.7,
            metadata={"summary_length": len(summary), "sentence_count": len(summary_sentences)},
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

    def _extract_key_sentences(self, sentences: list, max_sentences: int = 5) -> list:
        """Pick the most informative sentences using word frequency scoring."""
        if len(sentences) <= max_sentences:
            return sentences

        # Build word frequency map (excluding stop words)
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "need", "dare", "ought",
            "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "but", "and", "or", "nor", "not", "so", "yet",
            "both", "either", "neither", "each", "every", "all", "any", "few",
            "more", "most", "other", "some", "such", "no", "only", "own", "same",
            "than", "too", "very", "just", "because", "if", "when", "where",
            "how", "what", "which", "who", "whom", "this", "that", "these",
            "those", "it", "its", "he", "she", "they", "we", "you", "i", "me",
            "my", "your", "his", "her", "our", "their",
        }
        word_freq: dict = {}
        for sentence in sentences:
            words = re.findall(r'\b[a-z]{3,}\b', sentence.lower())
            for word in words:
                if word not in stop_words:
                    word_freq[word] = word_freq.get(word, 0) + 1

        # Score each sentence
        scored = []
        for i, sentence in enumerate(sentences):
            words = re.findall(r'\b[a-z]{3,}\b', sentence.lower())
            if not words:
                scored.append((0.0, i, sentence))
                continue
            score = sum(word_freq.get(w, 0) for w in words if w not in stop_words) / len(words)
            # Boost early sentences (they often contain key information)
            position_boost = 1.0 + max(0, (5 - i) * 0.1)
            scored.append((score * position_boost, i, sentence))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = sorted(scored[:max_sentences], key=lambda x: x[1])  # preserve order
        return [s[2] for s in selected]

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
