"""Schema-guided LLM prompt construction for structured extraction.

Salvaged and adapted from legacy idpo/agents/extraction_prompts.py.
Provider-specific chat wrappers (build_chat_messages etc.) are excluded —
callers assemble message lists using SYSTEM_PROMPT and the functions here.
Not yet wired into any runtime pipeline.
"""

from __future__ import annotations

import re

_DESC_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "for", "from",
    "field", "value", "document", "extract", "this", "that", "with",
})

SYSTEM_PROMPT = (
    "You are a precise document data extraction engine. "
    "You only return valid JSON. No markdown, no explanations, no extra text."
)

_RULES = (
    "1. Return ONLY a JSON object with key 'entities' as a list.\n"
    '2. Each entity: {"key": "<field_name>", "value": "<exact_value>", "confidence": <0.0-1.0>}\n'
    "3. Use ONLY the requested field names above — never invent keys.\n"
    "4. Extract numeric amounts exactly as they appear (e.g. '70,000' not '70000', '36.000' not '36').\n"
    "5. Only extract values that appear explicitly in the document text — do NOT guess, infer, or construct values.\n"
    '6. If a field is absent, include it with value "N/A" and confidence 0.0. Do NOT guess or infer a value.\n'
    "7. At most one entity per key. Confidence: 0.9+ = verbatim, 0.6-0.8 = probable, 0.0 = not found."
)


def build_extraction_prompt(
    fields: list[str],
    field_descriptions: dict[str, str],
    document_text: str,
    *,
    expected_format: str = "json",
    no_think: bool = False,
) -> str:
    """Build the user-turn extraction prompt for a set of schema fields.

    Adapted from legacy build_prompt; AgentContext and Document removed.
    ``no_think=True`` prepends /no_think for Qwen3 extended-thinking suppression.
    """
    if field_descriptions and fields:
        fields_block = "\n".join(
            f'  - "{key}": {field_descriptions.get(key, "Extract this field value")} [omit if not present]'
            for key in fields
        )
    elif fields:
        fields_block = "\n".join(f'  - "{key}" [omit if not present]' for key in fields)
    else:
        fields_block = "  - Extract any relevant key-value fields you find"

    prompt = (
        "Extract the following fields from the document text.\n\n"
        "FIELDS:\n"
        f"{fields_block}\n\n"
        "RULES:\n"
        f"{_RULES}\n\n"
        "DOCUMENT TEXT:\n"
        "---\n"
        f"{document_text}\n"
        "---\n\n"
        "JSON:"
    )
    if no_think:
        prompt = "/no_think\n" + prompt
    return prompt


def build_single_field_prompt(
    field_name: str,
    field_description: str,
    document_text: str,
    *,
    no_think: bool = False,
) -> str:
    """Build a prompt for extracting exactly one field.

    Adapted from legacy build_single_field_prompt; AgentContext removed.
    """
    prompt = (
        f'Extract the field "{field_name}" from the document text.\n\n'
        f"FIELD DESCRIPTION: {field_description or 'Extract this field value'}\n\n"
        "RULES:\n"
        "1. Return ONLY a JSON object: "
        '{"entities": [{"key": "<field_name>", "value": "<exact_value>", "confidence": <0.0-1.0>}]}\n'
        "2. Extract the value exactly as it appears in the document — do NOT guess or infer.\n"
        '3. If the field is absent, return value "N/A" with confidence 0.0.\n'
        "4. Extract numeric amounts exactly as they appear (e.g. '70,000' not '70000').\n\n"
        "DOCUMENT TEXT:\n"
        "---\n"
        f"{document_text}\n"
        "---\n\n"
        "JSON:"
    )
    if no_think:
        prompt = "/no_think\n" + prompt
    return prompt


def build_extraction_input(
    document_text: str,
    fields: list[str],
    field_descriptions: dict[str, str],
    *,
    max_chars: int = 12000,
    prefer_targeted: bool = True,
    window_lines: int = 2,
) -> str:
    """Select and return the document text to embed in an extraction prompt.

    Strategy (simplified from legacy 5-way):
    1. If text fits within max_chars, return it in full.
    2. If prefer_targeted and targeted context is non-empty and sufficient,
       return targeted context (combined with truncated remainder if room allows).
    3. Fall back to smart-truncated full text.

    Adapted from legacy build_extraction_input; Document/AgentContext removed.
    No page-number prefixes — operates on flat document_text.
    """
    if not document_text.strip():
        return ""

    if len(document_text) <= max_chars:
        return document_text

    if prefer_targeted and fields:
        targeted = _targeted_context(document_text, fields, field_descriptions, window_lines=window_lines)
        if targeted and _is_sufficient(targeted, document_text):
            if len(targeted) >= int(max_chars * 0.8):
                return _smart_truncate(targeted, max_chars)
            remaining = max(0, max_chars - len(targeted) - 2)
            if remaining:
                return targeted + "\n\n" + _smart_truncate(document_text, remaining)
            return targeted

    return _smart_truncate(document_text, max_chars)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]


def _targeted_context(
    document_text: str,
    fields: list[str],
    field_descriptions: dict[str, str],
    window_lines: int = 1,
) -> str:
    terms: set[str] = set()
    for key in fields:
        terms.update(token for token in _tokenize(key) if len(token) > 2)
        description = field_descriptions.get(key, "")
        terms.update(
            token
            for token in _tokenize(description)
            if token not in _DESC_STOPWORDS and len(token) > 2
        )
    if not terms:
        return ""

    lines = document_text.splitlines()
    seen: set[int] = set()
    snippets: list[str] = []
    for idx, line in enumerate(lines):
        lowered = line.lower()
        if not any(term in lowered for term in terms):
            continue
        start = max(0, idx - window_lines)
        end = min(len(lines), idx + window_lines + 1)
        for line_idx in range(start, end):
            if line_idx in seen:
                continue
            seen.add(line_idx)
            text_line = lines[line_idx].strip()
            if text_line:
                snippets.append(text_line)
    return "\n".join(snippets)


def _is_sufficient(targeted: str, full_text: str) -> bool:
    targeted_chars = len(targeted.strip())
    if targeted_chars == 0:
        return False
    full_chars = max(1, len(full_text.strip()))
    min_chars = min(full_chars, max(40, int(full_chars * 0.3)))
    return targeted_chars >= min_chars


def _smart_truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_para = truncated.rfind("\n\n")
    if last_para > max_chars * 0.7:
        return truncated[:last_para]
    last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
    if last_sentence > max_chars * 0.7:
        return truncated[:last_sentence + 1]
    last_line = truncated.rfind("\n")
    if last_line > max_chars * 0.8:
        return truncated[:last_line]
    return truncated
