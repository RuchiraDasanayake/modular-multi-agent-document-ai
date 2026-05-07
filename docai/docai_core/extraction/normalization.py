"""Deterministic text/key/value normalization utilities for structured extraction.

Salvaged from legacy idpo/agents/extraction_parsing.py.
Not yet wired into any runtime pipeline.
"""

from __future__ import annotations

import re

_NORMALIZE_KEY_RE = re.compile(r"[^a-z0-9]+")
_BULLET_PREFIX_RE = re.compile(
    "^[\\-\\*•◦●○▪■□]+"
)

TOKEN_EQUIVALENTS: dict[str, tuple[str, ...]] = {
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

MISSING_VALUE_MARKERS: frozenset[str] = frozenset({
    "",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not found",
    "-",
})


def normalize_key(raw: str) -> str:
    """Normalise a field key to a lowercase underscore-delimited identifier.

    Applies legacy truncation: if the result exceeds 40 chars, cut at the last
    underscore past position 20; otherwise hard-truncate at 40.
    TOKEN_EQUIVALENTS is NOT applied here — that belongs in canonicalization.
    """
    key = _NORMALIZE_KEY_RE.sub("_", raw.strip().lower()).strip("_")
    if len(key) > 40:
        truncated = key[:40]
        last_underscore = truncated.rfind("_")
        if last_underscore > 20:
            key = truncated[:last_underscore]
        else:
            key = truncated
    return key


def clean_candidate_value(raw: str) -> str:
    """Clean a raw extracted value: strip whitespace, remove bullet/list prefixes,
    collapse internal whitespace, and strip trailing punctuation."""
    value = (raw or "").strip()
    value = _BULLET_PREFIX_RE.sub("", value).strip()
    value = re.sub(r"^[\-\:=#\|]+", "", value).strip()
    value = re.sub(r"\s+", " ", value)
    value = value.strip("|;,. ")
    return value
