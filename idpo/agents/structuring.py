"""Sectioning and summarization agents used by the active IDPO pipeline."""

from __future__ import annotations

import re
import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Section, StageSignal


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


class SummarizationAgent(Agent):
    name = "summarization"
    version = "v1"
    input_contract = {"document": "Document"}
    output_contract = {"summary": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        full_text = "\n".join(page.text for page in doc.pages)

        cleaned_text = re.sub(r"(?<!\n)\n(?!\n)", " ", full_text)
        cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)
        cleaned_text = re.sub(r"[\u25cb\u25cf\u25a0\u25a1\u25aa\u25b8\u25ba\u25b6\u2022]", "", cleaned_text)

        sentences = []
        for sentence in re.split(r"(?<=[.!?])\s+", cleaned_text):
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence.split()) >= 4:
                sentences.append(sentence)

        if not sentences:
            sentences = [sentence.strip() for sentence in full_text.split(".") if len(sentence.strip()) > 15]

        summary_sentences = self._extract_key_sentences(sentences, max_sentences=5)
        summary = " ".join(summary_sentences).strip()

        if len(summary) > 800:
            truncated = summary[:800]
            last_period = truncated.rfind(".")
            if last_period > 400:
                summary = truncated[: last_period + 1]

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

    def _extract_key_sentences(self, sentences: list[str], max_sentences: int = 5) -> list[str]:
        if len(sentences) <= max_sentences:
            return sentences

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
        word_freq: dict[str, int] = {}
        for sentence in sentences:
            words = re.findall(r"\b[a-z]{3,}\b", sentence.lower())
            for word in words:
                if word not in stop_words:
                    word_freq[word] = word_freq.get(word, 0) + 1

        scored: list[tuple[float, int, str]] = []
        for index, sentence in enumerate(sentences):
            words = re.findall(r"\b[a-z]{3,}\b", sentence.lower())
            if not words:
                scored.append((0.0, index, sentence))
                continue
            score = sum(word_freq.get(word, 0) for word in words if word not in stop_words) / len(words)
            position_boost = 1.0 + max(0, (5 - index) * 0.1)
            scored.append((score * position_boost, index, sentence))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = sorted(scored[:max_sentences], key=lambda item: item[1])
        return [item[2] for item in selected]
