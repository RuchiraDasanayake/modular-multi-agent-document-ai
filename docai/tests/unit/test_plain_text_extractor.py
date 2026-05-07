"""Unit tests for PlainTextExtractor."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest

from docai_core.contracts.domain import Document, DocumentProfile
from docai_core.text_acquisition.plain_text_extractor import PlainTextExtractor


def _doc(file_path: str, doc_id: str = "doc-1") -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename="test.txt",
        file_path=file_path,
        status="processing",
        uploaded_at=datetime(2026, 3, 15),
        profile=DocumentProfile(document_id=doc_id),
    )


def _write_txt(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".txt")
    os.write(fd, content.encode("utf-8"))
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_extracts_text_file_to_ocr_output() -> None:
    path = _write_txt("Invoice Number: INV-001\nTotal Amount: $100.00\n")
    try:
        result = PlainTextExtractor().extract(_doc(path))
        assert "INV-001" in result.text
        assert "$100.00" in result.text
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert "INV-001" in result.pages[0].text
        assert result.confidence == 1.0
    finally:
        os.unlink(path)


def test_missing_file_raises_file_not_found_error() -> None:
    with pytest.raises(FileNotFoundError):
        PlainTextExtractor().extract(_doc("/nonexistent/path/missing.txt"))


def test_empty_text_file_returns_confidence_zero() -> None:
    path = _write_txt("")
    try:
        result = PlainTextExtractor().extract(_doc(path))
        assert result.text == ""
        assert result.confidence == 0.0
    finally:
        os.unlink(path)


def test_document_id_and_engine_id_are_correct() -> None:
    path = _write_txt("some content")
    try:
        result = PlainTextExtractor().extract(_doc(path, doc_id="doc-abc"))
        assert result.document_id == "doc-abc"
        assert result.engine_id == "plain_text_extractor"
    finally:
        os.unlink(path)


def test_directory_path_raises_value_error() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        doc = _doc(tmpdir)
        with pytest.raises(ValueError):
            PlainTextExtractor().extract(doc)
