from __future__ import annotations

import json
import re

from idpo.core.types import Entity

NORMALIZE_KEY_RE = re.compile(r"[^a-z0-9]+")
BULLET_PREFIX_RE = re.compile("^[\\-\\*\\u2022\\u25e6\\u25cf\\u25cb\\u25aa\\u25a0\\u25a1]+")

TOKEN_EQUIVALENTS = {
    "no": ("number",),
    "num": ("number",),
    "qty": ("quantity",),
    "amt": ("amount",),
    "addr": ("address",),
    "tel": ("telephone", "phone"),
    "inv": ("invoice",),
    "po": ("purchase", "order"),
    "dob": ("date", "birth"),
}

DESC_STOPWORDS = {
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

MISSING_VALUE_MARKERS = {
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not found",
    "-",
}


def normalize_key(raw: str) -> str:
    key = NORMALIZE_KEY_RE.sub("_", raw.strip().lower()).strip("_")
    if len(key) > 40:
        truncated = key[:40]
        last_underscore = truncated.rfind("_")
        if last_underscore > 20:
            key = truncated[:last_underscore]
        else:
            key = truncated
    return key


def clean_candidate_value(raw: str) -> str:
    value = (raw or "").strip()
    value = BULLET_PREFIX_RE.sub("", value).strip()
    value = re.sub(r"^[\-\:=#\|]+", "", value).strip()
    value = re.sub(r"\s+", " ", value)
    value = value.strip("|;,. ")
    return value


def merge_by_key(entities: list[Entity]) -> list[Entity]:
    selected: dict[str, Entity] = {}
    for entity in entities:
        key = normalize_key(entity.key)
        current = selected.get(key)
        if not current or entity.confidence > current.confidence:
            selected[key] = entity
    return list(selected.values())


def filter_to_explicit_keys(entities: list[Entity], explicit_key_set: set[str]) -> list[Entity]:
    if not explicit_key_set:
        return entities
    return [entity for entity in entities if normalize_key(entity.key) in explicit_key_set]


def canonicalize_entities(
    entities: list[Entity],
    explicit_keys: list[str],
    field_descriptions: dict[str, str],
) -> list[Entity]:
    if not entities:
        return []
    explicit_norm = [normalize_key(key) for key in explicit_keys if normalize_key(key)]
    if not explicit_norm:
        return entities

    canonicalized: list[Entity] = []
    for entity in entities:
        raw_key = normalize_key(entity.key)
        target_key = raw_key
        match_key, score = _closest_explicit_key(raw_key, explicit_norm, field_descriptions)
        if match_key and score >= 0.62:
            target_key = match_key
        metadata = dict(entity.metadata or {})
        if target_key != raw_key:
            metadata["canonicalized_from"] = raw_key
        canonicalized.append(
            Entity(
                key=target_key,
                value=entity.value,
                confidence=entity.confidence,
                page=entity.page,
                span=entity.span,
                metadata=metadata,
            )
        )
    return canonicalized


def parse_entities_response(response: str, model_name: str, source: str) -> list[Entity]:
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
        items = [
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

    entities: list[Entity] = []
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
        entities.append(
            Entity(
                key=key,
                value=value,
                confidence=confidence,
                metadata={"explicit": True, "source": source, "model": model_name},
            )
        )
    return entities


def parse_json_payload(cleaned: str) -> object | None:
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


def _salvage_entity_items(cleaned: str) -> list[dict[str, object]]:
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


def _closest_explicit_key(
    candidate_key: str,
    explicit_keys: list[str],
    field_descriptions: dict[str, str],
) -> tuple[str | None, float]:
    best_key = None
    best_score = 0.0
    for target in explicit_keys:
        score = _field_match_score(candidate_key, target, field_descriptions.get(target, ""))
        if score > best_score:
            best_score = score
            best_key = target
    return best_key, best_score


def _field_match_score(candidate: str, target: str, description: str) -> float:
    if not candidate or not target:
        return 0.0
    if candidate == target:
        return 1.0

    cand_tokens = set(_tokenize(candidate))
    target_tokens = _field_tokens(target, description)
    if not cand_tokens or not target_tokens:
        return 0.0

    overlap = len(cand_tokens.intersection(target_tokens))
    union = len(cand_tokens.union(target_tokens))
    containment = overlap / max(len(target_tokens), 1)
    jaccard = overlap / max(union, 1)
    score = max(containment, jaccard)

    if candidate in target or target in candidate:
        score += 0.2
    if overlap and any(token in {"id", "number", "date", "amount", "total"} for token in cand_tokens):
        score += 0.08
    return min(score, 1.0)


def _field_tokens(key: str, description: str) -> set[str]:
    tokens = set(_tokenize(key))
    expanded = set(tokens)
    for token in list(tokens):
        for alt in TOKEN_EQUIVALENTS.get(token, ()):
            expanded.update(_tokenize(alt))
    desc_tokens = {
        token
        for token in _tokenize(description)
        if token not in DESC_STOPWORDS and len(token) > 2
    }
    return expanded.union(desc_tokens)


def _tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]
