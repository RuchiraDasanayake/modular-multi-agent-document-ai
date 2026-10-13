import json
from types import SimpleNamespace

import pytest

from product_eval import cord_model_ocr_replay as replay


@pytest.fixture
def cache(tmp_path, monkeypatch):
    sources, rows = [], []
    for index in range(60):
        image = tmp_path / f"image-{index}.png"
        image.write_bytes(f"source{index}".encode())
        source = {"doc_id": str(index), "source_path": str(image), "source_sha256": replay.sha(image)}
        sources.append(source)
        rows.append({**source, "rapidocr": {"failure": None, "lines_in_bounds": True, "text": "Total 42",
                     "lines": [{"text": "Total 42", "start": 0, "end": 8}]}})
    path = tmp_path / "raw.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    monkeypatch.setattr(replay, "RAW_SHA256", replay.sha(path))
    monkeypatch.setattr(replay, "SOURCE_HASHES", {source["source_sha256"] for source in sources[:2]})
    return path, sources[:2]


def test_cache_checks_originals_and_offsets_before_replaying(cache):
    path, sources = cache
    assert replay.selected_pages(path, sources) == {"0": "Total 42", "1": "Total 42"}
    from pathlib import Path

    Path(sources[0]["source_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="source bytes changed"):
        replay.selected_pages(path, sources)


def test_cache_tamper_and_source_substitution_rejected(cache):
    path, sources = cache
    with pytest.raises(ValueError, match="two fixed"):
        replay.selected_pages(path, sources[:1])
    path.write_text(path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cache changed"):
        replay.selected_pages(path, sources)


def test_two_call_ceiling_does_not_touch_provider(tmp_path):
    def forbidden(**kwargs):
        raise AssertionError("An extra call would spend credits")

    chat = replay.ReplayChat(SimpleNamespace(complete_json=forbidden), tmp_path, "secret")
    chat.calls = 2
    result = chat.complete_json(system="system", prompt="prompt")
    assert result.sdk_attempts == 0
    assert result.error == "local_call_budget"
