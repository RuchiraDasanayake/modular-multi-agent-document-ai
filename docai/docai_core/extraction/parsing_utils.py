"""JSON parsing and entity salvage utilities for structured extraction.

Salvaged from legacy idpo/agents/extraction_parsing.py.
Not yet wired into any runtime pipeline.

Adaptation from legacy: parse_entities_response returns list[dict[str, object]]
instead of list[Entity]. Each dict has keys: key, value, confidence, metadata.
"""

from __future__ import annotations

import json

from docai_core.extraction.normalization import (
    MISSING_VALUE_MARKERS,
    clean_candidate_value,
    normalize_key,
)


def parse_json_payload(cleaned: str) -> object | None:
    """Parse a JSON payload from text, tolerating embedded and stray surrounding content.

    Tries three passes:
      1. Direct json.loads on the full string.
      2. Extract the outermost {...} and parse that.
      3. Extract the outermost [...] and parse that.

    Returns the parsed Python value (dict, list, etc.) or None on failure.
    Does NOT strip markdown fences — callers (e.g. parse_entities_response) do that.
    """
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    object_start = cleaned.find("{")
    object_end = cleaned.rfind("}")
    if object_start != -1 and object_end > object_start:
        candidate = cleaned[object_start : object_end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    array_start = cleaned.find("[")
    array_end = cleaned.rfind("]")
    if array_start != -1 and array_end > array_start:
        candidate = cleaned[array_start : array_end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def parse_entities_response(
    response: str,
    model_name: str,
    source: str,
) -> list[dict[str, object]]:
    """Salvage entity-like key/value pairs from a model response string.

    Accepts these shapes (as legacy does):
      - Flat dict:       {"invoice_number": "INV-001"}
      - Entities array:  {"entities": [{"key": "invoice_number", "value": "INV-001"}]}
      - Bare array:      [{"key": "invoice_number", "value": "INV-001"}]
      - Markdown-fenced: ```json\\n{...}\\n```

    Returns list[dict] with keys: key, value, confidence, metadata.
    Legacy returned list[Entity]; this function returns plain dicts instead.
    """
    cleaned = response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    if not cleaned:
        return []

    parsed = parse_json_payload(cleaned)
    if parsed is None:
        salvaged_items = _salvage_entity_items(cleaned)
        if not salvaged_items:
            return []
        parsed = {"entities": salvaged_items}

    if isinstance(parsed, dict) and "entities" not in parsed:
        items: object = [
            {"key": key, "value": value, "confidence": 0.65}
            for key, value in parsed.items()
            if isinstance(value, (str, int, float, bool))
        ]
    else:
        items = parsed.get("entities", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(items, dict):
        if {"key", "value"}.issubset(items.keys()):
            items = [items]
        else:
            items = [
                {"key": key, "value": value, "confidence": 0.65}
                for key, value in items.items()
                if isinstance(value, (str, int, float, bool))
            ]

    result: list[dict[str, object]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        key = normalize_key(str(item.get("key", "")).strip())
        value = clean_candidate_value(str(item.get("value", "")))
        if (not key or not value) and isinstance(item, dict):
            fallback_fields = [
                (normalize_key(str(raw_key).strip()), raw_value)
                for raw_key, raw_value in item.items()
                if str(raw_key).strip().lower() not in {"key", "value", "confidence"}
                and isinstance(raw_value, (str, int, float, bool))
            ]
            if len(fallback_fields) == 1:
                key, raw_value = fallback_fields[0]
                value = clean_candidate_value(str(raw_value))
        if not key or not value or value.lower() in MISSING_VALUE_MARKERS:
            continue
        try:
            confidence = float(item.get("confidence", 0.7))
        except Exception:
            confidence = 0.7
        confidence = max(0.0, min(confidence, 1.0))
        result.append({
            "key": key,
            "value": value,
            "confidence": confidence,
            "metadata": {"explicit": True, "source": source, "model": model_name},
        })
    return result


def _salvage_entity_items(cleaned: str) -> list[dict[str, object]]:
    """Character-level scanner that extracts valid JSON objects from inside a
    partially-broken JSON array. Used as last-resort salvage when standard
    parsing fails."""
    array_start = cleaned.find("[")
    if array_start == -1:
        return []
    items: list[dict[str, object]] = []
    depth = 0
    obj_start = -1
    in_string = False
    escaped = False
    for index, ch in enumerate(cleaned[array_start:], start=array_start):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                obj_start = index
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and obj_start != -1:
                candidate = cleaned[obj_start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except Exception:
                    obj_start = -1
                    continue
                if isinstance(parsed, dict):
                    items.append(parsed)
                obj_start = -1
        elif ch == "]" and depth == 0:
            break
    return items
