from __future__ import annotations

import re
from typing import Sequence

from idpo.agents.extraction_parsing import MISSING_VALUE_MARKERS, normalize_key
from idpo.core.types import Document, Entity

_AMOUNT_RE = re.compile(r"((?:\$|usd\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")


def match_rule_in_pages(doc: Document, pattern: str) -> tuple[str | None, int | None, tuple[int, int] | None]:
    for page in doc.pages:
        match = re.search(pattern, page.text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            return value, page.number, match.span(1)
    return None, None, None


def extract_explicit_entities(
    doc: Document,
    explicit_keys: list[str],
    generic_entities: list[Entity],
    extraction_rules: Sequence[object],
    policy_id: str | None,
    model_name: str | None,
) -> list[Entity]:
    rule_map = {
        normalize_key(str(getattr(rule, "key", ""))): rule
        for rule in extraction_rules
        if normalize_key(str(getattr(rule, "key", "")))
    }
    explicit_map: dict[str, Entity] = {}
    for key in explicit_keys:
        rule = rule_map.get(key)
        if rule:
            match_value, page_num, span = match_rule_in_pages(doc, str(getattr(rule, "pattern", "")))
            if match_value:
                _pick_best(
                    explicit_map,
                    Entity(
                        key=str(getattr(rule, "key", key)),
                        value=match_value,
                        confidence=0.82,
                        page=page_num,
                        span=span,
                        metadata={
                            "explicit": True,
                            "source": "rule",
                            "label": getattr(rule, "label", None),
                            "policy_id": policy_id,
                            "model": model_name,
                        },
                    ),
                )

    explicit_set = {normalize_key(key) for key in explicit_keys}
    for entity in generic_entities:
        if normalize_key(entity.key) in explicit_set:
            _pick_best(
                explicit_map,
                Entity(
                    key=entity.key,
                    value=entity.value,
                    confidence=max(entity.confidence, 0.62),
                    page=entity.page,
                    span=entity.span,
                    metadata={**(entity.metadata or {}), "explicit": True, "source": "generic_kv"},
                ),
            )
    return list(explicit_map.values())


def is_valid_candidate_value(value: str) -> bool:
    if not value:
        return False
    lowered = value.lower().strip()
    if lowered in MISSING_VALUE_MARKERS:
        return False
    if len(value) < 2 or len(value) > 180:
        return False
    if value.endswith(":"):
        return False
    if value.count(" ") == 0 and re.fullmatch(r"[A-Za-z]+", value) and len(value) <= 2:
        return False
    return True


def best_generic_match(tokens: list[str], generic_by_key: dict[str, list[Entity]]) -> Entity | None:
    if not tokens:
        return None
    best = None
    best_score = 0.0
    token_set = set(tokens)
    for key, entities in generic_by_key.items():
        key_tokens = set(tokenize(key))
        if not key_tokens:
            continue
        overlap = token_set.intersection(key_tokens)
        score = len(overlap) / max(len(token_set), 1)
        if key in token_set or any(tok in key for tok in token_set):
            score += 0.15
        if score > best_score:
            best_score = score
            best = max(entities, key=lambda item: item.confidence)
    if best_score >= 0.55:
        return best
    return None


def regex_fallback(key: str, tokens: list[str], text: str) -> Entity | None:
    lowered = " ".join(tokens)
    if any(token in lowered for token in ["amount", "total", "balance", "due", "price", "cost"]):
        candidates = re.findall(
            r"(?:total|amount|balance|due|subtotal|tax|invoice\s+total)[^\d\n]{0,18}"
            r"((?:\$|usd\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
            text,
            re.IGNORECASE,
        )
        if candidates:
            best = max(
                candidates,
                key=lambda item: float(item.replace(",", "").replace("usd", "").replace("$", "") or 0),
            )
            return Entity(
                key=key,
                value=best.strip(),
                confidence=0.45,
                metadata={"explicit": True, "source": "schema_regex", "rule": "amount"},
            )
        currency = re.findall(r"(?:\$|usd\s*)\d{1,3}(?:,\d{3})*(?:\.\d{2})?", text, re.IGNORECASE)
        if currency:
            best = max(
                currency,
                key=lambda item: float(item.replace(",", "").replace("usd", "").replace("$", "") or 0),
            )
            return Entity(
                key=key,
                value=best.strip(),
                confidence=0.4,
                metadata={"explicit": True, "source": "schema_regex", "rule": "amount_any"},
            )
    if any(token in lowered for token in ["date", "issued", "invoice_date", "due_date"]):
        date_match = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
        if not date_match:
            date_match = re.search(
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
                text,
                re.IGNORECASE,
            )
        if not date_match:
            date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
        if date_match:
            return Entity(
                key=key,
                value=date_match.group(0),
                confidence=0.45,
                metadata={"explicit": True, "source": "schema_regex", "rule": "date"},
            )
    if any(token in lowered for token in ["invoice", "id", "number", "reference"]):
        id_match = re.search(r"\b[A-Z]{0,4}[\-#]?\d{3,}[A-Z0-9-]*\b", text)
        if not id_match:
            id_match = re.search(r"\b[A-Z0-9-]{5,}\b", text)
        if id_match:
            return Entity(
                key=key,
                value=id_match.group(0),
                confidence=0.42,
                metadata={"explicit": True, "source": "schema_regex", "rule": "id"},
            )
    if any(token in lowered for token in ["fax", "phone", "telephone", "tel"]):
        phone_pattern = r"\(?(\d{3})\)?[-.\s]*(\d{3})[-.\s]*(\d{4})"
        fax_match = None
        if "fax" in lowered:
            fax_match = re.search(r"fax[^\d]{0,6}" + phone_pattern, text, re.IGNORECASE)
        if fax_match:
            number = "-".join(fax_match.groups())
            return Entity(
                key=key,
                value=number,
                confidence=0.45,
                metadata={"explicit": True, "source": "schema_regex", "rule": "fax"},
            )
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            number = "-".join(phone_match.groups())
            return Entity(
                key=key,
                value=number,
                confidence=0.42,
                metadata={"explicit": True, "source": "schema_regex", "rule": "phone"},
            )
    return None


def tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"[^a-z0-9]+", text.lower()) if part]


def _pick_best(selected: dict[str, Entity], candidate: Entity) -> None:
    current = selected.get(candidate.key)
    if not current or candidate.confidence > current.confidence:
        selected[candidate.key] = candidate
