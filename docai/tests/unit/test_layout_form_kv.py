"""Unit tests for layout-aware form KV extraction."""

from __future__ import annotations

import pytest

from docai_core.extraction.layout_form_kv import extract_layout_aware_kv


class TestLayoutFormKV:
    """Test layout-aware KV extraction for scanned forms."""

    def test_same_line_kv_colon(self) -> None:
        """Same-line key:value still extracts."""
        text = "Name: John Smith\n"
        candidate = extract_layout_aware_kv(text, "name", ["name"])
        assert candidate is not None
        assert candidate.value == "John Smith"
        assert "same_line" in candidate.source

    def test_same_line_kv_equals(self) -> None:
        """Same-line key=value extracts."""
        text = "Date = 2024-01-15\n"
        candidate = extract_layout_aware_kv(text, "date", ["date"])
        assert candidate is not None
        assert candidate.value == "2024-01-15"

    def test_next_line_answer(self) -> None:
        """Label followed by answer on next line extracts."""
        text = (
            "Recipient\n"
            "ABC Corporation\n"
        )
        candidate = extract_layout_aware_kv(text, "recipient", ["recipient", "to"])
        assert candidate is not None
        assert candidate.value == "ABC Corporation"
        assert "next_line" in candidate.source

    def test_next_line_answer_with_multiple_lines(self) -> None:
        """Next-line extraction works in multi-line document."""
        text = (
            "Invoice Number\n"
            "INV-2024-001\n"
            "\n"
            "Date\n"
            "2024-01-15\n"
            "\n"
            "Recipient\n"
            "John Smith\n"
        )
        # Should find recipient
        candidate = extract_layout_aware_kv(text, "recipient", ["recipient", "to"])
        assert candidate is not None
        assert candidate.value == "John Smith"

    def test_right_aligned_answer(self) -> None:
        """Label with answer to the right (2+ spaces) extracts."""
        text = "Date       2024-01-15\n"
        candidate = extract_layout_aware_kv(text, "date", ["date"])
        assert candidate is not None
        assert candidate.value == "2024-01-15"

    def test_alias_matching(self) -> None:
        """Field aliases are tried."""
        text = "To: John Smith\n"
        candidate = extract_layout_aware_kv(text, "recipient", ["recipient", "to"])
        assert candidate is not None
        assert candidate.value == "John Smith"

    def test_case_insensitive_matching(self) -> None:
        """Label matching is case-insensitive."""
        text = "NAME: John Smith\n"
        candidate = extract_layout_aware_kv(text, "name", ["name"])
        assert candidate is not None
        assert candidate.value == "John Smith"

    def test_label_alone_not_value(self) -> None:
        """Label text alone does not become value."""
        text = "Name:\n"
        candidate = extract_layout_aware_kv(text, "name", ["name"])
        assert candidate is None

    def test_returns_none_for_unknown_field(self) -> None:
        """Unknown field returns None."""
        text = "Name: John Smith\nDate: 2024-01-01\n"
        candidate = extract_layout_aware_kv(text, "unknown", ["unknown"])
        assert candidate is None

    def test_no_hallucination_empty_text(self) -> None:
        """Empty text returns None, not hallucinated value."""
        candidate = extract_layout_aware_kv("", "name", ["name"])
        assert candidate is None

    def test_no_hallucination_no_aliases(self) -> None:
        """No aliases returns None."""
        text = "Name: John Smith\n"
        candidate = extract_layout_aware_kv(text, "name", [])
        assert candidate is None

    def test_ignores_noise_values(self) -> None:
        """Noise values like 'yes', 'no' are not returned."""
        text = "Active: yes\n"
        candidate = extract_layout_aware_kv(text, "active", ["active"])
        # "yes" is noise
        assert candidate is None

    def test_value_length_limit(self) -> None:
        """Very long values are rejected."""
        long_value = "x" * 300
        text = f"Name: {long_value}\n"
        candidate = extract_layout_aware_kv(text, "name", ["name"])
        assert candidate is None

    def test_next_line_rejects_other_label(self) -> None:
        """Next line that looks like a label is not treated as value."""
        text = (
            "Name\n"
            "Date: 2024-01-01\n"
        )
        candidate = extract_layout_aware_kv(text, "name", ["name"])
        # "Date: ..." looks like a label, should not be used as value
        assert candidate is None

    def test_real_world_form_multi_field(self) -> None:
        """Real-world form with mixed label/value patterns."""
        text = (
            "Invoice Number: INV-2024-001\n"
            "Date\n"
            "2024-01-15\n"
            "Recipient       ABC Corp\n"
            "Sender: Jane Doe\n"
        )

        # Should find invoice number (same-line)
        inv = extract_layout_aware_kv(text, "invoice", ["invoice number"])
        assert inv is not None
        assert inv.value == "INV-2024-001"

        # Should find date (next-line)
        date = extract_layout_aware_kv(text, "date", ["date"])
        assert date is not None
        assert date.value == "2024-01-15"

        # Should find recipient (right-aligned)
        recp = extract_layout_aware_kv(text, "recipient", ["recipient"])
        assert recp is not None
        assert recp.value == "ABC Corp"

        # Should find sender (same-line)
        sender = extract_layout_aware_kv(text, "sender", ["sender"])
        assert sender is not None
        assert sender.value == "Jane Doe"

    def test_confidence_scores(self) -> None:
        """Layout-aware extraction assigns appropriate confidence scores."""
        text = "Name: John Smith\nDate\n2024-01-15\n"

        # Same-line should have higher confidence than next-line
        same_line = extract_layout_aware_kv(text, "name", ["name"])
        next_line = extract_layout_aware_kv(text, "date", ["date"])

        assert same_line is not None
        assert next_line is not None
        assert same_line.confidence > next_line.confidence

    def test_evidence_text_present(self) -> None:
        """Evidence text is populated for audit trail."""
        text = "Name: John Smith\n"
        candidate = extract_layout_aware_kv(text, "name", ["name"])
        assert candidate is not None
        assert candidate.evidence_text
        assert "John Smith" in candidate.evidence_text
