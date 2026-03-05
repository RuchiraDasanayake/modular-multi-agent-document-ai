"""Document categorization agent for classifying document type and category."""

from __future__ import annotations

import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, StageSignal

class CategorizationAgent(Agent):
    name = "categorization"
    version = "v1"
    input_contract = {"document": "Document", "analysis": "dict|None"}
    output_contract = {"doc_type": "str", "category": "str", "bin": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        analysis = payload.get("analysis", {})
        doc_type = self._doc_type(doc, analysis)
        category = self._category(doc, analysis)
        bin_name = self._bin(category, doc.metadata.get("domain"))

        doc.metadata["doc_type"] = doc_type
        doc.metadata["category"] = category
        doc.metadata["bin"] = bin_name

        signal = StageSignal(
            stage=self.name,
            confidence=0.7,
            uncertainty=0.3,
            metadata={"doc_type": doc_type, "category": category, "bin": bin_name},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"doc_type": doc_type, "category": category, "bin": bin_name},
            parameters={},
            started=started,
        )
        return AgentResult(artifacts={"doc_type": doc_type, "category": category, "bin": bin_name, "signal": signal})

    def _doc_type(self, doc: Document, analysis: dict) -> str:
        profile = analysis.get("profile") or doc.profile or ""
        if "table" in profile:
            return "table_document"
        if "form" in profile:
            return "form_document"
        if doc.source == "scanned":
            return "scanned_document"
        return "text_document"

    def _category(self, doc: Document, analysis: dict) -> str:
        profile = analysis.get("profile") or doc.profile or ""
        if doc.source == "scanned" or profile == "image-heavy":
            return "scanned"
        if "table" in profile:
            return "table"
        if "form" in profile:
            return "form"
        return "text"

    def _bin(self, category: str, domain: str | None) -> str:
        base = category or "unknown"
        if domain:
            return f"{base}:{domain}"
        return base
