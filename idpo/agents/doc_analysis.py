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
        page_count = len(doc.pages)
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
        quality_features = self._quality_features(doc, signals)
        structural_features = self._structural_features(doc, table_ratio, form_ratio, avg_len, page_count)
        route_bin = self._route_bin(quality_score, complexity_score, image_ratio, table_ratio, form_ratio, ctx)
        layout_cluster_id = self._layout_cluster_id(content_profile, structural_features)
        analysis_confidence = self._analysis_confidence(quality_score, complexity_score, quality_features, structural_features)
        confidence_type = "heuristic"

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
                "route_bin": route_bin,
                "layout_cluster_id": layout_cluster_id,
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
            layout_cluster_id=layout_cluster_id,
            route_bin=route_bin,
            analysis_confidence=analysis_confidence,
            confidence_type=confidence_type,
            quality_features=quality_features,
            structural_features=structural_features,
            signals=signals,
        )

        signal = StageSignal(
            stage=self.name,
            confidence=analysis_confidence,
            uncertainty=1.0 - analysis_confidence,
            metadata={
                "table_ratio": table_ratio,
                "form_ratio": form_ratio,
                "quality_bin": quality_bin,
                "route_bin": route_bin,
                "layout_cluster_id": layout_cluster_id,
            },
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
                "route_bin": route_bin,
                "layout_cluster_id": layout_cluster_id,
                "analysis_confidence": analysis_confidence,
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

    def _quality_features(self, doc: Document, signals: dict[str, float]) -> dict[str, float]:
        return {
            "blur_score": round(float(signals.get("blur_score", 0.0)), 4),
            "skew_angle": round(float(signals.get("skew_angle", 0.0)), 4),
            "text_density": round(float(signals.get("text_density", 0.0)), 4),
            "image_ratio": round(float(signals.get("image_ratio", 0.0)), 4),
            "dpi_est": round(float(signals.get("dpi_est", 0.0)), 2),
        }

    def _structural_features(
        self,
        doc: Document,
        table_ratio: float,
        form_ratio: float,
        avg_len: float,
        page_count: int,
    ) -> dict[str, float]:
        text = "\n".join(page.text for page in doc.pages if page.text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        heading_density = 0.0
        if lines:
            heading_lines = 0
            for line in lines:
                words = len(line.split())
                if words <= 6 and line == line.upper():
                    heading_lines += 1
            heading_density = heading_lines / len(lines)
        return {
            "table_ratio": round(float(table_ratio), 4),
            "form_ratio": round(float(form_ratio), 4),
            "page_count": float(page_count),
            "avg_line_length": round(float(avg_len), 4),
            "heading_density": round(float(heading_density), 4),
        }

    def _route_bin(
        self,
        quality_score: float,
        complexity_score: float,
        image_ratio: float,
        table_ratio: float,
        form_ratio: float,
        ctx: AgentContext,
    ) -> str:
        heavy_signal = (
            quality_score < ctx.config.routing.quality_threshold
            or complexity_score >= ctx.config.routing.heavy_route_threshold
            or image_ratio >= ctx.config.routing.image_specialization_threshold
            or table_ratio >= ctx.config.routing.table_specialization_threshold
            or form_ratio >= ctx.config.routing.form_specialization_threshold
        )
        if heavy_signal:
            return "heavy"
        if quality_score >= 0.82 and complexity_score <= ctx.config.routing.light_route_threshold:
            return "light"
        return "standard"

    def _layout_cluster_id(self, content_profile: str, structural_features: dict[str, float]) -> str:
        table_ratio = structural_features.get("table_ratio", 0.0)
        form_ratio = structural_features.get("form_ratio", 0.0)
        if content_profile == "table-heavy" or table_ratio >= 0.2:
            return "table_dense"
        if content_profile == "form-centric" or form_ratio >= 0.25:
            return "form_dense"
        if content_profile == "image-heavy":
            return "image_sparse"
        return "text_simple"

    def _analysis_confidence(
        self,
        quality_score: float,
        complexity_score: float,
        quality_features: dict[str, float],
        structural_features: dict[str, float],
    ) -> float:
        blur_penalty = min(quality_features.get("blur_score", 0.0), 1.0) * 0.15
        skew_penalty = min(abs(quality_features.get("skew_angle", 0.0)) / 20.0, 1.0) * 0.1
        complexity_penalty = min(complexity_score, 1.0) * 0.15
        sparse_penalty = 0.05 if structural_features.get("page_count", 0.0) <= 0 else 0.0
        confidence = quality_score - blur_penalty - skew_penalty - complexity_penalty - sparse_penalty
        return round(max(0.05, min(confidence, 0.99)), 4)
