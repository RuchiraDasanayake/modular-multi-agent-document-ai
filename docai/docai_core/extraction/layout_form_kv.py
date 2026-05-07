"""Layout-aware form key-value extraction for scanned forms.

When generic line-based KV extraction fails to find a field value,
this module uses conservative heuristics to find label-adjacent answer text
in plain-text OCR output.

Handles spatial form patterns:
  Label\n
  Answer

  Label    Answer  (wide-space separated)

  Label: Answer

Uses text-window and proximity heuristics. Never hallucinate.
Only returns a value if candidate text is found near the label.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class FormKVCandidate(NamedTuple):
    """A candidate field value extracted via layout-aware heuristics."""
    key: str
    value: str
    confidence: float
    source: str = "layout_form_kv"
    evidence_text: str = ""


def extract_layout_aware_kv(
    raw_text: str,
    field_name: str,
    aliases: list[str],
) -> FormKVCandidate | None:
    """Extract a field value using layout-aware heuristics.

    Args:
        raw_text: Full plain-text OCR output from document
        field_name: Schema field name (e.g., "recipient")
        aliases: Field aliases to search for (e.g., ["to", "recipient"])

    Returns:
        FormKVCandidate if a plausible value is found, None otherwise.
        Never returns a value if unsure.
    """
    if not raw_text or not raw_text.strip():
        return None

    if not aliases:
        return None

    lines = raw_text.split("\n")

    for alias in aliases:
        # Try same-line KV first (label: value)
        candidate = _try_same_line_kv(lines, alias)
        if candidate:
            return candidate

        # Try next-line answer (label on line N, answer on line N+1)
        candidate = _try_next_line_answer(lines, alias)
        if candidate:
            return candidate

        # Try right-aligned answer (label followed by whitespace then answer)
        candidate = _try_right_aligned_answer(lines, alias)
        if candidate:
            return candidate

    return None


def _try_same_line_kv(lines: list[str], alias: str) -> FormKVCandidate | None:
    """Try to extract value from same line as label using colon/equals/dash."""
    label_pattern = re.compile(
        rf"^\s*{re.escape(alias)}\s*[:=\-]\s*(.+)$",
        re.IGNORECASE
    )

    for line in lines:
        match = label_pattern.match(line.strip())
        if match:
            value = match.group(1).strip()
            if value and len(value) < 200 and not _is_noise_value(value):
                return FormKVCandidate(
                    key=alias,
                    value=value,
                    confidence=0.8,
                    source="layout_form_kv_same_line",
                    evidence_text=line.strip(),
                )
    return None


def _try_next_line_answer(lines: list[str], alias: str) -> FormKVCandidate | None:
    """Try to extract value from next line after label match.

    Pattern:
        Label
        Answer
    """
    label_pattern = re.compile(
        rf"^\s*{re.escape(alias)}\s*$",
        re.IGNORECASE
    )

    for i, line in enumerate(lines):
        if label_pattern.match(line.strip()):
            # Found label on its own line. Check next line.
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Candidate answer must be:
                # - non-empty
                # - not another label (doesn't end with :)
                # - not a known label itself
                # - reasonable length
                if (next_line and
                    len(next_line) < 200 and
                    not next_line.endswith(":") and
                    not next_line.endswith("=") and
                    not _is_noise_value(next_line) and
                    not _looks_like_label(next_line)):

                    return FormKVCandidate(
                        key=alias,
                        value=next_line,
                        confidence=0.7,
                        source="layout_form_kv_next_line",
                        evidence_text=f"{line.strip()}\n{next_line}",
                    )
    return None


def _try_right_aligned_answer(lines: list[str], alias: str) -> FormKVCandidate | None:
    """Try to extract value from same line as label, right side.

    Pattern:
        Label       Value  (2+ spaces between)
    """
    # Match label followed by 2+ spaces, then capture the rest
    pattern = re.compile(
        rf"^\s*{re.escape(alias)}\s{{2,}}(.+)$",
        re.IGNORECASE
    )

    for line in lines:
        match = pattern.match(line.strip())
        if match:
            value = match.group(1).strip()
            if (value and
                len(value) < 200 and
                not _is_noise_value(value) and
                not _looks_like_label(value)):

                return FormKVCandidate(
                    key=alias,
                    value=value,
                    confidence=0.65,
                    source="layout_form_kv_right_aligned",
                    evidence_text=line.strip(),
                )
    return None


def _is_noise_value(value: str) -> bool:
    """Check if value is likely noise/non-semantic."""
    if not value:
        return True

    # Common noise patterns
    noise_values = {
        "yes", "no", "true", "false", "n/a", "na", "none", "null",
        "x", "o", "-", "--", ":", "=", "...", "?", "!",
    }

    if value.lower() in noise_values:
        return True

    # Single char (except numbers)
    if len(value) == 1 and not value.isdigit():
        return True

    # All punctuation
    if all(not c.isalnum() for c in value):
        return True

    return False


def _looks_like_label(text: str) -> bool:
    """Check if text looks like a field label rather than a value.

    Labels typically:
    - End with : or =
    - Contain common label words
    - Are relatively short and specific
    """
    if text.endswith(":") or text.endswith("="):
        return True

    lower = text.lower()

    label_indicators = {
        "name", "date", "address", "phone", "email", "amount",
        "total", "subtotal", "tax", "invoice", "date:",
        "cc:", "recipient:", "sender:", "from:", "to:",
    }

    return any(ind in lower for ind in label_indicators)
