"""Pure adapter checks; no OCR model or selected document is loaded."""

from __future__ import annotations

import base64
import builtins
import hashlib
import importlib.util
import json
import os
import py_compile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from product_eval import tatr_ocr_word_source_free as ocr_probe
from product_eval.tatr_cell_compat import prepare_word_tokens
from product_eval.tatr_ocr_word_source_free import (
    _installed_distributions,
    _verify_installed_record,
    _verify_site_packages_inventory,
    _verify_wheel_payload,
    guarded_rapidocr_class,
    rapidocr_words_to_tatr_tokens,
    run_synthetic,
)


@pytest.fixture
def site_packages(tmp_path: Path) -> Path:
    root = tmp_path / "site-packages"
    package = root / "demo"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    metadata = root / "demo_package-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: demo-package\nVersion: 1.0\n", encoding="utf-8",
    )
    (metadata / "RECORD").write_text(
        "demo/__init__.py,,\n"
        "demo_package-1.0.dist-info/METADATA,,\n"
        "demo_package-1.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    return root


def test_installed_distribution_rejects_duplicate_normalized_name(site_packages: Path) -> None:
    duplicate = site_packages / "shadow-1.0.dist-info"
    duplicate.mkdir()
    (duplicate / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: demo_package\nVersion: 1.0\n", encoding="utf-8",
    )
    (duplicate / "RECORD").write_text(
        "shadow-1.0.dist-info/METADATA,,\nshadow-1.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate installed distribution: demo-package"):
        _installed_distributions(site_packages)


@pytest.mark.parametrize("name", [
    "intruder.py", "sitecustomize.py", "usercustomize.py", "startup.pth",
    "demo/intruder.py", "demo/native.pyd", "demo/native.so", "demo/native.pyc",
    "demo/__pycache__/orphan.cpython-311.pyc",
])
def test_inventory_rejects_unrecorded_importable_or_executable_files(
    site_packages: Path, name: str,
) -> None:
    injected = site_packages / name
    injected.parent.mkdir(parents=True, exist_ok=True)
    injected.write_bytes(b"injected")
    with pytest.raises(ValueError, match="unrecorded site-packages file"):
        _verify_site_packages_inventory(site_packages, _installed_distributions(site_packages))


def test_inventory_allows_generated_bytecode_for_recorded_source(site_packages: Path) -> None:
    source = site_packages / "demo" / "__init__.py"
    cache = Path(importlib.util.cache_from_source(str(source)))
    py_compile.compile(str(source), cfile=str(cache), doraise=True)
    assert _verify_site_packages_inventory(site_packages, _installed_distributions(site_packages)) == 4


def test_inventory_allows_recorded_pth(site_packages: Path) -> None:
    (site_packages / "bootstrap.pth").write_text("import bootstrap\n", encoding="utf-8")
    record = site_packages / "demo_package-1.0.dist-info" / "RECORD"
    record.write_text(record.read_text(encoding="utf-8") + "bootstrap.pth,,\n", encoding="utf-8")
    assert _verify_site_packages_inventory(site_packages, _installed_distributions(site_packages)) == 4


def test_inventory_rejects_injection_before_vendor_imports(
    site_packages: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (site_packages / "sitecustomize.py").write_text("raise RuntimeError('loaded')\n", encoding="utf-8")

    def reject_inventory(*_args: object) -> dict:
        _verify_site_packages_inventory(site_packages, _installed_distributions(site_packages))
        return {}

    original_import = builtins.__import__

    def reject_vendor_import(name: str, *args: object, **kwargs: object) -> object:
        if name.split(".", 1)[0] in {"numpy", "onnxruntime", "PIL", "rapidocr"}:
            pytest.fail(f"vendor import before runtime inventory: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(ocr_probe, "verify_runtime", reject_inventory)
    monkeypatch.setattr(builtins, "__import__", reject_vendor_import)
    with pytest.raises(ValueError, match="unrecorded site-packages file"):
        ocr_probe.run_synthetic(runtime_root=site_packages.parent, wheelhouse=site_packages.parent,
                                notices_root=site_packages.parent, font_path=site_packages.parent,
                                output_dir=site_packages.parent / "unused")


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


def test_orientation_guard_runs_before_word_box_construction() -> None:
    class FakeRapidOCR:
        def __init__(self, labels: list[tuple[str, float]]) -> None:
            self.labels = labels
            self.text_cls = SimpleNamespace(cls_thresh=0.9)
            self.word_box_calls = 0

        def __call__(self) -> None:
            self.run_ocr_steps(None, {})
            self.calc_word_boxes()

        def run_ocr_steps(self, img, op_record):
            return (SimpleNamespace(boxes=[object() for _ in self.labels]),
                    SimpleNamespace(cls_res=self.labels), None, [])

        def calc_word_boxes(self) -> None:
            self.word_box_calls += 1

    guarded = guarded_rapidocr_class(FakeRapidOCR)
    upright = guarded([("0", 0.99)])
    upright()
    assert upright.word_box_calls == 1
    assert upright.word_box_build_count == 1
    assert upright.last_line_orientations == [("0", 0.99)]

    upside_down = guarded([("180", 1.0)])
    with pytest.raises(ValueError, match="confidently upright"):
        upside_down()
    assert upside_down.word_box_calls == 0
    assert not hasattr(upside_down, "word_box_build_count")
    assert upside_down.last_line_orientations == [("180", 1.0)]

    uncertain = guarded([("0", 0.8)])
    with pytest.raises(ValueError, match="confidently upright"):
        uncertain()
    assert uncertain.word_box_calls == 0
    assert not hasattr(uncertain, "word_box_build_count")


def test_frozen_zero_line_threshold_preserves_low_score_result() -> None:
    rapidocr = pytest.importorskip("rapidocr")
    np = pytest.importorskip("numpy")
    from rapidocr.utils.output import RapidOCROutput

    engine = rapidocr.RapidOCR(params={"Global.text_score": 0.0})
    assert engine.text_score == 0.0
    quad = [[0, 0], [10, 0], [10, 10], [0, 10]]
    result = RapidOCROutput(
        boxes=np.zeros((2, 4, 2)), txts=("LOW", "HIGH"), scores=(0.2, 0.9),
        word_results=((('LOW', 0.2, quad),), (('HIGH', 0.9, quad),)),
    )
    filtered = engine.filter_by_text_score(result)
    assert filtered.txts == ("LOW", "HIGH")
    assert filtered.scores == (0.2, 0.9)
    assert len(filtered.word_results) == 2


def test_pinned_source_free_orientation_probe(tmp_path: Path) -> None:
    names = ("TATR_OCR_RUNTIME_ROOT", "TATR_OCR_WHEELHOUSE",
             "TATR_OCR_NOTICES_ROOT", "TATR_OCR_FONT")
    if not all(os.environ.get(name) for name in names):
        pytest.skip("pinned source-free OCR runtime paths were not supplied")
    result = run_synthetic(
        runtime_root=Path(os.environ[names[0]]),
        wheelhouse=Path(os.environ[names[1]]),
        notices_root=Path(os.environ[names[2]]),
        font_path=Path(os.environ[names[3]]),
        output_dir=tmp_path / "probe",
    )
    receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
    assert [token["text"] for token in receipt["word_tokens"]] == [
        "NORTH", "SOUTH", "ALPHA", "BETA"
    ]
    assert receipt["line_score_threshold"] == 0.0
    assert receipt["low_score_filter_probe_scores"] == [0.2, 0.9]
    assert receipt["low_score_filter_probe_retained_lines"] == ["NORTH SOUTH", "ALPHA BETA"]
    assert all(label == "0" for label, _ in receipt["upright_line_orientations"])
    assert all(label == "180" for label, _ in receipt["rotated_line_orientations_rejected"])
    assert receipt["word_box_builder_calls_before_rotation"] == 1
    assert receipt["word_box_builder_calls_after_rotation"] == 1
