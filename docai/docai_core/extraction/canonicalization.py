"""Schema-field canonicalization utilities for structured extraction.

Salvaged from legacy idpo/agents/extraction_parsing.py.
Not yet wired into any runtime pipeline.

Operates on plain dicts produced by parse_entities_response (key, value,
confidence, metadata) rather than legacy Entity objects.
"""

from __future__ import annotations

import re

from docai_core.extraction.normalization import TOKEN_EQUIVALENTS, normalize_key

_DESC_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "for", "from",
    "field", "value", "document", "extract", "this", "that", "with",
})


def merge_by_key(
    entities: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Deduplicate entities by normalized key, keeping the highest-confidence item.

    Adapted from legacy merge_by_key; operates on plain dicts instead of Entity.
    """
    selected: dict[str, dict[str, object]] = {}
    for entity in entities:
        key = normalize_key(str(entity.get("key", "")))
        current = selected.get(key)
        if current is None:
            selected[key] = entity
        else:
            current_conf = float(current.get("confidence", 0.0) or 0.0)
            entity_conf = float(entity.get("confidence", 0.0) or 0.0)
            if entity_conf > current_conf:
                selected[key] = entity
    return list(selected.values())


def canonicalize_entities(
    entities: list[dict[str, object]],
    schema_fields: list[str],
    field_descriptions: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Map extracted entities to canonical schema field names.

    Uses token overlap, containment scoring, substring detection, and
    description-token expansion (same algorithm as legacy). Threshold: 0.62.

    Unmatched entities are returned unchanged (legacy behavior: not dropped).
    When canonicalization changes the key, the normalized pre-canonical key is
    stored in metadata["raw_key"].

    Adapted from legacy canonicalize_entities; operates on plain dicts.
    """
    if not entities:
        return []
    descriptions = field_descriptions or {}
    schema_norm = [normalize_key(f) for f in schema_fields if normalize_key(f)]
    if not schema_norm:
        return list(entities)

    result: list[dict[str, object]] = []
    for entity in entities:
        raw_key = normalize_key(str(entity.get("key", "")))
        target_key = raw_key
        match_key, score = _closest_schema_key(raw_key, schema_norm, descriptions)
        if match_key and score >= 0.62:
            target_key = match_key
        metadata = dict(entity.get("metadata") or {})
        if target_key != raw_key:
            metadata["raw_key"] = raw_key
        result.append({
            **entity,
            "key": target_key,
            "metadata": metadata,
        })
    return result


# ---------------------------------------------------------------------------
# Private helpers (ported from legacy)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]


def _field_tokens(key: str, description: str) -> set[str]:
    tokens = set(_tokenize(key))
    expanded = set(tokens)
    for token in list(tokens):
        for alt in TOKEN_EQUIVALENTS.get(token, ()):
            expanded.update(_tokenize(alt))
    desc_tokens = {
        token
        for token in _tokenize(description)
        if token not in _DESC_STOPWORDS and len(token) > 2
    }
    return expanded.union(desc_tokens)


def _field_match_score(candidate: str, target: str, description: str) -> float:
    if not candidate or not target:
        return 0.0
    if candidate == target:
        return 1.0
    cand_tokens = set(_tokenize(candidate))
    target_tokens = _field_tokens(target, description)
    if not cand_tokens or not target_tokens:
        return 0.0
    overlap = len(cand_tokens & target_tokens)
    union = len(cand_tokens | target_tokens)
    containment = overlap / max(len(target_tokens), 1)
    jaccard = overlap / max(union, 1)
    score = max(containment, jaccard)
    if candidate in target or target in candidate:
        score += 0.2
    if overlap and any(t in {"id", "number", "date", "amount", "total"} for t in cand_tokens):
        score += 0.08
    return min(score, 1.0)


def _closest_schema_key(
    candidate: str,
    schema_norm: list[str],
    descriptions: dict[str, str],
) -> tuple[str | None, float]:
    best_key: str | None = None
    best_score = 0.0
    for target in schema_norm:
        score = _field_match_score(candidate, target, descriptions.get(target, ""))
        if score > best_score:
            best_score = score
            best_key = target
    return best_key, best_score
