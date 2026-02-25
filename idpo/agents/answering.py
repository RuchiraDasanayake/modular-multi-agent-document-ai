from __future__ import annotations

import re
import time
from typing import Dict, List, Optional

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Answer, Chunk, Entity, StageSignal


class AnsweringAgent(Agent):
    name = "answering"
    version = "v1"
    input_contract = {"question": "str", "context_chunks": "list", "entities": "list", "signals": "list"}
    output_contract = {"answer": "Answer", "signal": "StageSignal"}

    def run(
        self,
        payload: AgentMessage,
        ctx: AgentContext,
    ) -> AgentResult:
        started = time.time()
        question: str = payload["question"]
        context_chunks: List[Chunk] = payload.get("context_chunks", [])
        entities: List[Entity] = payload.get("entities", [])
        signals = payload.get("signals", [])
        min_confidence = payload.get("min_confidence", 0.55)

        answer_text, base_conf = self._answer_from_entities(question, entities)
        citations = self._build_citations(context_chunks, answer_text)
        confidence = base_conf
        if signals:
            signal_values = [signal.confidence for signal in signals if signal]
            if signal_values:
                confidence = min(confidence, min(signal_values))
        abstained = confidence < min_confidence or not citations
        if abstained:
            answer_text = "Insufficient evidence in retrieved context."
            confidence = min(confidence, 0.2)

        answer = Answer(
            question=question,
            answer=answer_text,
            citations=citations,
            confidence=confidence,
            abstained=abstained,
        )
        answer_artifact = ctx.artifact_store.save_json(
            f"answer_{ctx.run_id}.json",
            answer.__dict__,
            kind="answer",
            raw=False,
            metadata={"agent": self.name, "version": self.version},
        )
        signal = StageSignal(
            stage=self.name,
            confidence=confidence,
            uncertainty=1.0 - confidence,
            failure_reason="low_confidence" if abstained else None,
        )
        self._record(
            ctx,
            inputs={"question": question},
            outputs={"confidence": confidence, "abstained": abstained, "citations": citations},
            parameters={},
            artifacts=[answer_artifact.artifact_id],
            output_artifacts=[answer_artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"answer": answer, "signal": signal, "answer_artifact": answer_artifact})

    def _answer_from_entities(self, question: str, entities: List[Entity]) -> tuple[str, float]:
        q = question.lower()
        best = ("", 0.0)
        for entity in entities:
            labels = [entity.key.replace("_", " ")]
            label = entity.metadata.get("label")
            if label:
                labels.append(str(label))
            score = 0.0
            for label_item in labels:
                label_tokens = [token for token in label_item.lower().split() if token]
                if all(token in q for token in label_tokens):
                    score = max(score, 0.6 + entity.confidence * 0.4)
            if score > best[1]:
                best = (entity.value, score)
        return best

    def _build_citations(self, chunks: List[Chunk], answer_text: str) -> List[Dict[str, str]]:
        citations = []
        for chunk in chunks[:3]:
            if answer_text and answer_text not in chunk.text:
                continue
            snippet = self._snippet(chunk.text, answer_text)
            citations.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "page_range": f"{chunk.page_range[0]}-{chunk.page_range[1]}",
                    "section": chunk.section or "",
                    "snippet": snippet,
                }
            )
        if not citations and chunks:
            chunk = chunks[0]
            citations.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "page_range": f"{chunk.page_range[0]}-{chunk.page_range[1]}",
                    "section": chunk.section or "",
                    "snippet": self._snippet(chunk.text, ""),
                }
            )
        return citations

    def _snippet(self, text: str, answer: str) -> str:
        if not answer:
            return text[:160]
        idx = text.find(answer)
        if idx == -1:
            return text[:160]
        start = max(idx - 60, 0)
        end = min(idx + 100, len(text))
        return text[start:end]
