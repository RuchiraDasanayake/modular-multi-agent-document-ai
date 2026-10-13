"""Pure, lossless planning of numbered source text within model input limits.

Offsets are Python character offsets into each original page, not UTF-8 bytes,
PDF geometry or offsets into another OCR version. No overlap, normalization,
inference, evidence remapping or extraction merging is performed here.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

MAX_SEGMENT_CHARS = 24_000
MAX_SEGMENTS = 4
_PARAGRAPH_END = re.compile(r"\r?\n[ \t]*\r?\n|\r[ \t]*\r")
_LINE_END = re.compile(r"\r\n|\n|\r")


@dataclass(frozen=True)
class SourcePage:
    page: int
    text_length: int
    source_text_sha256: str


@dataclass(frozen=True)
class TextSlice:
    page: int
    start: int
    end: int
    text: str
    source_text_sha256: str


@dataclass(frozen=True)
class TextSegment:
    index: int
    slices: tuple[TextSlice, ...]

    @property
    def char_count(self) -> int:
        return sum(part.end - part.start for part in self.slices)


@dataclass(frozen=True)
class SegmentPlan:
    source_pages: tuple[SourcePage, ...]
    segments: tuple[TextSegment, ...]
    reason: str | None = None
    boundary_policy: str | None = None
    overlap_chars: int = 0

    @property
    def supported(self) -> bool:
        return self.reason is None


def _boundary(text: str, start: int, limit: int, prefer_paragraph: bool) -> int | None:
    if prefer_paragraph:
        for pattern in (_PARAGRAPH_END, _LINE_END):
            matches = list(pattern.finditer(text, start, limit))
            # A regex search cut off after CR must not split its following LF.
            for match in reversed(matches):
                end = match.end()
                if not (text[end - 1] == "\r" and end < len(text) and text[end] == "\n"):
                    return end
    for end in range(limit, start, -1):
        if text[end - 1] == "\r" and end < len(text) and text[end] == "\n":
            continue
        if text[end - 1].isspace() or (end < len(text) and text[end].isspace()):
            return end
    return None


def _attempt(
    pages: tuple[tuple[SourcePage, str], ...], max_chars: int, max_segments: int, *, preserve_pages: bool,
) -> tuple[tuple[TextSegment, ...], str | None]:
    segments: list[TextSegment] = []
    current: list[TextSlice] = []
    used = 0

    def flush() -> None:
        nonlocal current, used
        if current:
            segments.append(TextSegment(len(segments), tuple(current)))
            current, used = [], 0

    for source, text in pages:
        if preserve_pages and used and len(text) <= max_chars and len(text) > max_chars - used:
            flush()
        if not text:
            current.append(TextSlice(source.page, 0, 0, "", source.source_text_sha256))
            continue
        start = 0
        while start < len(text):
            if used == max_chars:
                flush()
            if len(segments) >= max_segments:
                return (), "source_exceeds_segment_budget"
            available = max_chars - used
            end = len(text) if len(text) - start <= available else _boundary(text, start, start + available, preserve_pages)
            if end is None:
                if used:
                    flush()
                    continue
                return (), "unbreakable_span_exceeds_segment_chars"
            current.append(TextSlice(source.page, start, end, text[start:end], source.source_text_sha256))
            used += end - start
            start = end
            if start < len(text):
                flush()
    flush()
    if len(segments) > max_segments:
        return (), "source_exceeds_segment_budget"
    return tuple(segments), None


def plan_segments(
    pages: Sequence[Mapping[str, object]], *, max_chars: int = MAX_SEGMENT_CHARS, max_segments: int = MAX_SEGMENTS,
) -> SegmentPlan:
    """Keep whole pages/paragraphs where feasible, then compact at whitespace.

    A second packing pass avoids rejecting a source solely because whole-page
    preference wasted capacity. Long uninterrupted spans are never split to
    force admission. Unsupported plans expose no partially planned segments.
    Empty pages have explicit zero-length slices in supported plans. The caller
    owns page-count/byte admission limits and supplies its canonical page order.
    """
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_SEGMENT_CHARS:
        raise ValueError("max_chars must be an integer between 1 and 24000")
    if type(max_segments) is not int or not 1 <= max_segments <= MAX_SEGMENTS:
        raise ValueError("max_segments must be an integer between 1 and 4")
    source_rows, seen = [], set()
    for page in pages:
        if not isinstance(page, Mapping):
            raise TypeError("Each source page must be a mapping")
        number, text = page.get("page"), page.get("text")
        if type(number) is not int or number < 1 or number in seen or not isinstance(text, str):
            raise ValueError("Source pages need unique positive page IDs and exact string text")
        try:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except UnicodeEncodeError as exc:
            raise ValueError("Source page text must be valid Unicode") from exc
        source_rows.append((SourcePage(number, len(text), digest), text))
        seen.add(number)
    rows = tuple(source_rows)
    source_pages = tuple(source for source, _ in rows)
    characters = sum(source.text_length for source in source_pages)
    if not characters:
        return SegmentPlan(source_pages, (), "no_source_text")
    if characters > max_chars * max_segments:
        return SegmentPlan(source_pages, (), "source_exceeds_segment_budget")
    for preserve_pages in (True, False):
        segments, reason = _attempt(rows, max_chars, max_segments, preserve_pages=preserve_pages)
        if reason is None:
            return SegmentPlan(source_pages, segments, boundary_policy="page_paragraph" if preserve_pages else "packed_whitespace")
    return SegmentPlan(source_pages, (), reason)
