from __future__ import annotations

import hashlib
import re
import statistics
import time
from typing import Dict, List, Tuple

from idpo.agents.base import Agent, AgentContext
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, DAEOutput, Document, StageSignal


class DocumentAnalysisAgent(Agent):
    name = "document_analysis"
    version = "v2"
    input_contract = {"document": "Document"}
    output_contract = {
        "dae_output": "DAEOutput",
        "analysis": {"quality_score": "float", "complexity_score": "float", "profile": "str"},
        "signal": "StageSignal",
    }

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        full_text = "\n".join(page.text or "" for page in doc.pages)
        lines = [line for line in full_text.splitlines() if line.strip()]
        page_lengths = [len(page.text or "") for page in doc.pages]
        avg_len = statistics.mean(page_lengths) if page_lengths else 0.0

        non_alpha_ratio = self._non_alpha_ratio(full_text)
        blur = self._blur_estimate(doc, full_text, non_alpha_ratio)
        contrast = self._contrast_estimate(full_text)
        skew = self._skew_estimate(doc)
        noise = self._noise_estimate(full_text, non_alpha_ratio)

        table_density, form_pattern, blocks, sections = self._structural_features(lines, full_text)
        image_ratio = 1.0 if doc.source == "scanned" or any(page.image_path for page in doc.pages) else 0.0

        quality_score = self._quality_score(blur, contrast, skew, noise)
        complexity_score = self._complexity_score(table_density, form_pattern, blocks, sections, image_ratio)
        route_bin = self._route_bin(quality_score, complexity_score, ctx)

        content_profile = self._profile(table_density, form_pattern, image_ratio, avg_len)
        doc_type = self._doc_type(doc, content_profile)
        vendor_cluster = self._vendor_cluster(doc)
        layout_cluster_id = self._layout_cluster(lines, table_density, form_pattern, blocks, sections)
        quality_bin = self._quality_bin(quality_score)
        complexity_bin = self._complexity_bin(complexity_score)

        quality_features = {
            "blur_estimate": blur,
            "contrast_estimate": contrast,
            "skew_estimate": skew,
            "noise_estimate": noise,
        }
        structural_features = {
            "table_density_proxy": table_density,
            "block_count_proxy": blocks,
            "section_count_proxy": sections,
            "form_pattern_proxy": form_pattern,
        }
        confidence_type = (
            "calibrated"
            if ctx.config.calibration.enabled
            and ctx.config.calibration.mode != "heuristic_only"
            and ctx.config.calibration.model_path
            else "heuristic"
        )
        analysis_confidence = self._analysis_confidence(full_text, quality_score, complexity_score)

        signals = self._signals(
            full_text=full_text,
            image_ratio=image_ratio,
            quality_features=quality_features,
            structural_features=structural_features,
            route_bin=route_bin,
        )

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
                "layout_cluster_id": layout_cluster_id,
                "quality_bin": quality_bin,
                "complexity_bin": complexity_bin,
                "content_profile": content_profile,
                "route_bin": route_bin,
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
            quality_features=quality_features,
            structural_features=structural_features,
            analysis_confidence=analysis_confidence,
            confidence_type=confidence_type,
            signals=signals,
        )

        signal = StageSignal(
            stage=self.name,
            confidence=analysis_confidence,
            uncertainty=max(0.0, 1.0 - analysis_confidence),
            metadata={
                "quality_bin": quality_bin,
                "complexity_bin": complexity_bin,
                "route_bin": route_bin,
                "confidence_type": confidence_type,
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
                "layout_cluster_id": layout_cluster_id,
                "quality_bin": quality_bin,
                "complexity_bin": complexity_bin,
                "route_bin": route_bin,
                "quality_features": quality_features,
                "structural_features": structural_features,
                "analysis_confidence": analysis_confidence,
                "confidence_type": confidence_type,
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
                    "route_bin": route_bin,
                    "quality_features": quality_features,
                    "structural_features": structural_features,
                    "analysis_confidence": analysis_confidence,
                    "confidence_type": confidence_type,
                },
                "signal": signal,
            }
        )

    def _non_alpha_ratio(self, text: str) -> float:
        if not text:
            return 1.0
        non_alpha = sum(1 for ch in text if not ch.isalnum() and not ch.isspace())
        return non_alpha / max(len(text), 1)

    def _blur_estimate(self, doc: Document, text: str, non_alpha_ratio: float) -> float:
        if not text.strip():
            return 0.9 if doc.source == "scanned" else 0.7
        short_lines = sum(1 for line in text.splitlines() if 0 < len(line.strip()) <= 2)
        total_lines = max(len([line for line in text.splitlines() if line.strip()]), 1)
        short_line_ratio = short_lines / total_lines
        return min(max((non_alpha_ratio * 0.7) + (short_line_ratio * 0.3), 0.0), 1.0)

    def _contrast_estimate(self, text: str) -> float:
        if not text:
            return 0.2
        chars = [ch for ch in text if not ch.isspace()]
        if not chars:
            return 0.2
        upper = sum(1 for ch in chars if ch.isupper())
        lower = sum(1 for ch in chars if ch.islower())
        digit = sum(1 for ch in chars if ch.isdigit())
        dominant = max(upper, lower, digit)
        return max(0.2, min(1.0, dominant / len(chars)))

    def _skew_estimate(self, doc: Document) -> float:
        raw = float(doc.metadata.get("skew_angle", 0.0) or 0.0)
        return min(abs(raw) / 15.0, 1.0)

    def _noise_estimate(self, text: str, non_alpha_ratio: float) -> float:
        if not text:
            return 0.9
        odd = sum(1 for ch in text if ord(ch) < 9 or (13 < ord(ch) < 32))
        odd_ratio = odd / max(len(text), 1)
        return min(max((odd_ratio * 0.6) + (non_alpha_ratio * 0.4), 0.0), 1.0)

    def _structural_features(self, lines: List[str], text: str) -> Tuple[float, float, float, float]:
        if not lines:
            return 0.0, 0.0, 0.0, 0.0
        table_lines = sum(1 for line in lines if "|" in line or "\t" in line or re.search(r"\d+\s+\d+\s+\d+", line))
        table_density = min(table_lines / max(len(lines), 1), 1.0)

        kv_lines = sum(
            1 for line in lines if ":" in line and len(line.split(":")[0].split()) <= 6
        )
        form_pattern = min(kv_lines / max(len(lines), 1), 1.0)

        paragraphs = [block for block in re.split(r"\n\s*\n", text) if block.strip()]
        block_count = min(len(paragraphs) / 20.0, 1.0)

        heading_lines = sum(
            1 for line in lines if line.strip().isupper() or re.match(r"^\d+(\.\d+)*\s+\w+", line.strip())
        )
        section_count = min(heading_lines / 15.0, 1.0)
        return table_density, form_pattern, block_count, section_count

    def _quality_score(self, blur: float, contrast: float, skew: float, noise: float) -> float:
        score = 1.0 - ((blur * 0.3) + ((1.0 - contrast) * 0.25) + (skew * 0.2) + (noise * 0.25))
        return min(max(score, 0.0), 1.0)

    def _complexity_score(
        self,
        table_density: float,
        form_pattern: float,
        block_count: float,
        section_count: float,
        image_ratio: float,
    ) -> float:
        score = (
            table_density * 0.3
            + form_pattern * 0.25
            + block_count * 0.2
            + section_count * 0.15
            + image_ratio * 0.1
        )
        return min(max(score, 0.0), 1.0)

    def _route_bin(self, quality_score: float, complexity_score: float, ctx: AgentContext) -> str:
        route_signal = (complexity_score * 0.65) + ((1.0 - quality_score) * 0.35)
        if route_signal <= ctx.config.routing.light_route_threshold:
            return "light"
        if route_signal >= ctx.config.routing.heavy_route_threshold:
            return "heavy"
        return "standard"

    def _profile(self, table_ratio: float, form_ratio: float, image_ratio: float, avg_len: float) -> str:
        if image_ratio > 0.6:
            return "image-heavy"
        if table_ratio > 0.18:
            return "table-heavy"
        if form_ratio > 0.18:
            return "form-centric"
        return "text-heavy" if avg_len >= 120 else "text-heavy"

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

    def _layout_cluster(
        self,
        lines: List[str],
        table_density: float,
        form_pattern: float,
        blocks: float,
        sections: float,
    ) -> str:
        line_lengths = [str(min(len(line), 80) // 10) for line in lines[:30]]
        signature = "|".join(line_lengths + [f"t{table_density:.2f}", f"f{form_pattern:.2f}", f"b{blocks:.2f}", f"s{sections:.2f}"])
        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
        return f"layout:{digest}"

    def _quality_bin(self, quality_score: float) -> str:
        if quality_score >= 0.78:
            return "A"
        if quality_score >= 0.55:
            return "B"
        return "C"

    def _complexity_bin(self, complexity_score: float) -> str:
        if complexity_score <= 0.33:
            return "1"
        if complexity_score <= 0.66:
            return "2"
        return "3"

    def _analysis_confidence(self, text: str, quality_score: float, complexity_score: float) -> float:
        text_factor = min(len(text) / 2000.0, 1.0)
        confidence = (quality_score * 0.5) + ((1.0 - abs(0.5 - complexity_score)) * 0.2) + (text_factor * 0.3)
        return min(max(confidence, 0.2), 0.98)

    def _signals(
        self,
        full_text: str,
        image_ratio: float,
        quality_features: Dict[str, float],
        structural_features: Dict[str, float],
        route_bin: str,
    ) -> Dict[str, float]:
        total_chars = len(full_text)
        alpha_chars = sum(1 for ch in full_text if ch.isalnum())
        text_density = alpha_chars / max(total_chars, 1)
        signal = {
            "text_density": text_density,
            "image_ratio": image_ratio,
            "route_bin_score": {"light": 0.2, "standard": 0.5, "heavy": 0.8}[route_bin],
        }
        signal.update(quality_features)
        signal.update(structural_features)
        signal["table_likelihood"] = structural_features.get("table_density_proxy", 0.0)
        signal["form_likelihood"] = structural_features.get("form_pattern_proxy", 0.0)
        return signal
