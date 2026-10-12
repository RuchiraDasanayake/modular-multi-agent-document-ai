"""Manifest and sampling tests; these never invoke a document parser."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from product_eval.real_native_parser_diagnostic import sample_indices, verify_corpus


def _frozen_dummy_corpus(directory: Path) -> Path:
    sources = []
    for extension in ("docx", "xlsx", "pptx", "html", "eml"):
        for index in range(2):
            name = f"source_{extension}_{index}.{extension}"
            content = f"original-{extension}-{index}".encode()
            (directory / name).write_bytes(content)
            item = {"id": f"{extension}_{index}", "format": extension, "filename": name,
                    "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            if extension == "eml":
                raw = b"From archive\n" + content
                raw_name = f"source_{extension}_{index}.mbox-source"
                (directory / raw_name).write_bytes(raw)
                item.update({"raw_filename": raw_name, "raw_bytes": len(raw),
                             "raw_sha256": hashlib.sha256(raw).hexdigest()})
            sources.append(item)
    manifest_path = directory.parent / "manifest.json"
    manifest_path.write_text(json.dumps({"manifest_version": 1, "source_file_count": 10,
                                         "sources": sources}), encoding="utf-8")
    return manifest_path


def test_verify_corpus_requires_exact_hashes_and_eml_derivation(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = _frozen_dummy_corpus(corpus)
    verified, digest = verify_corpus(corpus, manifest)
    assert len(verified["sources"]) == 10
    assert len(digest) == 64

    (corpus / "source_eml_0.eml").write_bytes(b"modified")
    with pytest.raises(ValueError, match="source_hash_mismatch:eml_0"):
        verify_corpus(corpus, manifest)


def test_verify_corpus_rejects_extra_file_and_unsafe_manifest_name(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = _frozen_dummy_corpus(corpus)
    (corpus / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected_corpus_file"):
        verify_corpus(corpus, manifest)
    (corpus / "extra.txt").unlink()

    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["sources"][0]["filename"] = "../outside.docx"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="unsafe_source_name"):
        verify_corpus(corpus, manifest)


@pytest.mark.parametrize(("count", "maximum", "expected"), [
    (0, 16, []), (3, 16, [0, 1, 2]), (17, 16, [*range(15), 16]),
    (100, 3, [0, 49, 99]), (100, 1, [0]),
])
def test_sample_indices_are_deterministic_and_spread(
    count: int, maximum: int, expected: list[int],
) -> None:
    assert sample_indices(count, maximum) == expected
