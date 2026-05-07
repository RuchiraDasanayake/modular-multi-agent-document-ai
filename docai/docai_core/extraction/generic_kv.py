"""Fresh minimal generic key-value extraction for DocAI v2.

Curated for IDP/invoice documents. IoT-specific noise entries excluded.
Not wired into runtime — standalone utility only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field

from docai_core.extraction.normalization import (
    MISSING_VALUE_MARKERS,
    clean_candidate_value,
    normalize_key,
)

_RE_KV_COLON = re.compile(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s*[:=\-]\s*(.+)$")
_RE_KV_SPACE = re.compile(r"^([A-Za-z][A-Za-z0-9 #/&()._-]{1,40})\s{2,}(.+)$")
_RE_MULTI_KV = re.compile(
    # No digits/hyphens in label so "INV-001" is never mistaken for a label start.
    r"(?P<label>[A-Za-z][A-Za-z #/&()._]{0,39}?)\s*[:=]\s*"
    r"(?P<value>.*?)(?=(?:[A-Za-z][A-Za-z #/&()._]{0,39}?\s*[:=])|$)"
)
_RE_AMOUNT = re.compile(r"((?:\$|usd\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
_RE_BULLET_PREFIX = re.compile(r"^[\-\*•◦●○▪■□]+")
_RE_DATE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$|^\d{4}-\d{2}-\d{2}$")
_RE_AMOUNT_VALUE = re.compile(r"^[\d.,/$%\s]+$")
_RE_ID_LIKE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{2,}$")

_AMOUNT_KEYWORDS = frozenset({"total", "amount", "balance", "due", "subtotal", "tax"})

# Single-word keys that carry no IDP/invoice meaning.
# Does NOT include invoice-relevant words: date, status, type, total, subtotal, tax, balance, due.
_SINGLE_WORD_NOISE = frozenset({
    "value", "label", "code", "data", "text", "note", "item",
    "page", "line", "file", "path", "info", "mode", "size",
    "count", "list", "link", "icon", "view", "form",
    "width", "height", "depth", "length",
    "section", "header", "footer", "body",
    "group", "category", "block", "segment",
    "error", "warning",
})

_NOISE_PREFIXES = frozenset({
    "the", "a", "an", "if", "but", "and", "or",
    "so", "yet", "nor", "for", "it", "this", "that",
    "what", "how", "why", "when", "where", "who", "which",
    "here", "there", "our", "my", "your",
})

_SINGLE_VALUE_NOISE = frozenset({
    "yes", "no", "true", "false", "none", "null",
    "stop", "start", "high", "low", "medium",
})

_SENTENCE_STARTS = (
    "the ", "a ", "an ", "it ", "this ", "that ", "these ",
    "those ", "we ", "you ", "they ", "he ", "she ",
    "before ", "will ", "can ", "should ", "would ",
    "could ", "may ", "might ",
)


@dataclass(slots=True)
class KeyValueCandidate:
    key: str
    value: str
    confidence: float
    source: str = "generic_kv"
    metadata: dict[str, object] = dc_field(default_factory=dict)


def parse_kv_line(line: str) -> tuple[str, str] | None:
    """Parse a single KV line with colon/equals/dash or wide-space delimiter."""
    cleaned = line.strip()
    if not cleaned:
        return None
    match = _RE_KV_COLON.match(cleaned) or _RE_KV_SPACE.match(cleaned)
    if not match:
        return None
    key_raw = match.group(1).strip()
    val_raw = match.group(2).strip()
    if not key_raw or not val_raw or len(val_raw) > 200:
        return None
    key = normalize_key(key_raw)
    value = clean_candidate_value(val_raw)
    if not key or not value:
        return None
    return key, value


def parse_multi_kv_line(line: str) -> list[tuple[str, str]]:
    """Parse a line containing multiple KV pairs (e.g. compact invoice header rows)."""
    cleaned = line.strip()
    if not cleaned or len(re.findall(r"[:=]", cleaned)) < 2:
        return []
    pairs: list[tuple[str, str]] = []
    for m in _RE_MULTI_KV.finditer(cleaned):
        label = m.group("label").strip()
        val = m.group("value").strip().rstrip(".")
        if not label or not val or len(val) > 200:
            continue
        key = normalize_key(label)
        value = clean_candidate_value(val)
        if key and value:
            pairs.append((key, value))
    return pairs if len(pairs) >= 2 else []


def parse_amount_line(line: str) -> tuple[str, str] | None:
    """Parse amount-focused lines containing financial keywords."""
    cleaned = line.strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if not any(kw in lowered for kw in _AMOUNT_KEYWORDS):
        return None
    match = _RE_AMOUNT.search(cleaned)
    if not match:
        return None
    value = match.group(1).strip()
    prefix = cleaned[: match.start()].strip().rstrip(":")
    key = normalize_key(prefix) if prefix else "amount"
    if not key:
        key = "amount"
    return key, value


def extract_key_values(text: str) -> list[KeyValueCandidate]:
    """Extract KV candidates from plain text using deterministic heuristics.

    Applies parse_multi_kv_line first, then parse_kv_line, then parse_amount_line.
    Filters through curated noise rules and deduplicates by (key, value).
    """
    if not text or not text.strip():
        return []
    candidates: list[KeyValueCandidate] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in text.splitlines():
        line = (
            raw_line
            .replace("–", "-")
            .replace("—", "-")
            .replace("−", "-")
        )
        pairs = parse_multi_kv_line(line)
        if not pairs:
            single = parse_kv_line(line)
            pairs = [single] if single else []
        if not pairs:
            amount = parse_amount_line(line)
            pairs = [amount] if amount else []
        for pair in pairs:
            if not pair:
                continue
            key, value = pair
            if not _is_valid_candidate(key, value):
                continue
            token = (key, value)
            if token in seen:
                continue
            seen.add(token)
            candidates.append(
                KeyValueCandidate(
                    key=key,
                    value=value,
                    confidence=_score_confidence(value),
                    metadata={"source_line": raw_line.strip()},
                )
            )
    return candidates


def _is_valid_candidate(key: str, value: str) -> bool:
    if not key or not value:
        return False
    if len(key) < 2 or len(key) > 50:
        return False
    if len(value) > 180:
        return False
    key_words = key.replace("_", " ").split()
    if len(key_words) > 5:
        return False
    if len(key_words) == 1 and key_words[0] in _SINGLE_WORD_NOISE:
        return False
    if key_words and key_words[0] in _NOISE_PREFIXES:
        return False
    if sum(c.isdigit() for c in key) > 2:
        return False
    v = value.strip()
    if len(v) <= 1:
        return False
    if v.lower() in MISSING_VALUE_MARKERS:
        return False
    if _RE_BULLET_PREFIX.match(v):
        return False
    if v.startswith("[") or v.startswith("{"):
        return False
    if "->" in value or "=>" in value:
        return False
    if v.count("(") != v.count(")"):
        return False
    if len(v.split()) == 1 and v.lower() in _SINGLE_VALUE_NOISE:
        return False
    if any(v.lower().startswith(s) for s in _SENTENCE_STARTS):
        return False
    return True


def _score_confidence(value: str) -> float:
    """0.75 date | 0.72 amount | 0.70 ID-like | 0.35 long-text | 0.55 default."""
    v = value.strip()
    if _RE_DATE.match(v):
        return 0.75
    if _RE_AMOUNT_VALUE.match(v) and any(c.isdigit() for c in v):
        return 0.72
    if _RE_ID_LIKE.match(v):
        return 0.70
    if len(v.split()) > 8:
        return 0.35
    return 0.55
