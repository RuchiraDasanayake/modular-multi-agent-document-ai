from __future__ import annotations

from docai_core.extraction import (
    build_extraction_input,
    build_extraction_prompt,
    build_single_field_prompt,
)
from docai_core.extraction.prompt_builder import SYSTEM_PROMPT


def test_build_extraction_prompt_fields_with_descriptions() -> None:
    result = build_extraction_prompt(
        ["invoice_number", "total"],
        {"invoice_number": "The invoice ID", "total": "Total amount due"},
        "Invoice #INV-001 Total: 100.00",
    )
    assert '"invoice_number": The invoice ID' in result
    assert '"total": Total amount due' in result
    assert "INV-001" in result


def test_build_extraction_prompt_fields_without_descriptions() -> None:
    result = build_extraction_prompt(
        ["invoice_number", "total"],
        {},
        "some text",
    )
    assert '"invoice_number" [omit if not present]' in result
    assert '"total" [omit if not present]' in result


def test_build_extraction_prompt_no_fields_uses_generic_block() -> None:
    result = build_extraction_prompt([], {}, "some text")
    assert "Extract any relevant key-value fields" in result


def test_build_extraction_prompt_seven_rules_present() -> None:
    result = build_extraction_prompt(["field"], {}, "text")
    for i in range(1, 8):
        assert f"{i}." in result


def test_build_extraction_prompt_no_think_true_prepends_token() -> None:
    result = build_extraction_prompt(["field"], {}, "text", no_think=True)
    assert result.startswith("/no_think\n")


def test_build_extraction_prompt_no_think_false_no_prefix() -> None:
    result = build_extraction_prompt(["field"], {}, "text", no_think=False)
    assert not result.startswith("/no_think")


def test_build_single_field_prompt_contains_key_and_description() -> None:
    result = build_single_field_prompt("vendor_name", "Name of the vendor", "ACME Corp")
    assert '"vendor_name"' in result
    assert "Name of the vendor" in result
    assert "ACME Corp" in result


def test_build_single_field_prompt_no_think_prepends_token() -> None:
    result = build_single_field_prompt("total", "Total amount", "text", no_think=True)
    assert result.startswith("/no_think\n")


def test_build_extraction_input_short_text_returns_verbatim() -> None:
    text = "Invoice number: INV-001\nTotal: 100.00"
    result = build_extraction_input(text, ["invoice_number"], {}, max_chars=500)
    assert result == text


def test_build_extraction_input_long_text_truncates() -> None:
    # Build a text longer than max_chars with a clear paragraph break past the 70% mark.
    para1 = "A " * 400  # 800 chars
    para2 = "B " * 400  # 800 chars
    text = para1.rstrip() + "\n\n" + para2.rstrip()
    result = build_extraction_input(
        text, [], {}, max_chars=900, prefer_targeted=False
    )
    assert len(result) <= 900
    # Should cut at the paragraph break.
    assert result == para1.rstrip()


def test_build_extraction_input_targeted_selects_relevant_lines() -> None:
    lines = [
        "Line about weather today",
        "Invoice number: INV-001",
        "Some unrelated content here",
        "Total amount: 500.00",
        "More unrelated filler text",
    ]
    long_text = ("\n".join(lines) + "\n") * 200  # make it long enough to need truncation
    result = build_extraction_input(
        long_text,
        ["invoice_number", "total_amount"],
        {"invoice_number": "invoice ID", "total_amount": "total due"},
        max_chars=500,
        prefer_targeted=True,
        window_lines=0,
    )
    # Targeted context should include lines with "invoice" and "total" terms.
    assert "INV-001" in result or "Invoice" in result
    assert "500.00" in result or "Total" in result


def test_system_prompt_is_exported() -> None:
    assert isinstance(SYSTEM_PROMPT, str)
    assert "JSON" in SYSTEM_PROMPT
    assert len(SYSTEM_PROMPT) > 10


def test_public_exports_available() -> None:
    assert callable(build_extraction_prompt)
    assert callable(build_single_field_prompt)
    assert callable(build_extraction_input)
    # Smoke round-trip
    prompt = build_extraction_prompt(["total"], {"total": "Total due"}, "Total: 100")
    assert "total" in prompt
    assert "100" in prompt
