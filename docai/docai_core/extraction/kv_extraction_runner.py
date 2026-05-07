"""KV-only extraction runner for DocAI v2.

First real (non-stub) extraction runner. Uses deterministic key-value extraction,
schema canonicalization, and candidate merging to build ExtractedOutput from
OCROutput.text. No model calls, no image processing, no table extraction.
Not yet wired into DocumentProcessor/runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import (
    Document,
    ExtractionSchema,
    ExtractedOutput,
    Field,
    FieldOutput,
    OCROutput,
    SelectedPolicy,
)
from docai_core.extraction.canonicalization import canonicalize_entities, merge_by_key
from docai_core.extraction.degarble import detect_and_degarble
from docai_core.extraction.generic_kv import extract_key_values
from docai_core.extraction.layout_form_kv import extract_layout_aware_kv
from docai_core.extraction.normalization import normalize_key


@dataclass(slots=True)
class KVOnlyExtractionRunner:
    """Deterministic extraction runner using generic KV extraction and canonicalization.

    Satisfies ExtractionRunnerProtocol. Does not call any model or perform OCR.
    Tables are not extracted — ExtractedOutput.tables is always empty.
    """

    runner_id: str = "kv_only_extraction_runner"

    def build_ocr_output(self, document: Document) -> OCROutput:
        """Return an empty OCROutput for protocol compatibility.

        This runner does not perform OCR. Callers should supply a populated
        OCROutput from a real OCR plugin and pass it to build_extracted_output.
        """
        return OCROutput(
            document_id=document.document_id,
            engine_id=self.runner_id,
            text="",
            pages=[],
            blocks=[],
            tables_detected=[],
            confidence=0.0,
        )

    def build_extracted_output(
        self,
        schema: ExtractionSchema,
        document: Document,
        selected_policy: SelectedPolicy,
        ocr_output: OCROutput,
    ) -> ExtractedOutput:
        """Extract schema fields from OCROutput.text using KV heuristics + layout-aware fallback.

        Flow:
        1. Degarble text if needed.
        2. Run extract_key_values → raw candidates.
        3. Canonicalize candidates to schema fields.
        4. Merge by key (keep highest confidence).
        5. For missing fields, try layout-aware form KV fallback.
        6. Build one FieldOutput per schema field; missing fields → N/A.
        """
        raw_text = ocr_output.text or ""
        if not raw_text.strip():
            return self._empty_output(schema, document, selected_policy)

        cleaned_text, _ = detect_and_degarble(raw_text)

        kv_candidates = extract_key_values(cleaned_text)
        entities: list[dict[str, object]] = [
            {
                "key": c.key,
                "value": c.value,
                "confidence": c.confidence,
                "metadata": {"source": "generic_kv", **c.metadata},
            }
            for c in kv_candidates
        ]

        schema_fields = [f.name for f in schema.fields]
        field_descriptions = {
            f.name: " ".join(filter(None, [f.description or ""] + list(f.aliases or [])))
            for f in schema.fields
        }

        canonical = canonicalize_entities(entities, schema_fields, field_descriptions)
        merged = merge_by_key(canonical)
        candidate_map: dict[str, dict[str, object]] = {
            normalize_key(str(e.get("key", ""))): e for e in merged
        }

        # Build fields, with layout-aware fallback for missing ones
        fields = []
        for field in schema.fields:
            norm_name = normalize_key(field.name)
            candidate = candidate_map.get(norm_name)

            if candidate is None:
                # Try layout-aware extraction as fallback
                aliases = list(field.aliases or []) + [field.name]
                layout_candidate = extract_layout_aware_kv(cleaned_text, field.name, aliases)
                if layout_candidate:
                    candidate = {
                        "key": layout_candidate.key,
                        "value": layout_candidate.value,
                        "confidence": layout_candidate.confidence,
                        "metadata": {
                            "source": layout_candidate.source,
                            "source_line": layout_candidate.evidence_text,
                        },
                    }

            fields.append(self._field_output(field, candidate))

        return ExtractedOutput(
            document_id=document.document_id,
            schema_id=schema.schema_id,
            policy_id=selected_policy.policy_id,
            fields=fields,
            tables=[],
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _empty_output(
        self,
        schema: ExtractionSchema,
        document: Document,
        policy: SelectedPolicy,
    ) -> ExtractedOutput:
        return ExtractedOutput(
            document_id=document.document_id,
            schema_id=schema.schema_id,
            policy_id=policy.policy_id,
            fields=[self._field_output(f, None) for f in schema.fields],
            tables=[],
        )

    @staticmethod
    def _field_output(field: Field, candidate: dict[str, object] | None) -> FieldOutput:
        if candidate is not None:
            meta = candidate.get("metadata") or {}
            evidence = str(meta.get("source_line") or candidate["value"])
            # Use the source from metadata if available (e.g., layout_form_kv)
            method = str(meta.get("source") or "generic_kv")
            return FieldOutput(
                field_name=field.name,
                value=candidate["value"],
                confidence=float(candidate.get("confidence") or 0.0),
                evidence_text=evidence,
                extraction_method=method,
                validation_status="needs_review",
            )
        return FieldOutput(
            field_name=field.name,
            value="N/A",
            confidence=0.0,
            extraction_method="not_found",
            validation_status="missing",
        )
