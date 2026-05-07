"""ModelCenteredExtractionRunner — KV + model candidate merge for DocAI v2.

Satisfies ExtractionRunnerProtocol. Not yet wired into DocumentProcessor or
any runtime pipeline. Tests use fake ModelPlugin / QwenExtractionStep.

Hardening guards (derived from legacy review):
- model_confidence_floor=0.30: candidates below this threshold are treated as not found.
- _is_valid_model_value: rejects label-leakage artifacts and pathologically short/long values.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from docai_core.contracts.domain import (
    Document,
    ExtractionSchema,
    ExtractedOutput,
    Field,
    FieldOutput,
    OCROutput,
    SelectedPolicy,
)
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.normalization import MISSING_VALUE_MARKERS, normalize_key
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep


@dataclass(slots=True)
class ModelCenteredExtractionRunner:
    """Merge KV-heuristic candidates with schema-guided model candidates.

    The model is the primary semantic extractor; KV is fallback/cross-check.
    GroundingValidationRunner remains responsible for verifying that selected
    values are traceable to the source text — high model confidence does not
    bypass grounding.
    """

    model_step: QwenExtractionStep
    kv_runner: KVOnlyExtractionRunner = dc_field(default_factory=KVOnlyExtractionRunner)
    model_confidence_floor: float = 0.30

    def build_ocr_output(self, document: Document) -> OCROutput:
        """Protocol compatibility only — delegates to kv_runner."""
        return self.kv_runner.build_ocr_output(document)

    def build_extracted_output(
        self,
        schema: ExtractionSchema,
        document: Document,
        selected_policy: SelectedPolicy,
        ocr_output: OCROutput,
    ) -> ExtractedOutput:
        """Produce ExtractedOutput by merging KV and model candidates.

        Flow:
        1. Run KV path → per-field FieldOutput via kv_runner.
        2. Run model path → canonicalized candidate dicts via model_step.
        3. Apply hardening guards to model candidates.
        4. Merge per schema field; return ExtractedOutput preserving field order.
        """
        kv_output = self.kv_runner.build_extracted_output(
            schema, document, selected_policy, ocr_output
        )
        kv_map: dict[str, FieldOutput] = {
            normalize_key(f.field_name): f for f in kv_output.fields
        }

        model_raw = self.model_step.run(schema, ocr_output.text or "")
        model_map: dict[str, dict[str, object]] = {
            normalize_key(str(c.get("key", ""))): c for c in model_raw
        }

        return ExtractedOutput(
            document_id=document.document_id,
            schema_id=schema.schema_id,
            policy_id=selected_policy.policy_id,
            fields=[
                self._merge_field(field, kv_map, model_map)
                for field in schema.fields
            ],
            tables=[],
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _merge_field(
        self,
        field: Field,
        kv_map: dict[str, FieldOutput],
        model_map: dict[str, dict[str, object]],
    ) -> FieldOutput:
        norm = normalize_key(field.name)
        kv_fo = kv_map.get(norm)
        model_cand = model_map.get(norm)

        kv_found = kv_fo is not None and kv_fo.extraction_method != "not_found"
        model_found = self._model_usable(model_cand)

        if kv_found and model_found:
            return self._merge_both(field, kv_fo, model_cand)  # type: ignore[arg-type]
        if model_found:
            return self._from_model(field, model_cand)  # type: ignore[arg-type]
        if kv_found:
            return self._from_kv(kv_fo)  # type: ignore[arg-type]
        return self._not_found(field)

    def _model_usable(self, cand: dict[str, object] | None) -> bool:
        """Return True only if cand passes all hardening guards."""
        if cand is None:
            return False
        val = str(cand.get("value", "")).strip()
        conf = float(cand.get("confidence") or 0.0)
        return (
            not self._is_missing(val)
            and conf >= self.model_confidence_floor
            and self._is_valid_model_value(val)
        )

    def _merge_both(
        self,
        field: Field,
        kv_fo: FieldOutput,
        model_cand: dict[str, object],
    ) -> FieldOutput:
        kv_val = str(kv_fo.value).strip()
        model_val = str(model_cand.get("value", "")).strip()
        kv_conf = float(kv_fo.confidence or 0.0)
        model_conf = float(model_cand.get("confidence") or 0.0)

        if kv_val == model_val:
            return FieldOutput(
                field_name=field.name,
                value=kv_fo.value,
                confidence=max(kv_conf, model_conf),
                evidence_text=kv_val,
                extraction_method="hybrid_kv_model",
                validation_status="needs_review",
            )

        if model_conf >= kv_conf:
            return FieldOutput(
                field_name=field.name,
                value=model_val,
                confidence=model_conf,
                evidence_text=model_val,
                extraction_method="model_extraction",
                validation_status="needs_review",
            )
        return FieldOutput(
            field_name=field.name,
            value=kv_fo.value,
            confidence=kv_conf,
            evidence_text=kv_val,
            extraction_method="generic_kv",
            validation_status="needs_review",
        )

    @staticmethod
    def _from_model(field: Field, cand: dict[str, object]) -> FieldOutput:
        val = str(cand.get("value", "")).strip()
        conf = float(cand.get("confidence") or 0.0)
        return FieldOutput(
            field_name=field.name,
            value=val,
            confidence=conf,
            evidence_text=val,
            extraction_method="model_extraction",
            validation_status="needs_review",
        )

    @staticmethod
    def _from_kv(kv_fo: FieldOutput) -> FieldOutput:
        return FieldOutput(
            field_name=kv_fo.field_name,
            value=kv_fo.value,
            confidence=kv_fo.confidence,
            evidence_text=str(kv_fo.value),
            extraction_method="generic_kv",
            validation_status="needs_review",
        )

    @staticmethod
    def _not_found(field: Field) -> FieldOutput:
        return FieldOutput(
            field_name=field.name,
            value="N/A",
            confidence=0.0,
            extraction_method="not_found",
            validation_status="missing",
        )

    @staticmethod
    def _is_missing(value: str) -> bool:
        return value.strip().lower() in MISSING_VALUE_MARKERS

    @staticmethod
    def _is_valid_model_value(value: str) -> bool:
        """Return False for label-leakage artifacts and pathologically short/long values."""
        stripped = value.strip()
        if len(stripped) < 2:
            return False
        if len(stripped) > 180:
            return False
        if stripped.endswith(":"):
            return False
        if len(stripped) == 1 and stripped.isalpha():
            return False
        return True
