"""Audit the isolated RapidTable table runtime and run one source-free table smoke.

The supplied OCR tuple exercises RapidTable's HTML/cell matching without an OCR
package or OCR model. This module opens no selected PDF or gold annotation.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import math
import platform
import re
import sys
import sysconfig
import zipfile
from pathlib import Path
from typing import Any, Iterable

from product_eval.rapidtable_adbuy12_preflight import (
    MODEL_SHA256,
    make_synthetic_table,
    sha256_file,
    validate_ocr_tuple,
    validate_result,
    write_receipt_exclusive,
)
from product_eval.rapidtable_runtime_provenance import audit_wheel

LOCK_SHA256 = "c817cd6e6043e4dad24ca05889362d57d7e7f7f952cf339bd7899706011dff24"
FLATBUFFERS_LICENSE_SHA256 = (
    "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
)
FORBIDDEN_PACKAGES = {"rapidocr", "opencv-python-headless"}
VENDOR_IMPORT_ROOTS = (
    "PIL",
    "_yaml",
    "certifi",
    "charset_normalizer",
    "colorama",
    "colorlog",
    "cv2",
    "flatbuffers",
    "google",
    "google.protobuf",
    "idna",
    "numpy",
    "omegaconf",
    "onnxruntime",
    "packaging",
    "rapid_table",
    "requests",
    "tqdm",
    "urllib3",
    "yaml",
)
VENDOR_TOP_LEVEL = {name.split(".", 1)[0] for name in VENDOR_IMPORT_ROOTS}


def _package_key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _canonical_text_sha256(path: Path) -> str:
    """Pin Git text regardless of Windows checkout line-ending conversion."""
    content = path.read_bytes()
    if b"\r" in content.replace(b"\r\n", b""):
        raise ValueError("lock has unsupported line endings")
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def _installed_distributions(
    distributions: Iterable[importlib.metadata.Distribution],
    expected: dict[str, str],
) -> dict[str, importlib.metadata.Distribution]:
    by_name: dict[str, importlib.metadata.Distribution] = {}
    for distribution in distributions:
        name = _package_key(distribution.metadata["Name"])
        if name in by_name:
            raise ValueError(f"duplicate installed distribution metadata name: {name}")
        by_name[name] = distribution
    if {name: dist.version for name, dist in by_name.items()} != expected:
        raise ValueError("installed distributions differ from table-only lock")
    return by_name


def _site_packages_inventory(
    site_packages: Path, distributions: Iterable[importlib.metadata.Distribution]
) -> set[Path]:
    """Reject files that can be imported but are absent from installed RECORDs."""
    if not site_packages.is_dir():
        raise ValueError("runtime site-packages directory is missing")
    recorded: set[Path] = set()
    for distribution in distributions:
        if distribution.files is None:
            raise ValueError("installed distribution lacks RECORD file list")
        for member in distribution.files:
            path = Path(distribution.locate_file(member)).resolve()
            if path.is_relative_to(site_packages):
                recorded.add(path)
    actual: set[Path] = set()
    for path in site_packages.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"site-packages contains a symlink: {path}")
        if path.is_file():
            if path.suffix.lower() in {".pth", ".egg-link"}:
                raise ValueError(f"site-packages contains an import-path extension: {path}")
            actual.add(path.resolve())
    if actual != recorded:
        raise ValueError(
            f"site-packages differs from installed RECORD inventory: "
            f"{len(actual - recorded)} unrecorded, {len(recorded - actual)} missing"
        )
    recorded_dirs = {
        parent
        for file in recorded
        for parent in file.parents
        if parent != site_packages and parent.is_relative_to(site_packages)
    }
    actual_dirs = {path.resolve() for path in site_packages.rglob("*") if path.is_dir()}
    # RapidTable creates this empty model-cache directory when its own module loads.
    allowed_empty = site_packages / "rapid_table" / "models"
    if actual_dirs - recorded_dirs - {allowed_empty} or recorded_dirs - actual_dirs:
        raise ValueError("site-packages has unrecorded or missing directories")
    return recorded


def _verify_import_roots(site_packages: Path, recorded: set[Path]) -> None:
    for name in VENDOR_IMPORT_ROOTS:
        spec = importlib.util.find_spec(name)
        if spec is None:
            raise ValueError(f"vendor import root is missing: {name}")
        if spec.origin not in (None, "namespace"):
            if Path(spec.origin).resolve() not in recorded:
                raise ValueError(f"vendor import resolves to unsealed file: {name}")
        locations = spec.submodule_search_locations or ()
        if any(not Path(path).resolve().is_relative_to(site_packages) for path in locations):
            raise ValueError(f"vendor import searches outside runtime: {name}")


def _verify_loaded_vendor_modules(site_packages: Path, recorded: set[Path]) -> int:
    checked = 0
    for name, module in tuple(sys.modules.items()):
        if name.split(".", 1)[0] not in VENDOR_TOP_LEVEL or module is None:
            continue
        source = getattr(module, "__file__", None)
        if source is not None:
            if Path(source).resolve() not in recorded:
                raise ValueError(f"loaded vendor module came from unsealed file: {name}")
            checked += 1
        locations = getattr(module, "__path__", ())
        if any(not Path(path).resolve().is_relative_to(site_packages) for path in locations):
            raise ValueError(f"loaded vendor module searches outside runtime: {name}")
    return checked


def _supplied_ocr_tuple(
    drawn_ocr_tuple: tuple[Any, tuple[str, ...], tuple[float, ...]]
) -> tuple[Any, tuple[str, ...], tuple[float, ...]]:
    """Make supplied words differ from those painted in the raster."""
    return (
        drawn_ocr_tuple[0],
        tuple(f"SUPPLIED_{index}_{text}" for index, text in enumerate(drawn_ocr_tuple[1])),
        drawn_ocr_tuple[2],
    )


def _require_installed_record_hash(row: dict[str, Any], result: dict[str, Any]) -> None:
    if result["installed_record_sha256"] != row["installed_record_sha256"]:
        raise ValueError(f"installed RECORD differs from lock: {row['package']}")


def audit_table_runtime(
    lock_file: Path,
    wheel_dir: Path,
    model: Path,
    flatbuffers_license: Path,
) -> dict[str, Any]:
    if platform.system() != "Windows" or sys.version_info[:2] != (3, 11):
        raise ValueError("table runtime requires Windows CPython 3.11")
    if _canonical_text_sha256(lock_file) != LOCK_SHA256:
        raise ValueError("table-only wheel lock changed")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    wheels = lock.get("wheels")
    if lock.get("schema_version") != 1 or not isinstance(wheels, list) or len(wheels) != 18:
        raise ValueError("table-only wheel lock is incomplete")

    expected = {_package_key(row["package"]): row["version"] for row in wheels}
    if len(expected) != len(wheels) or FORBIDDEN_PACKAGES & expected.keys():
        raise ValueError("table-only lock has duplicate or forbidden packages")
    distributions = list(importlib.metadata.distributions())
    installed = _installed_distributions(distributions, expected)
    if importlib.util.find_spec("rapidocr") is not None:
        raise ValueError("RapidOCR is importable in the table-only runtime")

    packages: list[dict[str, Any]] = []
    owners: dict[str, set[str]] = {}
    notice_count = 0
    for row in wheels:
        filename = row["filename"]
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("unsafe wheel filename")
        wheel = wheel_dir / filename
        if wheel.stat().st_size != row["size_bytes"] or sha256_file(wheel) != row["sha256"]:
            raise ValueError(f"wheel differs from lock: {filename}")
        with zipfile.ZipFile(wheel) as archive:
            for notice in row["notices"]:
                data = archive.read(notice["path"])
                if hashlib.sha256(data).hexdigest() != notice["sha256"] or (
                    "size_bytes" in notice and len(data) != notice["size_bytes"]
                ):
                    raise ValueError(f"notice differs from lock: {filename}: {notice['path']}")
                notice_count += 1
            notice_candidates = {
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and Path(name).name.lower().startswith(("license", "licence", "notice", "copying"))
            }
            if notice_candidates - {notice["path"] for notice in row["notices"]}:
                raise ValueError(f"wheel has unpinned notice files: {filename}")
        distribution = installed[_package_key(row["package"])]
        result, owned_paths = audit_wheel(wheel, distribution)
        _require_installed_record_hash(row, result)
        if result["mismatches"] or result["hashed_extra_installed_record_mismatches"]:
            raise ValueError(f"installed wheel bytes or RECORD differ: {filename}")
        if result["unhashed_extra_installed_record_files"]:
            raise ValueError(f"installed RECORD has unhashed extra entries: {filename}")
        packages.append(result)
        for path, _, _ in owned_paths:
            owners.setdefault(path, set()).add(_package_key(row["package"]))

    shared_paths = sorted(
        path for path, packages_for_path in owners.items() if len(packages_for_path) > 1
    )
    if shared_paths:
        raise ValueError(f"multiple distributions own installed paths: {shared_paths}")

    site_packages = Path(sysconfig.get_paths()["purelib"]).resolve()
    if site_packages != Path(sysconfig.get_paths()["platlib"]).resolve():
        raise ValueError("table runtime has multiple site-packages roots")
    recorded = _site_packages_inventory(site_packages, distributions)
    _verify_import_roots(site_packages, recorded)

    flatbuffers = lock.get("external_notices", [])
    if len(flatbuffers) != 1 or flatbuffers[0]["package"] != "flatbuffers":
        raise ValueError("FlatBuffers external notice missing")
    if (
        flatbuffers[0]["sha256"] != FLATBUFFERS_LICENSE_SHA256
        or flatbuffers_license.stat().st_size != flatbuffers[0]["size_bytes"]
        or sha256_file(flatbuffers_license) != FLATBUFFERS_LICENSE_SHA256
    ):
        raise ValueError("tagged FlatBuffers license differs")
    if (
        lock.get("publisher_model_sha256") != MODEL_SHA256
        or model.stat().st_size != 7_758_305
        or sha256_file(model) != MODEL_SHA256
    ):
        raise ValueError("publisher SLANet-plus model differs")

    return {
        "status": "installed_table_runtime_pass",
        "wheel_count": len(wheels),
        "wheel_lock_sha256": LOCK_SHA256,
        "installed_distribution_count": len(installed),
        "wheel_payload_files_checked": sum(row["wheel_payload_files"] for row in packages),
        "installed_record_extra_files_checked": sum(
            row["extra_installed_record_files"] for row in packages
        ),
        "site_packages_files_verified": len(recorded),
        "conflicting_shared_paths": shared_paths,
        "embedded_notice_files_verified": notice_count,
        "external_flatbuffers_license_sha256": FLATBUFFERS_LICENSE_SHA256,
        "installed_distribution_contents_verified": True,
        "packages": packages,
    }


def preflight(
    lock_file: Path,
    wheel_dir: Path,
    model: Path,
    flatbuffers_license: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("refusing to overwrite source-free receipt")
    runtime = audit_table_runtime(lock_file, wheel_dir, model, flatbuffers_license)

    from rapid_table import ModelType, RapidTable, RapidTableInput

    image, drawn_ocr_tuple = make_synthetic_table()
    ocr_tuple = _supplied_ocr_tuple(drawn_ocr_tuple)
    validate_ocr_tuple(ocr_tuple)
    engine = RapidTable(
        RapidTableInput(
            model_type=ModelType.SLANETPLUS,
            model_dir_or_path=str(model),
            use_ocr=True,
        )
    )
    providers = engine.table_structure.session.session.get_providers()
    from onnxruntime import InferenceSession

    if (
        not isinstance(engine.table_structure.session.session, InferenceSession)
        or providers != ["CPUExecutionProvider"]
        or engine.ocr_engine is not None
    ):
        raise ValueError("unexpected model provider or OCR engine")
    result = engine(image, ocr_results=[ocr_tuple])
    expected_grid = {
        (row, row, col, col): ocr_tuple[1][row * 3 + col]
        for row in range(2)
        for col in range(3)
    }
    contract = validate_result(
        result, image.shape[1], image.shape[0], ocr_tuple[1], expected_grid
    )
    import numpy as np

    if not np.array_equal(result.imgs[0], image):
        raise ValueError("table result image differs from synthetic input")
    if not math.isfinite(contract["elapsed_seconds_per_image"]) or contract[
        "elapsed_seconds_per_image"
    ] <= 0:
        raise ValueError("table inference elapsed time is invalid")
    if any(name == "rapidocr" or name.startswith("rapidocr.") for name in sys.modules):
        raise ValueError("RapidOCR module was loaded")
    site_packages = Path(sysconfig.get_paths()["purelib"]).resolve()
    recorded = _site_packages_inventory(
        site_packages, importlib.metadata.distributions()
    )
    loaded_vendor_modules = _verify_loaded_vendor_modules(site_packages, recorded)

    receipt = {
        "status": "source_free_table_only_pass",
        "source_pdf_count_opened": 0,
        "gold_count_opened": 0,
        "rapidocr_installed": False,
        "rapidocr_module_loaded": False,
        "ocr_tuple_supplied": True,
        "model_sha256": MODEL_SHA256,
        "model_session_providers": providers,
        "loaded_vendor_modules_verified": loaded_vendor_modules,
        "synthetic_contract": contract,
        "runtime": runtime,
        "python_executable": str(Path(sys.executable).resolve()),
        "preflight_source_sha256": sha256_file(Path(__file__).resolve()),
    }
    write_receipt_exclusive(output, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-lock", type=Path, required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--flatbuffers-license", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = preflight(
        args.wheel_lock,
        args.wheel_dir,
        args.model,
        args.flatbuffers_license,
        args.output,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "runtime"},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
