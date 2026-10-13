"""Pure adapter checks; no OCR model or selected document is loaded."""

from __future__ import annotations

import base64
import hashlib
import zipfile
from types import SimpleNamespace

import pytest

from product_eval.tatr_cell_compat import prepare_word_tokens
from product_eval.tatr_ocr_word_source_free import (
    _verify_installed_record,
    _verify_wheel_payload,
    rapidocr_words_to_tatr_tokens,
)


def _result() -> SimpleNamespace:
    return SimpleNamespace(
        txts=("NORTH SOUTH",),
        boxes=([0, 0], [100, 0], [100, 20], [0, 20]),
        scores=(0.94,),
        word_results=((
            ("NORTH", 0.91, [[2, 2], [42, 2], [42, 17], [2, 17]]),
            ("SOUTH", 0.88, [[55, 2], [98, 2], [98, 17], [55, 17]]),
        ),),
    )


def test_separate_word_polygons_and_reported_scores_feed_tatr_contract() -> None:
    result = _result()
    result.boxes = (result.boxes,)
    tokens = rapidocr_words_to_tatr_tokens(result, (100, 20))

    assert [token["text"] for token in tokens] == ["NORTH", "SOUTH"]
    assert [token["bbox"] for token in tokens] == [[2, 2, 42, 17], [55, 2, 98, 17]]
    assert [token["ocr_confidence"] for token in tokens] == [0.91, 0.88]
    assert [token["reading_order"] for token in tokens] == [0, 1]
    assert [token["source_token_id"] for token in tokens] == ["rapidocr:l0:w0", "rapidocr:l0:w1"]
    assert tokens[0]["ocr_polygon"] == [[2, 2], [42, 2], [42, 17], [2, 17]]
    assert len(prepare_word_tokens(tokens, (100, 20))) == 2


@pytest.mark.parametrize("change, message", [
    ({"word_results": None}, "absent or misaligned"),
    ({"word_results": ((),)}, "no recognized words"),
    ({"word_results": ((("NORTH SOUTH", 0.9, [[0, 0], [100, 0], [100, 20], [0, 20]]),),)},
     "one nonempty word"),
    ({"word_results": ((("NORTH", float("nan"), [[2, 2], [42, 2], [42, 17], [2, 17]]),
                       ("SOUTH", 0.88, [[55, 2], [98, 2], [98, 17], [55, 17]])),)},
     "reported word score"),
    ({"word_results": ((("NORTH", 0.91, [[-1, 2], [42, 2], [42, 17], [-1, 17]]),
                       ("SOUTH", 0.88, [[55, 2], [98, 2], [98, 17], [55, 17]])),)},
     "exceeds the image"),
    ({"word_results": ((("NORTH", 0.91, [[2, 2], [42, 2], [42, 17], [2, 17]]),),)},
     "do not reconstruct"),
])
def test_missing_line_only_or_invalid_word_output_fails_closed(change: dict, message: str) -> None:
    result = _result()
    result.boxes = (result.boxes,)
    for key, value in change.items():
        setattr(result, key, value)
    with pytest.raises(ValueError, match=message):
        rapidocr_words_to_tatr_tokens(result, (100, 20))


def test_order_is_engine_order_not_inferred_from_coordinates() -> None:
    result = _result()
    result.boxes = (result.boxes,)
    result.txts = ("SOUTH NORTH",)
    result.word_results = ((
        ("SOUTH", 0.88, [[55, 2], [98, 2], [98, 17], [55, 17]]),
        ("NORTH", 0.91, [[2, 2], [42, 2], [42, 17], [2, 17]]),
    ),)
    assert [token["text"] for token in rapidocr_words_to_tatr_tokens(result, (100, 20))] == ["SOUTH", "NORTH"]


def test_installed_record_rejects_mutated_payload(tmp_path) -> None:
    payload = tmp_path / "package.py"
    payload.write_bytes(b"original")
    encoded = base64.urlsafe_b64encode(hashlib.sha256(b"original").digest()).rstrip(b"=").decode()
    record = f"package.py,sha256={encoded},8\npackage.dist-info/RECORD,,\n"
    record_path = tmp_path / "package.dist-info" / "RECORD"
    record_path.parent.mkdir()
    record_path.write_text(record, encoding="utf-8")
    dist = SimpleNamespace(
        metadata={"Name": "package"},
        read_text=lambda name: record if name == "RECORD" else None,
        locate_file=lambda name: tmp_path / name,
    )
    assert _verify_installed_record(dist, tmp_path) == 1
    payload.write_bytes(b"changed!")
    with pytest.raises(ValueError, match="file differs"):
        _verify_installed_record(dist, tmp_path)


def test_pinned_wheel_bytes_reject_changed_installed_file(tmp_path) -> None:
    wheel_path = tmp_path / "package.whl"
    package = tmp_path / "package"
    package.mkdir()
    module = package / "module.py"
    module.write_bytes(b"original")
    with zipfile.ZipFile(wheel_path, "w") as output:
        output.writestr("package/module.py", b"original")
    with zipfile.ZipFile(wheel_path) as wheel:
        assert _verify_wheel_payload(wheel, tmp_path) == 1
        module.write_bytes(b"changed!")
        with pytest.raises(ValueError, match="pinned wheel"):
            _verify_wheel_payload(wheel, tmp_path)
