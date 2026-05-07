"""Document analysis agent for quality assessment and complexity profiling."""

from __future__ import annotations

import re
import statistics
import time

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, DAEOutput, Document, StageSignal

_KEYED_LINE_RE = re.compile(
    r"^(?:to|from|date|dated|re|subject|attn|attention|fax|fax transmission|message to|message from|"
    r"invoice(?:\s*(?:number|no))?|receipt(?:\s*(?:number|no))?|bill to|ship to|customer|vendor|seller|"
    r"buyer|recipient|sender|account(?:\s*(?:number|no))?|order(?:\s*(?:number|no))?)\b",
    re.IGNORECASE,
)

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
        page_lengths = [len(self._page_analysis_text(page)) for page in doc.pages]
        avg_len = statistics.mean(page_lengths) if page_lengths else 0
        page_count = len(doc.pages)
        non_alpha_ratio = self._non_alpha_ratio(doc)
        table_ratio = self._table_ratio(doc)
        form_ratio = self._form_ratio(doc)
        # Only treat as image-heavy if pages lack meaningful text content
        # PDFs set image_path for rendering but may still have extractable text
        has_text = any(self._page_analysis_text(page) for page in doc.pages)
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
        ocr_text = self._analysis_text(doc)
        semantic_doc_type = self._classify_semantic_doc_type(ocr_text)
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
                "routing_family": semantic_doc_type,
                "semantic_doc_type": semantic_doc_type,
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
            semantic_doc_type=semantic_doc_type,
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
                "semantic_doc_type": semantic_doc_type,
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
        text = self._analysis_text(doc)
        if not text:
            return 1.0
        non_alpha = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
        return non_alpha / max(len(text), 1)

    def _table_ratio(self, doc: Document) -> float:
        text = self._analysis_text(doc)
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
        text = self._analysis_text(doc)
        if not text:
            return 0.0
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return 0.0
        kv_lines = sum(1 for line in lines if self._is_keyed_line(line))
        return min(kv_lines / len(lines), 1.0)

    def _profile(self, table_ratio: float, form_ratio: float, image_ratio: float, avg_len: float) -> str:
        if image_ratio > 0.6:
            return "image-heavy"
        if table_ratio > 0.08 and form_ratio > 0.12:
            return "mixed"
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
        if content_profile == "mixed":
            return "mixed_document"
        return "text_document"

    def _vendor_cluster(self, doc: Document) -> str:
        vendor = doc.metadata.get("vendor") or doc.metadata.get("vendor_cluster")
        if vendor:
            return str(vendor).strip().lower()
        base = doc.doc_id.split("_")[0].split("-")[0].strip().lower()
        return base or "unknown"

    def _classify_semantic_doc_type(self, text: str) -> str:
        """Fast keyword fingerprint to identify document semantic type from OCR text."""
        lower = text.lower()
        receipt_signals = sum([
            bool(re.search(r"\b(total|subtotal|tax|cash|change|receipt|invoice|grand\s*total)\b", lower)),
            bool(re.search(r"[$₩Rp¥€£]\s*[\d,.]+|[\d,.]+\s*(?:won|krw|idr|usd|eur)", lower)),
            bool(re.search(r"\b(vat|pb1|ppn|gst|discount|surcharge)\b", lower)),
            bool(re.search(r"\b(qty|quantity|unit\s*price|item|price|amount)\b", lower)),
            bool(re.search(r"\b(payment|paid|change|card|cash)\b", lower)),
            # Line items: digit(s) × digit(s) pattern common on receipts
            bool(re.search(r"\d+\s*[x×]\s*[\d,]+", lower)),
        ])
        correspondence_signals = sum([
            bool(re.search(r"\bdear\b|\bsincerely\b|\bregards\b|\bfaithfully\b", lower)),
            bool(
                re.search(
                    r"^(?:from|to|re|subject|date|attn|attention|message to|message from)\b\s*:?\s+\S",
                    lower,
                    re.MULTILINE,
                )
            ),
            bool(re.search(r"yours\s+(?:truly|sincerely|faithfully)|best\s+regards", lower)),
            bool(re.search(r"\battention\b|\bcc\s*:|\benc\b|\benclosed\b|\bfax\s+transmission\b", lower)),
            bool(re.search(r"\bdated?\b|\bdate\s*:", lower)),
            # Salutation line: "Dear Mr/Ms/Dr ..."
            bool(re.search(r"\bdear\s+(?:mr|ms|mrs|dr|prof|sir|madam)\b", lower)),
        ])
        legal_signals = sum([
            bool(re.search(r"\bcourt\b|\bplaintiff\b|\bdefendant\b|\bjudge\b|\btribunal\b", lower)),
            bool(re.search(r"case\s+(?:no|number|#)|\bfiled\b|\bserved\b|\bhereby\b", lower)),
        ])
        # Require >= 2 strong signals for specialist routing; 1 signal = fallback to unknown
        if receipt_signals >= 2:
            return "receipt"
        if correspondence_signals >= 2:
            return "correspondence"
        if legal_signals >= 2:
            return "legal_form"
        return "unknown"

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
        text = self._analysis_text(doc)
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
            "ocr_noise_ratio": round(float(self._ocr_noise_ratio(doc)), 4),
        }

    def _structural_features(
        self,
        doc: Document,
        table_ratio: float,
        form_ratio: float,
        avg_len: float,
        page_count: int,
    ) -> dict[str, float]:
        text = self._analysis_text(doc)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        heading_density = 0.0
        kv_density = 0.0
        numeric_density = 0.0
        line_length_cv = 0.0
        if lines:
            heading_lines = 0
            kv_lines = 0
            numeric_chars = 0
            line_lengths = [len(line) for line in lines]
            for line in lines:
                words = len(line.split())
                if words <= 6 and line == line.upper():
                    heading_lines += 1
                if self._is_keyed_line(line):
                    kv_lines += 1
                numeric_chars += sum(1 for ch in line if ch.isdigit())
            heading_density = heading_lines / len(lines)
            kv_density = kv_lines / len(lines)
            total_chars = sum(line_lengths)
            numeric_density = numeric_chars / max(total_chars, 1)
            if len(line_lengths) > 1:
                mean_length = statistics.mean(line_lengths)
                if mean_length > 0:
                    line_length_cv = statistics.pstdev(line_lengths) / mean_length
        return {
            "table_ratio": round(float(table_ratio), 4),
            "form_ratio": round(float(form_ratio), 4),
            "page_count": float(page_count),
            "avg_line_length": round(float(avg_len), 4),
            "heading_density": round(float(heading_density), 4),
            "kv_density": round(float(kv_density), 4),
            "numeric_density": round(float(numeric_density), 4),
            "line_length_cv": round(float(line_length_cv), 4),
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
        if content_profile == "mixed":
            return "mixed_dense"
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

    def _ocr_noise_ratio(self, doc: Document) -> float:
        text = self._analysis_text(doc)
        if not text:
            return 1.0
        suspicious = 0
        for token in text.split():
            stripped = token.strip()
            if not stripped:
                continue
            alpha = sum(1 for ch in stripped if ch.isalpha())
            digit = sum(1 for ch in stripped if ch.isdigit())
            punct = sum(1 for ch in stripped if not ch.isalnum())
            if punct >= max(alpha + digit, 1):
                suspicious += 1
            elif len(stripped) >= 6 and alpha > 0 and digit > 0 and (alpha + digit) == len(stripped):
                suspicious += 1
            elif len(stripped) >= 8 and alpha >= 5 and punct >= 2:
                suspicious += 1
        total_tokens = max(len(text.split()), 1)
        return min(suspicious / total_tokens, 1.0)

    def _analysis_text(self, doc: Document) -> str:
        return "\n".join(
            text
            for page in doc.pages
            if (text := self._page_analysis_text(page))
        )

    @staticmethod
    def _page_analysis_text(page) -> str:
        return str(page.text or page.raw_text or "").strip()

    def _is_keyed_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if ":" in stripped and len(stripped.split(":", 1)[0].split()) <= 6:
            return True
        if not _KEYED_LINE_RE.search(stripped):
            return False
        if len(stripped.split()) <= 12:
            return True
        return bool(re.search(r"\b(?:to|from|date|re|subject|attn)\b\s*:?\s+\S", stripped, re.IGNORECASE))
