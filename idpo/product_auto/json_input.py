"""Bounded product-only JSON text pages and canonical logical-source receipts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from idpo.core.types import Document, Page

MAX_JSON_INPUT_BYTES = 20 * 1024 * 1024
MAX_LOGICAL_DOCUMENTS = 5000
MAX_JSON_PAGES = 50
MAX_SAFE_PAGE_ID = 2**53 - 1


class JsonInputLimitError(ValueError):
    """A complete container cannot fit the product's declared bounds."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class JsonInputPreflight:
    logical_count: int
    source_sha256: str | None
    reason: str | None = None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON source property")
        result[key] = value
    return result


def _finite_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("Nonfinite JSON source number")
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("Nonstandard JSON source constant")


def _read_entries(path: Path) -> tuple[list[dict], list[tuple[str, int, str]], str]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_JSON_INPUT_BYTES + 1)
    if len(raw) > MAX_JSON_INPUT_BYTES:
        raise JsonInputLimitError("file_too_large")
    payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                         parse_float=_finite_float, parse_constant=_reject_constant)
    entries = payload if isinstance(payload, list) else [payload]
    if not entries:
        raise ValueError("JSON source has no documents")
    if len(entries) > MAX_LOGICAL_DOCUMENTS:
        raise JsonInputLimitError("json_document_limit_exceeded")
    sources: list[tuple[str, int, str]] = []
    # Validate the complete container before constructing any Document or Page.
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("doc_id"), str) or not entry["doc_id"].strip():
            raise ValueError("JSON source needs a document ID")
        if "source" in entry and not isinstance(entry["source"], str):
            raise ValueError("JSON source kind must be text")
        pages = entry.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("JSON source needs text pages")
        if len(pages) > MAX_JSON_PAGES:
            raise JsonInputLimitError("too_many_pages")
        seen: set[int] = set()
        for index, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                raise TypeError("Invalid JSON source page")
            number = page.get("number", index)
            if type(number) is not int or not 1 <= number <= MAX_SAFE_PAGE_ID or number in seen:
                raise ValueError("JSON pages need unique positive safe integer IDs")
            seen.add(number)
            if not isinstance(page.get("text", ""), str) or (
                page.get("raw_text") is not None and not isinstance(page["raw_text"], str)
            ):
                raise ValueError("JSON page text must be a string")
        # Ignored image paths and metadata remain part of the original entry's
        # receipt. They never become executable source paths or Page metadata.
        encoded = json.dumps(entry, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        sources.append((hashlib.sha256(encoded).hexdigest(), len(encoded), "canonical_json_entry"))
    return entries, sources, hashlib.sha256(raw).hexdigest()


def preflight_json_input(path: Path) -> JsonInputPreflight:
    """Retain only a count/hash or one explicit original failure unit."""
    try:
        entries, _, source_hash = _read_entries(path)
    except JsonInputLimitError as exc:
        return JsonInputPreflight(1, None, exc.reason)
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError):
        return JsonInputPreflight(1, None, "parse_failed")
    return JsonInputPreflight(len(entries), source_hash)


def load_product_json(
    path: Path, *, expected_source_sha256: str, document_limit: int | None = None,
) -> tuple[list[Document], list[tuple[str, int, str]]]:
    """Build text-only documents after complete validation and source checking."""
    if document_limit is not None and (type(document_limit) is not int or
                                       not 1 <= document_limit <= MAX_LOGICAL_DOCUMENTS):
        raise ValueError("Invalid JSON preview document limit")
    entries, sources, source_hash = _read_entries(path)
    if source_hash != expected_source_sha256:
        raise ValueError("JSON source changed after admission")
    selected = entries if document_limit is None else entries[:document_limit]
    documents = [
        Document(
            doc_id=entry["doc_id"], source=entry.get("source", "synthetic"), path=str(path),
            pages=[Page(number=page.get("number", index), text=page.get("text", ""),
                        raw_text=page.get("raw_text"), image_path=None, metadata={})
                   for index, page in enumerate(entry["pages"], start=1)],
            metadata={},
        )
        for entry in selected
    ]
    return documents, sources[:len(documents)]
