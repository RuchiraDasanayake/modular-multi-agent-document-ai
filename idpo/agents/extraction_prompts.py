from __future__ import annotations

import re

from idpo.agents.base import AgentContext
from idpo.core.types import Document

_DESC_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "from",
    "field",
    "value",
    "document",
    "extract",
    "this",
    "that",
    "with",
}


SYSTEM_PROMPT = (
    "You are a precise document data extraction engine. "
    "You only return valid JSON. No markdown, no explanations, no extra text."
)


def build_prompt(
    text: str,
    explicit_keys: list[str],
    ctx: AgentContext,
    field_descriptions: dict[str, str],
    *,
    extraction_context: str = "",
) -> str:
    """Build the user-turn prompt (works for both /generate and /chat endpoints)."""
    keys = explicit_keys or [rule.key for rule in ctx.config.structuring.extraction_rules]
    if field_descriptions and keys:
        fields_block = "\n".join(
            f'  - "{key}": {field_descriptions.get(key, "Extract this field value")} [omit if not present]'
            for key in keys
        )
    elif keys:
        fields_block = "\n".join(f'  - "{key}" [omit if not present]' for key in keys)
    else:
        fields_block = "  - Extract any relevant key-value fields you find"

    context_block = f"{extraction_context.strip()}\n\n" if extraction_context.strip() else ""

    return (
        f"{context_block}"
        "Extract the following fields from the document text.\n\n"
        "FIELDS:\n"
        f"{fields_block}\n\n"
        "RULES:\n"
        "1. Return ONLY a JSON object with key 'entities' as a list.\n"
        '2. Each entity: {"key": "<field_name>", "value": "<exact_value>", "confidence": <0.0-1.0>}\n'
        "3. Use ONLY the requested field names above — never invent keys.\n"
        "4. Extract numeric amounts exactly as they appear (e.g. '70,000' not '70000', '36.000' not '36').\n"
        "5. Only extract values that appear explicitly in the document text — do NOT guess, infer, or construct values.\n"
        '6. If a field is absent, include it with value "N/A" and confidence 0.0. Do NOT guess or infer a value.\n'
        "7. At most one entity per key. Confidence: 0.9+ = verbatim, 0.6-0.8 = probable, 0.0 = not found.\n\n"
        "DOCUMENT TEXT:\n"
        "---\n"
        f"{text}\n"
        "---\n\n"
        "JSON:"
    )


def build_chat_messages(
    text: str,
    explicit_keys: list[str],
    ctx: AgentContext,
    field_descriptions: dict[str, str],
    *,
    no_think: bool = True,
    extraction_context: str = "",
) -> list[dict[str, str]]:
    """Build messages list for /api/chat endpoint (Qwen3, Llama3, etc.).

    ``no_think=True`` prepends /no_think to the user message which disables
    Qwen3's extended thinking chain — faster and more deterministic for
    structured extraction tasks.
    """
    user_content = build_prompt(text, explicit_keys, ctx, field_descriptions, extraction_context=extraction_context)
    if no_think:
        user_content = "/no_think\n" + user_content
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_single_field_prompt(
    text: str,
    key: str,
    description: str,
    *,
    extraction_context: str = "",
    sibling_fields: dict[str, str] | None = None,
) -> str:
    """Prompt for extracting exactly one field. Used by per-field extraction mode."""
    context_block = f"{extraction_context.strip()}\n\n" if extraction_context.strip() else ""
    siblings = {name: desc for name, desc in (sibling_fields or {}).items() if name != key}
    sibling_block = ""
    if siblings:
        lines = "\n".join(f"- {name}: {desc or 'separate field'}" for name, desc in siblings.items())
        sibling_block = (
            "OTHER FIELDS (extracted separately). Use them only to tell which printed label belongs to "
            f'"{key}"; two fields may still have the same value:\n'
            f"{lines}\n\n"
        )
    return (
        f"{context_block}"
        f'Extract the field "{key}" from the document text.\n\n'
        f"FIELD DESCRIPTION: {description or 'Extract this field value'}\n\n"
        f"{sibling_block}"
        "RULES:\n"
        "1. Return ONLY a JSON object: "
        '{"entities": [{"key": "<field_name>", "value": "<exact_value>", "confidence": <0.0-1.0>}]}\n'
        "2. Extract the value exactly as it appears in the document — do NOT guess or infer.\n"
        '3. If the field is absent, return value "N/A" with confidence 0.0.\n'
        "4. Extract numeric amounts exactly as they appear (e.g. '70,000' not '70000').\n\n"
        "DOCUMENT TEXT:\n"
        "---\n"
        f"{text}\n"
        "---\n\n"
        "JSON:"
    )


def build_single_field_messages(
    text: str,
    key: str,
    description: str,
    *,
    no_think: bool = True,
    extraction_context: str = "",
    sibling_fields: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    user_content = build_single_field_prompt(
        text, key, description, extraction_context=extraction_context, sibling_fields=sibling_fields
    )
    if no_think:
        user_content = "/no_think\n" + user_content
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def build_extraction_text(
    doc: Document,
    explicit_keys: list[str],
    field_descriptions: dict[str, str],
    ctx: AgentContext,
) -> str:
    text, _ = build_extraction_input(doc, explicit_keys, field_descriptions, ctx)
    return text


def build_extraction_input(
    doc: Document,
    explicit_keys: list[str],
    field_descriptions: dict[str, str],
    ctx: AgentContext,
) -> tuple[str, dict[str, object]]:
    full_text = "\n".join(page.text for page in doc.pages)
    meta: dict[str, object] = {
        "strategy": "empty",
        "full_chars": len(full_text),
        "selected_chars": 0,
        "truncated": False,
        "targeted_context_chars": 0,
        "targeted_context_lines": 0,
    }
    if not full_text.strip():
        return "", meta

    max_chars = max(2000, int(ctx.config.llm.prompt_max_chars))
    targeted = ""
    if ctx.config.llm.prefer_targeted_context:
        targeted = _targeted_context(
            doc,
            explicit_keys,
            field_descriptions,
            window_lines=max(0, int(ctx.config.llm.context_window_lines)),
        )
        if targeted:
            targeted_lines = len([line for line in targeted.splitlines() if line.strip()])
            meta["targeted_context_chars"] = len(targeted)
            meta["targeted_context_lines"] = targeted_lines
            if (
                len(full_text) <= max_chars
                and len(targeted) <= int(len(full_text) * 0.85)
                and _targeted_context_is_sufficient(targeted, full_text)
            ):
                meta.update(
                    {
                        "strategy": "targeted_only",
                        "selected_chars": len(targeted),
                        "truncated": len(targeted) < len(full_text),
                    }
                )
                return targeted, meta

    if len(full_text) <= max_chars:
        meta.update({"strategy": "full", "selected_chars": len(full_text)})
        return full_text, meta
    if not ctx.config.llm.prefer_targeted_context:
        truncated = _smart_truncate(full_text, max_chars)
        meta.update(
            {
                "strategy": "truncate",
                "selected_chars": len(truncated),
                "truncated": len(truncated) < len(full_text),
            }
        )
        return truncated, meta

    if targeted:
        if len(targeted) >= int(max_chars * 0.8):
            truncated = _smart_truncate(targeted, max_chars)
            meta.update(
                {
                    "strategy": "targeted_only",
                    "selected_chars": len(truncated),
                    "truncated": len(truncated) < len(full_text),
                }
            )
            return truncated, meta
        remaining = max(0, max_chars - len(targeted) - 2)
        if remaining:
            combined = targeted + "\n\n" + _smart_truncate(full_text, remaining)
            meta.update(
                {
                    "strategy": "targeted_plus_truncated",
                    "selected_chars": len(combined),
                    "truncated": len(combined) < len(full_text),
                }
            )
            return combined, meta
        meta.update(
            {
                "strategy": "targeted_only",
                "selected_chars": len(targeted),
                "truncated": len(targeted) < len(full_text),
            }
        )
        return targeted, meta

    truncated = _smart_truncate(full_text, max_chars)
    meta.update(
        {
            "strategy": "truncate",
            "selected_chars": len(truncated),
            "truncated": len(truncated) < len(full_text),
        }
    )
    return truncated, meta


def _targeted_context(
    doc: Document,
    explicit_keys: list[str],
    field_descriptions: dict[str, str],
    window_lines: int = 1,
) -> str:
    if not explicit_keys:
        return ""
    terms: set[str] = set()
    for key in explicit_keys:
        terms.update(token for token in _tokenize(key) if len(token) > 2)
        description = field_descriptions.get(key, "")
        terms.update(
            token
            for token in _tokenize(description)
            if token not in _DESC_STOPWORDS and len(token) > 2
        )
    if not terms:
        return ""

    seen: set[tuple[int, int]] = set()
    snippets: list[str] = []
    for page in doc.pages:
        lines = page.text.splitlines()
        for idx, line in enumerate(lines):
            lowered = line.lower()
            if not any(term in lowered for term in terms):
                continue
            start = max(0, idx - window_lines)
            end = min(len(lines), idx + window_lines + 1)
            for line_idx in range(start, end):
                marker = (page.number, line_idx)
                if marker in seen:
                    continue
                seen.add(marker)
                text_line = lines[line_idx].strip()
                if not text_line:
                    continue
                snippets.append(f"[p{page.number}] {text_line}")
    return "\n".join(snippets)


def _targeted_context_is_sufficient(targeted: str, full_text: str) -> bool:
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


def _tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]
