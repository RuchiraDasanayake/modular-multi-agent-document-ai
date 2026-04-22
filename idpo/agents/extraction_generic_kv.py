from __future__ import annotations

import re

from idpo.agents.extraction_parsing import normalize_key
from idpo.core.types import Document, Entity

_RE_KV_COLON = re.compile(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=\-]\s*(.+)$")
_RE_KV_SPACE = re.compile(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s{2,}(.+)$")
_RE_MULTI_KV = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=]\s*"
    r"(?P<value>.*?)(?=(?:[A-Za-z][A-Za-z0-9 #/&()._-]{1,40}\s*[:=])|$)"
)
_RE_AMOUNT = re.compile(r"((?:\$|usd\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_RE_BULLET_PREFIX = re.compile(r"^[\-\*\u2022\u25e6\u25cf\u25cb\u25aa\u25a0\u25a1]+")

_SINGLE_WORD_NOISE = {
    "member", "shows", "role", "logic", "type", "name",
    "value", "label", "model", "sensor", "step", "code",
    "data", "text", "note", "item", "page", "line",
    "file", "path", "info", "mode", "size", "count",
    "list", "link", "icon", "view", "form", "test",
    "soil", "temp", "light", "tank", "water", "task",
    "software", "hardware", "physical", "widget", "color",
    "alert", "prediction", "reason", "scenario", "output",
    "input", "transmission", "execution", "rain", "system",
    "actuation", "run", "class", "prob", "context",
    "phase", "stage", "layer", "source", "target",
    "status", "action", "result", "process", "method",
    "signal", "event", "state", "table", "field",
    "section", "header", "footer", "title", "body",
    "group", "category", "block", "segment", "unit",
    "level", "scope", "range", "margin", "padding",
    "width", "height", "depth", "weight", "length",
    "measure", "metric", "factor", "ratio", "scale",
    "device", "module", "component", "element", "object",
    "feature", "option", "setting", "config", "param",
    "error", "warning", "debug", "trace", "log",
}

_NOISE_PREFIXES = {
    "e", "o", "the", "a", "an", "if", "but", "and", "or",
    "so", "yet", "nor", "for", "it", "this", "that", "what",
    "how", "why", "when", "where", "who", "which", "result",
    "note", "example", "step", "concept", "twist",
    "s_special", "e_logic", "e_why", "shows", "tells",
    "circular", "line", "sun", "member", "role",
    "sensing", "context", "run", "actuation", "execution",
    "members", "scenario", "watering", "model", "rain",
    "system", "here", "there", "where", "our", "my",
}

_SINGLE_VALUE_NOISE = {
    "sensor", "model", "label", "value", "moisture",
    "humidity", "resistor", "gauge", "graph", "icon",
    "yes", "no", "true", "false", "none", "null",
    "stop", "start", "high", "low", "medium",
}

_SENTENCE_STARTS = (
    "the ", "a ", "an ", "it ", "this ", "that ", "these ",
    "those ", "we ", "you ", "they ", "he ", "she ", "normal ",
    "before ", "your ", "shows ", "tells ", "will ", "can ",
    "should ", "would ", "could ", "may ", "might ",
    "set ", "make ", "find ", "get ", "put ", "do ",
    "write ", "read ", "build ", "create ", "handle ",
    "large ", "small ", "how ", "what ", "if ", "when ",
    "○ ", "● ", "■ ",
)


def generic_kv_entities(
    doc: Document,
    span_for_line_fn,
) -> list[Entity]:
    entities: list[Entity] = []
    for page in doc.pages:
        for line in page.text.splitlines():
            normalized = line.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
            parsed_pairs = parse_multi_kv_line(normalized)
            if not parsed_pairs:
                parsed = parse_kv_line(normalized)
                parsed_pairs = [parsed] if parsed else []
            if not parsed_pairs:
                parsed = parse_amount_line(normalized)
                parsed_pairs = [parsed] if parsed else []
            for parsed in parsed_pairs:
                if not parsed:
                    continue
                key, value = parsed
                if not key or not value:
                    continue

                if len(key) < 3 or len(key) > 50:
                    continue
                if len(value) > 180:
                    continue
                key_words = key.replace("_", " ").split()
                if len(key_words) > 5:
                    continue
                if len(key_words) == 1 and key_words[0].lower() in _SINGLE_WORD_NOISE:
                    continue
                first_word = key_words[0].lower() if key_words else ""
                if first_word in _NOISE_PREFIXES:
                    continue
                digit_count = sum(char.isdigit() for char in key)
                if digit_count > 2:
                    continue

                if len(value.strip()) <= 1:
                    continue
                value_stripped = value.strip()
                if _RE_BULLET_PREFIX.match(value_stripped):
                    continue
                if value_stripped.startswith("[") or value_stripped.startswith("{"):
                    continue
                if "->" in value or "=>" in value:
                    continue
                if value_stripped.endswith('"') and not value_stripped.startswith('"'):
                    continue
                if value_stripped.startswith('"') and not value_stripped.endswith('"'):
                    continue
                if value_stripped.endswith(","):
                    value = value_stripped = value_stripped[:-1].strip()
                    if not value_stripped:
                        continue
                if value_stripped.count("(") != value_stripped.count(")"):
                    continue
                value_words = value.strip().split()
                if len(value_words) == 1 and value_words[0].lower() in _SINGLE_VALUE_NOISE:
                    continue
                value_lower = value.lower().strip()
                if any(value_lower.startswith(s) for s in _SENTENCE_STARTS):
                    continue
                if value.startswith('"') and value.endswith('"'):
                    inner = value[1:-1].strip()
                    if len(inner.split()) <= 4:
                        continue

                confidence = 0.55
                if re.match(r"^[\d.,/$%]+$", value.strip()):
                    confidence = 0.72
                elif re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", value.strip()):
                    confidence = 0.75
                elif re.match(r"^[A-Z0-9][A-Z0-9-]{2,}$", value.strip()):
                    confidence = 0.70
                elif len(value.split()) > 8:
                    confidence = 0.35
                span = span_for_line_fn(page.text, line, value)
                entities.append(
                    Entity(
                        key=key,
                        value=value,
                        confidence=confidence,
                        page=page.number,
                        span=span,
                        metadata={"generic_kv": True, "evidence": value},
                    )
                )
    return entities


def parse_kv_line(line: str) -> tuple[str, str] | None:
    cleaned = line.strip()
    if not cleaned:
        return None
    match = _RE_KV_COLON.match(cleaned)
    if not match:
        match = _RE_KV_SPACE.match(cleaned)
    if not match:
        return None
    key_part = match.group(1).strip()
    value_part = match.group(2).strip()
    if not key_part or not value_part or len(value_part) > 200:
        return None
    return normalize_key(key_part), value_part


def parse_multi_kv_line(line: str) -> list[tuple[str, str]]:
    cleaned = line.strip()
    if not cleaned:
        return []
    pairs: list[tuple[str, str]] = []
    for match in _RE_MULTI_KV.finditer(cleaned):
        label = match.group("label").strip()
        value = match.group("value").strip().strip(".")
        if not label or not value:
            continue
        if len(value) > 200:
            continue
        pairs.append((normalize_key(label), value))
    return pairs


def parse_amount_line(line: str) -> tuple[str, str] | None:
    cleaned = line.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if not any(token in lowered for token in ["total", "amount", "balance", "due", "subtotal", "invoice total"]):
        return None
    match = _RE_AMOUNT.search(cleaned)
    if not match:
        return None
    value = match.group(1).strip()
    prefix = cleaned[: match.start()].strip()
    key = normalize_key(prefix) if prefix else "amount"
    return key, value
