from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from docai_core.contracts.domain import ExtractedOutput

_MISSING_MARKERS = frozenset({"", "n/a", "none"})


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _looks_numeric_or_currency(value: str) -> bool:
    """True only when value is purely digits, commas, decimal point, and optional leading $."""
    stripped = value.strip().lstrip("$").replace(",", "").replace(".", "")
    return bool(stripped) and stripped.isdigit()


def _normalize_numeric_value(value: str) -> str:
    """Strip leading $ and commas for loose currency matching."""
    return value.strip().lstrip("$").replace(",", "")


@dataclass(slots=True)
class GroundedFieldResult:
    """Grounding verdict for one extracted field."""

    field_name: str
    value: str
    is_grounded: bool
    match_text: str | None = None
    start_index: int | None = None
    end_index: int | None = None
    reason: str = ""


@dataclass(slots=True)
class GroundingResult:
    """Aggregated grounding results for one document."""

    document_id: str
    grounded_count: int
    ungrounded_count: int
    missing_count: int
    fields: list[GroundedFieldResult] = dc_field(default_factory=list)


@dataclass(slots=True)
class GroundingValidator:
    """Validate extracted field values against cleaned source text.

    Deterministic v1: no model calls, no fuzzy libraries.
    Supports exact, case-insensitive, whitespace-normalized, and conservative
    numeric/currency matching. Does not mutate ExtractedOutput.
    """

    case_sensitive: bool = False
    normalize_whitespace: bool = True
    allow_numeric_loose_match: bool = True

    def validate(
        self,
        extracted_output: ExtractedOutput,
        source_text: str,
    ) -> GroundingResult:
        """Return a GroundingResult for all fields in extracted_output."""
        results: list[GroundedFieldResult] = []
        grounded = 0
        ungrounded = 0
        missing = 0

        for field in extracted_output.fields:
            value_str = "" if field.value is None else str(field.value)

            if value_str.lower().strip() in _MISSING_MARKERS:
                results.append(GroundedFieldResult(
                    field_name=field.field_name,
                    value=value_str,
                    is_grounded=False,
                    reason="missing_value",
                ))
                missing += 1
                continue

            span = self._find_span(source_text, value_str)
            if span is not None:
                start, end, matched = span
                results.append(GroundedFieldResult(
                    field_name=field.field_name,
                    value=value_str,
                    is_grounded=True,
                    match_text=matched,
                    start_index=start,
                    end_index=end,
                    reason="exact_match",
                ))
                grounded += 1
                continue

            if self.allow_numeric_loose_match and _looks_numeric_or_currency(value_str):
                norm = _normalize_numeric_value(value_str)
                if norm != value_str.strip():
                    span = self._find_span(source_text, norm)
                    if span is not None:
                        start, end, matched = span
                        results.append(GroundedFieldResult(
                            field_name=field.field_name,
                            value=value_str,
                            is_grounded=True,
                            match_text=matched,
                            start_index=start,
                            end_index=end,
                            reason="numeric_loose_match",
                        ))
                        grounded += 1
                        continue

            results.append(GroundedFieldResult(
                field_name=field.field_name,
                value=value_str,
                is_grounded=False,
                reason="not_found_in_source",
            ))
            ungrounded += 1

        return GroundingResult(
            document_id=extracted_output.document_id,
            grounded_count=grounded,
            ungrounded_count=ungrounded,
            missing_count=missing,
            fields=results,
        )

    def _find_span(self, source: str, value: str) -> tuple[int, int, str] | None:
        """Search for value in source, applying configured normalization.

        Returns (start, end, matched_text) in the (possibly collapsed) source
        space, or None if not found.
        """
        s = _collapse_whitespace(source) if self.normalize_whitespace else source
        v = _collapse_whitespace(value) if self.normalize_whitespace else value

        if not self.case_sensitive:
            idx = s.lower().find(v.lower())
        else:
            idx = s.find(v)

        if idx == -1:
            return None

        matched = s[idx : idx + len(v)]
        return idx, idx + len(v), matched
