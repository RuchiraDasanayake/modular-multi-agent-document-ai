from __future__ import annotations

import hashlib
from collections import defaultdict

import pytest

from idpo.product_auto.segments import plan_segments


def assert_lossless(pages, plan, max_chars):
    assert plan.supported and plan.overlap_chars == 0
    recovered, offsets, order = defaultdict(str), defaultdict(int), []
    for index, segment in enumerate(plan.segments):
        assert segment.index == index and segment.char_count <= max_chars
        for part in segment.slices:
            original = next(page["text"] for page in pages if page["page"] == part.page)
            assert part.start == offsets[part.page]
            assert original[part.start:part.end] == part.text
            assert part.source_text_sha256 == hashlib.sha256(original.encode()).hexdigest()
            offsets[part.page] = part.end
            recovered[part.page] += part.text
            if not order or order[-1] != part.page:
                order.append(part.page)
    assert order == [page["page"] for page in pages]
    assert dict(recovered) == {page["page"]: page["text"] for page in pages}


def test_preserves_whole_pages_exact_whitespace_and_nonconsecutive_ids():
    pages = [{"page": 4, "text": "alpha  "}, {"page": 9, "text": "beta\n"}]
    plan = plan_segments(pages, max_chars=8)
    assert len(plan.segments) == 2 and plan.boundary_policy == "page_paragraph"
    assert_lossless(pages, plan, 8)


def test_long_page_prefers_paragraph_boundaries():
    pages = [{"page": 1, "text": "alpha\n\nbeta\n\ngamma"}]
    plan = plan_segments(pages, max_chars=13)
    assert plan.segments[0].slices[0].text == "alpha\n\nbeta\n\n"
    assert_lossless(pages, plan, 13)


def test_compact_fallback_avoids_false_rejection_from_whole_page_preference():
    pages = [{"page": n, "text": "a a a "} for n in range(1, 6)]
    plan = plan_segments(pages, max_chars=10)
    assert plan.boundary_policy == "packed_whitespace"
    assert len(plan.segments) == 3
    assert_lossless(pages, plan, 10)


def test_exact_character_boundary_and_empty_pages_have_explicit_coverage():
    pages = [{"page": 1, "text": ""}, {"page": 2, "text": "abcd"}, {"page": 3, "text": ""}]
    plan = plan_segments(pages, max_chars=4)
    assert len(plan.segments) == 1
    assert_lossless(pages, plan, 4)


def test_unicode_and_crlf_offsets_are_characters_and_never_split_crlf():
    pages = [{"page": 1, "text": "café\r\n\r\n東京 Ωmega\r\nfin"}]
    plan = plan_segments(pages, max_chars=9)
    assert_lossless(pages, plan, 9)
    for segment in plan.segments:
        for part in segment.slices:
            text = pages[0]["text"]
            assert not (part.end < len(text) and text[part.end - 1:part.end + 1] == "\r\n")


def test_token_larger_than_segment_returns_unsupported_without_partial_output():
    plan = plan_segments([{"page": 1, "text": "prefix " + "x" * 11}], max_chars=10)
    assert not plan.supported and not plan.segments
    assert plan.reason == "unbreakable_span_exceeds_segment_chars"
    assert plan.source_pages[0].text_length == 18


def test_four_segment_limit_rejects_whole_source_not_a_prefix():
    pages = [{"page": 1, "text": "x " * 21}]
    plan = plan_segments(pages, max_chars=10)
    assert not plan.supported and plan.reason == "source_exceeds_segment_budget"
    assert not plan.segments and plan.source_pages[0].text_length == 42


def test_default_envelope_admits_exactly_four_full_size_pages():
    pages = [{"page": n, "text": "word " * 4800} for n in range(1, 5)]
    plan = plan_segments(pages)
    assert len(plan.segments) == 4
    assert_lossless(pages, plan, 24000)


def test_unbreakable_page_tokens_can_exceed_count_despite_fitting_character_sum():
    pages = [{"page": n, "text": "abcdefgh"} for n in range(1, 6)]
    plan = plan_segments(pages, max_chars=10)
    assert not plan.supported and not plan.segments
    assert plan.reason == "source_exceeds_segment_budget"


@pytest.mark.parametrize("pages", [[], [{"page": 1, "text": ""}]])
def test_no_text_is_explicitly_unsupported(pages):
    plan = plan_segments(pages)
    assert not plan.supported and plan.reason == "no_source_text"
    assert len(plan.source_pages) == len(pages)


@pytest.mark.parametrize("pages", [
    [{"page": True, "text": "a"}], [{"page": 0, "text": "a"}],
    [{"page": 1, "text": None}], [{"page": 1, "text": "a"}, {"page": 1, "text": "b"}],
    [{"page": 1, "text": "\ud800"}], ["invalid"],
])
def test_invalid_source_contract_is_rejected(pages):
    with pytest.raises((ValueError, TypeError)):
        plan_segments(pages)


@pytest.mark.parametrize("kwargs", [{"max_chars": 0}, {"max_chars": 24001}, {"max_chars": True}, {"max_segments": 5}, {"max_segments": 0}])
def test_limits_cannot_silently_exceed_model_or_call_envelope(kwargs):
    with pytest.raises(ValueError):
        plan_segments([{"page": 1, "text": "a"}], **kwargs)
