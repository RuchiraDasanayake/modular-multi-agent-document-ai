"""
Garbled-PDF text detection and correction.

Many PDFs (especially financial reports from certain generators) use custom font
encodings where the ToUnicode CMap maps standard Latin glyphs to obscure Unicode
codepoints in the Latin Extended-A/B range (U+0100-U+024F) and Greek block
(U+0370-U+03FF for digits).  When a PDF text extractor (pypdf, pdfplumber, etc.)
decodes the text using the broken CMap, the result is visually garbled but
structurally consistent — making it possible to reverse the mapping.

This module provides:
  - ``is_garbled(text)``  – detect garbled text via Unicode range analysis
  - ``degarble(text)``    – apply character/ligature substitution to recover text
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Ligature map  (multi-char replacements — applied FIRST)
# ---------------------------------------------------------------------------
_LIGATURES: dict[str, str] = {
    "\u0138": "ffi",   # ĸ
    "\u012a": "ff",    # Ī  (some fonts)
    "\u012b": "ff",    # ī
    "\u012e": "fi",    # Į
    "\u019f": "ti",    # Ɵ
    "\u014c": "ft",    # Ō
    "\u01a9": "tt",    # Ʃ
    "\u0147": "fl",    # Ň  (some fonts)
    "\u0192": "fl",    # ƒl – rare
}

# ---------------------------------------------------------------------------
# Single-character map  (garbled codepoint → ASCII)
# ---------------------------------------------------------------------------
_CHAR_MAP: dict[str, str] = {
    # --- lowercase letters ---
    "\u0102": "a",   # Ă
    "\u010f": "b",   # ď
    "\u0110": "c",   # Đ
    "\u011a": "d",   # Ě
    "\u011e": "e",   # Ğ
    "\u0128": "f",   # Ĩ
    "\u0150": "g",   # Ő
    "\u015a": "h",   # Ś
    "\u015d": "i",   # ŝ
    "\u0169": "j",   # ũ
    "\u016c": "k",   # Ŭ
    "\u016f": "l",   # ů
    "\u0175": "m",   # ŵ
    "\u0176": "n",   # Ŷ
    "\u017d": "o",   # Ž
    "\u0189": "p",   # Ɖ
    "\u018a": "p",   # Ɗ  (variant)
    "\u018b": "q",   # Ƌ
    "\u018c": "r",   # ƌ
    "\u0190": "s",   # Ɛ  (open E → s in this encoding)
    "\u019a": "t",   # ƚ
    "\u01b5": "u",   # Ƶ
    "\u01c0": "v",   # ǀ
    "\u01c1": "w",   # ǁ
    "\u01c6": "x",   # ǆ
    "\u01c7": "y",   # Ǉ  (LJ digraph → y)
    "\u01cc": "z",   # ǌ

    # --- uppercase (ASCII symbols used as capital letters) ---
    # These are only safe to remap inside garbled regions.
    # We store them separately and apply contextually.
}

# ASCII symbols that map to uppercase letters inside garbled text.
_UPPER_MAP: dict[str, str] = {
    "&": "F",
    "/": "I",
    "^": "S",
    ">": "L",
    ";": "(",
}

# ASCII *letters/digits* used as uppercase (ambiguous — only apply in garbled runs)
_UPPER_ALPHA_MAP: dict[str, str] = {
    "d": "T",
    "E": "N",
    "K": "O",
    "W": "P",
    "Z": "R",
    "D": "M",
    "'": "G",
    "\u2019": "G",
}

# --- Greek digits ---
_DIGIT_MAP: dict[str, str] = {
    "\u03ec": "0",   # Ϭ
    "\u03ed": "1",   # ϭ
    "\u03ee": "2",   # Ϯ
    "\u03ef": "3",   # ϯ
    "\u03f0": "4",   # ϰ
    "\u03f1": "5",   # ϱ
    "\u03f2": "6",   # ϲ
    "\u03f3": "7",   # ϳ
    "\u03f4": "8",   # ϴ
    "\u03f5": "9",   # ϵ
}

# --- Garbled punctuation ---
_PUNCT_MAP: dict[str, str] = {
    "\u0355": ",",   # ͕ (combining below)
    "\u0359": ",",   # ͙
    "\u035b": "'",   # ͛
    "\u0358": ".",   # ͘
    "\u037f": ")",   # Ϳ
}

# Combined safe map (non-ASCII replacements — always safe)
_SAFE_MAP: dict[str, str] = {**_CHAR_MAP, **_DIGIT_MAP, **_PUNCT_MAP}

# Precompile the union of all garbled codepoints for detection
_GARBLED_CODEPOINTS = set(_SAFE_MAP.keys()) | set(_LIGATURES.keys())

# Ranges used for detection heuristic
_LATIN_EXT_RANGE = range(0x0100, 0x0250)
_GREEK_DIGIT_RANGE = range(0x03EC, 0x03F6)

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def is_garbled(text: str, threshold: float = 0.15) -> bool:
    """Return True if *text* likely comes from a garbled PDF font encoding.

    Heuristic: if more than *threshold* (default 15%) of the alphabetic
    characters fall in the Latin Extended or Greek digit ranges, the text
    is almost certainly garbled.
    """
    if not text or len(text) < 20:
        return False

    alpha_chars = 0
    garbled_chars = 0
    for ch in text:
        cp = ord(ch)
        if ch.isalpha() or cp in _LATIN_EXT_RANGE or cp in _GREEK_DIGIT_RANGE:
            alpha_chars += 1
            if cp in _LATIN_EXT_RANGE or cp in _GREEK_DIGIT_RANGE:
                garbled_chars += 1

    if alpha_chars == 0:
        return False
    return (garbled_chars / alpha_chars) > threshold

def garbled_ratio(text: str) -> float:
    """Return the fraction of alphabetic chars that are garbled codepoints."""
    if not text:
        return 0.0
    alpha = 0
    garbled = 0
    for ch in text:
        cp = ord(ch)
        if ch.isalpha() or cp in _LATIN_EXT_RANGE or cp in _GREEK_DIGIT_RANGE:
            alpha += 1
            if cp in _LATIN_EXT_RANGE or cp in _GREEK_DIGIT_RANGE:
                garbled += 1
    return garbled / max(alpha, 1)

# ---------------------------------------------------------------------------
# Degarbling
# ---------------------------------------------------------------------------

def degarble(text: str) -> str:
    """Apply substitution map to recover readable English from garbled PDF text.

    Strategy:
      1. Replace known ligatures (multi-char mappings) first.
      2. Replace all unambiguous Latin Extended / Greek codepoints.
      3. For ASCII symbols used as uppercase letters (&, /, ^ etc.),
         only replace them when they appear adjacent to (within 2 chars of)
         a known garbled codepoint — this avoids corrupting normal text
         regions (like correctly-rendered section headers).
    """
    if not text:
        return text

    # --- Step 1: ligatures ---
    for garbled, replacement in _LIGATURES.items():
        text = text.replace(garbled, replacement)

    # --- Step 2: safe single-char replacements (Latin Extended + Greek digits + punct) ---
    # Track which positions had garbled chars (so Step 3 can skip them)
    result = []
    was_garbled_pos: list[bool] = []
    for ch in text:
        mapped = _SAFE_MAP.get(ch)
        if mapped is not None:
            result.append(mapped)
            was_garbled_pos.append(True)
        else:
            result.append(ch)
            was_garbled_pos.append(False)
    text = "".join(result)

    # --- Step 3: contextual ASCII → uppercase replacements ---
    text = _contextual_upper_replace(text, was_garbled_pos)

    return text

def _contextual_upper_replace(text: str, was_garbled: list[bool] | None = None) -> str:
    """Replace ASCII symbols that serve as uppercase letters in garbled PDFs.

    Only replaces & / ^ > ; when they appear adjacent to lowercase letters
    (which would be the case in garbled body text but not in formulas/code).
    Also replaces d→T, E→N, etc. when surrounded by degarbled lowercase,
    but ONLY at positions that were NOT already degarbled from non-ASCII chars.
    """
    chars = list(text)
    n = len(chars)
    if was_garbled is None:
        was_garbled = [False] * n

    # Pass 1: unambiguous symbols (& / ^ > ;)
    for i, ch in enumerate(chars):
        if ch in _UPPER_MAP and not was_garbled[i]:
            # Check if surrounded by lowercase letters (garbled context)
            before = chars[i - 1] if i > 0 else " "
            after = chars[i + 1] if i < n - 1 else " "
            if before.islower() or after.islower():
                # Only replace if the next char is lowercase (start of garbled word)
                if after.islower():
                    chars[i] = _UPPER_MAP[ch]
                elif before.islower() and (i == n - 1 or not after.isalpha()):
                    chars[i] = _UPPER_MAP[ch]

    # Pass 2: ambiguous alpha mappings (d→T, E→N, K→O, W→P, Z→R, D→M)
    # Only apply to positions that were NOT degarbled (they were original ASCII
    # in the garbled font) and when flanked by lowercase context.
    for i, ch in enumerate(chars):
        if ch in _UPPER_ALPHA_MAP and not was_garbled[i]:
            before = chars[i - 1] if i > 0 else " "
            after = chars[i + 1] if i < n - 1 else " "
            before2 = chars[i - 2] if i > 1 else " "
            after2 = chars[i + 2] if i < n - 2 else " "
            # Require BOTH neighbors to be lowercase to confirm garbled context
            if before.islower() and after.islower():
                chars[i] = _UPPER_ALPHA_MAP[ch]
            # Word-initial: followed by lowercase, preceded by space/punct
            elif (not before.isalpha() and after.islower() and
                  i < n - 2 and after2.islower()):
                chars[i] = _UPPER_ALPHA_MAP[ch]

    return "".join(chars)

# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def detect_and_degarble(text: str) -> tuple[str, bool]:
    """Detect garbled text and degarble if needed.

    Returns (processed_text, was_garbled).
    """
    if is_garbled(text):
        return degarble(text), True
    return text, False
