from __future__ import annotations

import re

from idpo.agents.extraction_parsing import DESC_STOPWORDS, TOKEN_EQUIVALENTS
from idpo.agents.extraction_rules import tokenize
from idpo.core.types import Document, Entity

_TITLE_BULLETS = ("●", "○", "■", "•", "-", "*")
_STRIP_BULLETS_RE = re.compile(r"[○●■□▪▸►▶•]")
            

def span_for_line(page_text: str, line: str, value: str) -> tuple[int, int] | None:
    start = page_text.find(line)
    if start == -1:
        return None
    value_start = line.find(value)
    if value_start == -1:
        return None
    span_start = start + value_start
    return (span_start, span_start + len(value))


def smart_field_extract(key: str, doc: Document, text: str) -> Entity | None:
    key_lower = key.lower()

    if any(tok in key_lower for tok in ["title", "project_name", "document_name"]):
        title_match = re.search(
            r"(?:project\s+title|title|project\s+name|document\s+title)\s*[:=\-]\s*(.+)",
            text,
            re.IGNORECASE,
        )
        if title_match:
            val = title_match.group(1).strip()
            if 2 < len(val) < 100:
                return Entity(
                    key=key,
                    value=val,
                    confidence=0.80,
                    metadata={"explicit": True, "source": "smart_heuristic"},
                )
        if doc.pages:
            first_page_text = doc.pages[0].text
            for line in first_page_text.splitlines():
                line = line.strip()
                if line and len(line) > 2 and len(line) < 80 and len(line.split()) <= 10:
                    if not line[0].isdigit() and not line.startswith(_TITLE_BULLETS):
                        return Entity(
                            key=key,
                            value=line,
                            confidence=0.70,
                            metadata={"explicit": True, "source": "smart_heuristic", "rule": "first_line"},
                        )
                    break
        if doc.doc_id and len(doc.doc_id) > 2:
            clean_name = re.sub(r"[_-]", " ", doc.doc_id).strip()
            if clean_name:
                return Entity(
                    key=key,
                    value=clean_name,
                    confidence=0.60,
                    metadata={"explicit": True, "source": "smart_heuristic", "rule": "filename"},
                )

    if any(tok in key_lower for tok in ["member", "author", "team", "contributor", "participant"]):
        members_match = re.search(
            r"(?:team\s+members?|members?|authors?|prepared\s+by|contributors?|participants?)\s*[:=\-]\s*(.+?)(?:\n\n|\n(?=[A-Z][a-z]+\s*:)|\Z)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if members_match:
            raw_val = members_match.group(1).strip()
            cleaned = _STRIP_BULLETS_RE.sub("", raw_val)
            cleaned = re.sub(r"\n+", ", ", cleaned).strip(", ")
            if 2 < len(cleaned) < 300:
                return Entity(
                    key=key,
                    value=cleaned,
                    confidence=0.75,
                    metadata={"explicit": True, "source": "smart_heuristic"},
                )
        member_lines = re.findall(r"Member\s*\d+\s*[:=\-]\s*(.+)", text, re.IGNORECASE)
        if member_lines:
            val = ", ".join(m.strip() for m in member_lines)
            if 2 < len(val) < 300:
                return Entity(
                    key=key,
                    value=val,
                    confidence=0.70,
                    metadata={"explicit": True, "source": "smart_heuristic"},
                )

    if any(tok in key_lower for tok in ["supervisor", "advisor", "professor", "mentor", "instructor"]):
        supervisor_match = re.search(
            r"(?:supervisor|advisor|professor|mentor|instructor|supervised\s+by|advised\s+by)\s*[:=\-]\s*(.+)",
            text,
            re.IGNORECASE,
        )
        if supervisor_match:
            val = supervisor_match.group(1).strip()
            val = _STRIP_BULLETS_RE.sub("", val).strip()
            if 2 < len(val) < 100:
                return Entity(
                    key=key,
                    value=val,
                    confidence=0.80,
                    metadata={"explicit": True, "source": "smart_heuristic"},
                )

    if any(tok in key_lower for tok in ["date", "submitted", "created", "issued"]):
        date_match = re.search(
            r"(?:date|submitted|created|issued)\s*[:=\-]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
            text,
            re.IGNORECASE,
        )
        if date_match:
            return Entity(
                key=key,
                value=date_match.group(1).strip(),
                confidence=0.78,
                metadata={"explicit": True, "source": "smart_heuristic"},
            )

    if any(tok in key_lower for tok in ["course", "subject", "module", "class_name"]):
        course_match = re.search(
            r"(?:course|subject|module|class)\s*(?:name|code|number)?\s*[:=\-]\s*(.+)",
            text,
            re.IGNORECASE,
        )
        if course_match:
            val = course_match.group(1).strip()
            if 2 < len(val) < 100:
                return Entity(
                    key=key,
                    value=val,
                    confidence=0.75,
                    metadata={"explicit": True, "source": "smart_heuristic"},
                )

    return None


def extract_by_label_anchor(
    key: str,
    description: str,
    doc: Document,
    clean_candidate_value_fn,
    is_valid_candidate_value_fn,
) -> Entity | None:
    variants = field_label_variants(key, description)
    if not variants:
        return None

    for page in doc.pages:
        lines = page.text.splitlines()
        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()
            if not line or len(line) > 240:
                continue
            for label in variants:
                escaped = re.escape(label)
                inline = re.search(
                    rf"(?i)\b{escaped}\b\s*(?:[:=\-#]|is)?\s*(.+)$",
                    line,
                )
                if inline:
                    value = clean_candidate_value_fn(inline.group(1))
                    if is_valid_candidate_value_fn(value):
                        span = span_for_line(page.text, raw_line, value)
                        return Entity(
                            key=key,
                            value=value,
                            confidence=0.68,
                            page=page.number,
                            span=span,
                            metadata={"explicit": True, "source": "label_anchor"},
                        )

                label_only = re.fullmatch(rf"(?i){escaped}\s*[:=\-#]?\s*", line)
                if label_only and idx + 1 < len(lines):
                    next_raw = lines[idx + 1]
                    next_value = clean_candidate_value_fn(next_raw)
                    if is_valid_candidate_value_fn(next_value):
                        span = span_for_line(page.text, next_raw, next_value)
                        return Entity(
                            key=key,
                            value=next_value,
                            confidence=0.64,
                            page=page.number,
                            span=span,
                            metadata={"explicit": True, "source": "label_anchor_next_line"},
                        )
    return None


def field_label_variants(key: str, description: str) -> list[str]:
    base_tokens = tokenize(key)
    if not base_tokens:
        return []
    variants = {" ".join(base_tokens)}

    for idx, token in enumerate(base_tokens):
        for alt in TOKEN_EQUIVALENTS.get(token, ()):
            alt_tokens = list(base_tokens)
            alt_tokens[idx : idx + 1] = tokenize(alt)
            variants.add(" ".join(alt_tokens))

    if "number" in base_tokens:
        variants.add(" ".join("no" if tok == "number" else tok for tok in base_tokens))
        variants.add(" ".join("#" if tok == "number" else tok for tok in base_tokens))

    if description:
        desc_tokens = [
            token
            for token in tokenize(description)
            if token not in DESC_STOPWORDS and len(token) > 2
        ]
        if desc_tokens:
            variants.add(" ".join(desc_tokens[:4]))

    cleaned = [item.strip() for item in variants if item and len(item.split()) <= 5]
    cleaned.sort(key=len, reverse=True)
    return cleaned[:12]
