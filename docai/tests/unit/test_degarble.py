from __future__ import annotations

from docai_core.extraction.degarble import (
    degarble,
    detect_and_degarble,
    garbled_ratio,
    is_garbled,
)


def test_is_garbled_clean_ascii_returns_false() -> None:
    text = "Invoice number INV-00123 issued by Acme Corporation on 2024-01-15."
    assert is_garbled(text) is False


def test_is_garbled_high_latin_extended_returns_true() -> None:
    # Build a string where >15% of alpha chars are in U+0100–U+024F.
    # Mix ASCII letters with Latin Extended chars to ensure len > 20.
    latin_ext = "ĨĞŝŽũŬŵƉƌƐ"
    text = "ab" + latin_ext + "cdefghij"  # 2 + 10 + 10 = 22 chars, 10/22 alpha ≈ 45% garbled
    assert is_garbled(text) is True


def test_is_garbled_short_text_always_false() -> None:
    # Under 20 chars — must return False even if content looks garbled.
    short_garbled = "ĨĞŝŽũ"  # 5 Latin Extended chars
    assert len(short_garbled) < 20
    assert is_garbled(short_garbled) is False


def test_degarble_ligatures() -> None:
    # ĸ (U+0138) → "ffi"
    result_ffi = degarble("ĸ")
    assert "ffi" in result_ffi

    # Į (U+012E) → "fi"
    result_fi = degarble("Į")
    assert "fi" in result_fi


def test_degarble_greek_digits() -> None:
    assert degarble("Ϭ") == "0"   # Ϭ → 0
    assert degarble("ϭ") == "1"   # ϭ → 1
    assert degarble("ϵ") == "9"   # ϵ → 9


def test_degarble_single_char_latin_extended() -> None:
    assert degarble("Ğ") == "e"   # Ğ → e
    assert degarble("ŝ") == "i"   # ŝ → i
    assert degarble("Ž") == "o"   # Ž → o


def test_degarble_contextual_upper_replace_only_in_lowercase_context() -> None:
    # "&" adjacent to lowercase → replaced with "F"
    result_lower = degarble("&abc")
    assert "Fabc" in result_lower

    # "&" NOT adjacent to lowercase → left unchanged
    result_upper = degarble("& ABC")
    assert result_upper == "& ABC"


def test_detect_and_degarble_returns_tuple() -> None:
    # Clean input: second item must be False, text unchanged
    clean = "Invoice total is 1234.56 dollars for services rendered."
    text_out, was_garbled = detect_and_degarble(clean)
    assert was_garbled is False
    assert text_out == clean

    # Garbled input: second item must be True, text must differ
    # Must be >= 20 chars to pass is_garbled's length guard.
    garbled = "abĨĞŝŽũŬŵƉƌcdefghijk"
    text_out2, was_garbled2 = detect_and_degarble(garbled)
    assert was_garbled2 is True
    assert text_out2 != garbled
