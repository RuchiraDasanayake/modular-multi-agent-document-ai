"""Document analysis agent for quality assessment and complexity profiling."""

from __future__ import annotations

import re
import statistics
import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, DAEOutput, Document, StageSignal

class DocumentAnalysisAgent(Agent):
    name = "document_analysis"
    version = "v1"
    input_contract = {"document": "Document"}
    output_contract = {
        "dae_output": "DAEOutput",
        "analysis": {"quality_score": "float", "complexity_score": "float", "profile": "str"},
        "signal": "StageSignal",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        page_lengths = [len(page.text or "") for page in doc.pages]
        avg_len = statistics.mean(page_lengths) if page_lengths else 0
        non_alpha_ratio = self._non_alpha_ratio(doc)
        table_ratio = self._table_ratio(doc)
        form_ratio = self._form_ratio(doc)
        # Only treat as image-heavy if pages lack meaningful text content
        # PDFs set image_path for rendering but may still have extractable text
        has_text = any((page.text or "").strip() for page in doc.pages)
        if doc.source == "scanned" and not has_text:
            image_ratio = 1.0
        elif not has_text and any(page.image_path for page in doc.pages):
            image_ratio = 0.9
        elif has_text:
            image_ratio = 0.2
        else:
            image_ratio = 0.2

        quality_score = max(0.0, 1.0 - non_alpha_ratio)
        complexity_score = min(1.0, (table_ratio + form_ratio + image_ratio) / 3.0)

        content_profile = self._profile(table_ratio, form_ratio, image_ratio, avg_len)
        doc_type = self._doc_type(doc, content_profile)
        vendor_cluster = self._vendor_cluster(doc)
        quality_bin = self._quality_bin(quality_score)
        complexity_bin = self._complexity_bin(complexity_score)

        signals = self._signals(doc, non_alpha_ratio, table_ratio, form_ratio, image_ratio)

        doc.quality_score = quality_score
        doc.complexity_score = complexity_score
        doc.profile = content_profile
        doc.content_profile = content_profile
        doc.doc_type = doc_type
        doc.vendor_cluster = vendor_cluster
        doc.quality_bin = quality_bin
        doc.complexity_bin = complexity_bin
        doc.dae_signals = signals
        doc.metadata.update(
            {
                "doc_type": doc_type,
                "vendor_cluster": vendor_cluster,
                "quality_bin": quality_bin,
                "complexity_bin": complexity_bin,
                "content_profile": content_profile,
            }
        )

        dae_output = DAEOutput(
            doc_id=doc.doc_id,
            doc_type=doc_type,
            vendor_cluster=vendor_cluster,
            quality_bin=quality_bin,
            complexity_bin=complexity_bin,
            content_profile=content_profile,
            quality_score=quality_score,
            complexity_score=complexity_score,
            signals=signals,
        )

        signal = StageSignal(
            stage=self.name,
            confidence=quality_score,
            uncertainty=1.0 - quality_score,
            metadata={"table_ratio": table_ratio, "form_ratio": form_ratio, "quality_bin": quality_bin},
        )

        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "pages": len(doc.pages)},
            outputs={
                "quality_score": quality_score,
                "complexity_score": complexity_score,
                "profile": content_profile,
                "doc_type": doc_type,
                "vendor_cluster": vendor_cluster,
                "quality_bin": quality_bin,
                "complexity_bin": complexity_bin,
            },
            parameters={},
            started=started,
            event_type="DAEOutput",
        )
        return AgentResult(
            artifacts={
                "dae_output": dae_output,
                "analysis": {
                    "quality_score": quality_score,
                    "complexity_score": complexity_score,
                    "profile": content_profile,
                },
                "signal": signal,
            }
        )

    def _non_alpha_ratio(self, doc: Document) -> float:
        text = "\n".join(page.text for page in doc.pages if page.text)
        if not text:
            return 1.0
        non_alpha = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
        return non_alpha / max(len(text), 1)

    def _table_ratio(self, doc: Document) -> float:
        text = "\n".join(page.text for page in doc.pages if page.text)
        if not text:
            return 0.0
        lines = text.splitlines()
        if not lines:
            return 0.0
        # Count lines with table-like patterns: pipe separators, tab separators, or consistent column alignment
        table_lines = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            pipe_count = stripped.count("|")
            tab_count = stripped.count("\t")
            if pipe_count >= 2 or tab_count >= 2:
                table_lines += 1
            elif re.search(r"\s{3,}", stripped) and re.search(r"\d", stripped):
                # Lines with large whitespace gaps and numbers (column-aligned data)
                table_lines += 1
        non_empty = sum(1 for line in lines if line.strip())
        return min(table_lines / max(non_empty, 1), 1.0)

    def _form_ratio(self, doc: Document) -> float:
        text = "\n".join(page.text for page in doc.pages if page.text)
        if not text:
            return 0.0
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return 0.0
        kv_lines = sum(1 for line in lines if ":" in line and len(line.split(":")[0].split()) <= 5)
        return min(kv_lines / len(lines), 1.0)

    def _profile(self, table_ratio: float, form_ratio: float, image_ratio: float, avg_len: float) -> str:
        if image_ratio > 0.6:
            return "image-heavy"
        if table_ratio > 0.15:
            return "table-heavy"
        if form_ratio > 0.25:
            return "form-centric"
        return "text-heavy" if avg_len >= 200 else "text-light"

    def _doc_type(self, doc: Document, content_profile: str) -> str:
        if doc.source == "scanned" or content_profile == "image-heavy":
            return "scanned_document"
        if content_profile == "table-heavy":
            return "table_document"
        if content_profile == "form-centric":
            return "form_document"
        return "text_document"

    def _vendor_cluster(self, doc: Document) -> str:
        vendor = doc.metadata.get("vendor") or doc.metadata.get("vendor_cluster")
        if vendor:
            return str(vendor).strip().lower()
        base = doc.doc_id.split("_")[0].split("-")[0].strip().lower()
        return base or "unknown"

    def _quality_bin(self, quality_score: float) -> str:
        if quality_score >= 0.75:
            return "A"
        if quality_score >= 0.5:
            return "B"
        return "C"

    def _complexity_bin(self, complexity_score: float) -> str:
        if complexity_score <= 0.33:
            return "1"
        if complexity_score <= 0.66:
            return "2"
        return "3"

    def _signals(
        self,
        doc: Document,
        non_alpha_ratio: float,
        table_ratio: float,
        form_ratio: float,
        image_ratio: float,
    ) -> dict[str, float]:
        text = "\n".join(page.text for page in doc.pages if page.text)
        total_chars = len(text)
        alpha_chars = sum(1 for ch in text if ch.isalnum())
        text_density = alpha_chars / max(total_chars, 1)
        dpi_est = float(doc.metadata.get("dpi", 300 if doc.source == "scanned" else 0))
        skew_angle = float(doc.metadata.get("skew_angle", 0.0))
        blur_score = min(max(non_alpha_ratio * 1.2, 0.0), 1.0)
        table_likelihood = min(table_ratio * 25.0, 1.0)
        return {
            "dpi_est": dpi_est,
            "blur_score": blur_score,
            "skew_angle": skew_angle,
            "text_density": text_density,
            "image_ratio": image_ratio,
            "table_likelihood": table_likelihood,
        }
