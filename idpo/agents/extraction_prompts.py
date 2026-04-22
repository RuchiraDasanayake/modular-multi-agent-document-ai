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


def build_prompt(
    text: str,
    explicit_keys: list[str],
    ctx: AgentContext,
    field_descriptions: dict[str, str],
) -> str:
    keys = explicit_keys or [rule.key for rule in ctx.config.structuring.extraction_rules]
    if field_descriptions and keys:
        fields_block = "\n".join(
            f"  - \"{key}\": {field_descriptions.get(key, 'Extract this field value')}"
            for key in keys
        )
    elif keys:
        fields_block = "\n".join(f"  - \"{key}\"" for key in keys)
    else:
        fields_block = "  - Extract any relevant key-value fields you find"

    return (
        "You are an expert document data extraction system.\n\n"
        "TASK: Extract structured fields from the document text below.\n\n"
        "FIELDS TO EXTRACT:\n"
        f"{fields_block}\n\n"
        "RULES:\n"
        "1. Return ONLY valid JSON with top-level key 'entities' as a list.\n"
        "2. Each entity object must be exactly: {\"key\": \"<requested_key>\", \"value\": \"<exact_span>\", \"confidence\": <0.0-1.0>}.\n"
        "3. Use ONLY requested key names; never invent keys.\n"
        "4. If a field is not found, omit it (no hallucinated values).\n"
        "5. Prefer exact spans from the text. Keep original formatting for amounts, IDs, and dates.\n"
        "6. Confidence: 0.9+ exact evidence, 0.6-0.8 probable, <0.6 weak.\n"
        "7. No markdown, no explanations, no extra keys.\n\n"
        "8. At most one entity per key; keep the best supported value.\n\n"
        "DOCUMENT TEXT:\n"
        "```\n"
        f"{text}\n"
        "```\n\n"
        "Return JSON:\n"
    )


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
