"""Pure adapter checks; no OCR model or selected document is loaded."""

from __future__ import annotations

import base64
import builtins
import hashlib
import importlib.util
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
    rapidocr_words_to_tatr_tokens,
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
