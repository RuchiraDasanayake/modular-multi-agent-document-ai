"""QwenExtractionStep — schema-guided model extraction over cleaned text.

Uses any ModelPlugin implementation (not QwenModelPlugin specifically).
Returns a list of canonicalized candidate dicts ready for HybridExtractionRunner
to merge with KV candidates. Does not build ExtractedOutput.
"""

from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import ExtractionSchema
from docai_core.extraction.canonicalization import canonicalize_entities, merge_by_key
from docai_core.extraction.parsing_utils import parse_entities_response
from docai_core.extraction.prompt_builder import (
    SYSTEM_PROMPT,
    build_extraction_input,
    build_extraction_prompt,
)
from docai_core.plugins.models.base import ModelPlugin, ModelRequest


@dataclass(slots=True)
class QwenExtractionStep:
    """Schema-guided extraction step that delegates to any ModelPlugin.

    Returns list[dict[str, object]] with keys: key, value, confidence, metadata.
    Each dict has been canonicalized to schema field names and deduped by key.
    Callers (e.g. HybridExtractionRunner) are responsible for merging with KV
    candidates and assembling ExtractedOutput.
    """

    model_plugin: ModelPlugin
    no_think: bool = True
    default_confidence: float = 0.65

    def run(
        self,
        schema: ExtractionSchema,
        document_text: str,
    ) -> list[dict[str, object]]:
        """Run model extraction over document_text guided by schema.

        Returns an empty list when the model fails or produces no parseable output.
        Never raises.
        """
        if not document_text or not document_text.strip():
            return []

        field_names = [f.name for f in schema.fields]
        field_descriptions = {f.name: f.description or "" for f in schema.fields}

        context = build_extraction_input(
            document_text,
            field_names,
            field_descriptions,
        )
        prompt = build_extraction_prompt(
            field_names,
            field_descriptions,
            context,
            no_think=self.no_think,
        )

        schema_hint: dict[str, object] = {
            f.name: f.description or f.type
            for f in schema.fields
        }

        request = ModelRequest(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            expected_format="json",
            schema_hint=schema_hint,
            temperature=0.0,
            json_mode=True,
        )

        try:
            response = self.model_plugin.generate(request)
        except Exception:
            return []

        if not response.success or not response.text:
            return []

        model_name = response.model_name or "qwen"
        entities = parse_entities_response(
            response.text,
            model_name,
            source="qwen_extraction",
        )

        canonical = canonicalize_entities(entities, field_names, field_descriptions)
        merged = merge_by_key(canonical)
        return merged
