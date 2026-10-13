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
import platform
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from product_eval.rapidtable_adbuy12_preflight import (
    MODEL_SHA256,
    make_synthetic_table,
    sha256_file,
    validate_ocr_tuple,
    validate_result,
    write_receipt_exclusive,
)
from product_eval.rapidtable_runtime_provenance import audit_wheel

LOCK_SHA256 = "487135bf5438212ea5ac46778b0e53e15c0314fb34b28cec83043e29834447a6"
FLATBUFFERS_LICENSE_SHA256 = (
    "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
)
FORBIDDEN_PACKAGES = {"rapidocr", "opencv-python-headless"}


def _package_key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _canonical_text_sha256(path: Path) -> str:
    """Pin Git text regardless of Windows checkout line-ending conversion."""
    content = path.read_bytes()
    if b"\r" in content.replace(b"\r\n", b""):
        raise ValueError("lock has unsupported line endings")
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


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
    installed = {
        _package_key(dist.metadata["Name"]): dist.version for dist in distributions
    }
    if len(distributions) != len(installed) or installed != expected:
        raise ValueError(f"installed distributions differ from lock: {installed}")
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
        distribution = importlib.metadata.distribution(row["package"])
        result, owned_paths = audit_wheel(wheel, distribution)
        if result["mismatches"] or result["hashed_extra_installed_record_mismatches"]:
            raise ValueError(f"installed wheel bytes or RECORD differ: {filename}")
        if result["unhashed_extra_installed_record_files"]:
            raise ValueError(f"installed RECORD has unhashed extra entries: {filename}")
        packages.append(result)
        for path, _, _ in owned_paths:
            owners.setdefault(path, set()).add(_package_key(row["package"]))

    shared_paths = sorted(path for path, packages_for_path in owners.items() if len(packages_for_path) > 1)
    if shared_paths:
        raise ValueError(f"multiple distributions own installed paths: {shared_paths}")

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
        "installed_record_extra_files_checked": sum(row["extra_installed_record_files"] for row in packages),
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

    image, ocr_tuple = make_synthetic_table()
    validate_ocr_tuple(ocr_tuple)
    engine = RapidTable(
        RapidTableInput(
            model_type=ModelType.SLANETPLUS,
            model_dir_or_path=str(model),
            use_ocr=True,
        )
    )
    providers = engine.table_structure.session.session.get_providers()
    if providers != ["CPUExecutionProvider"] or engine.ocr_engine is not None:
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
    if any(name == "rapidocr" or name.startswith("rapidocr.") for name in sys.modules):
        raise ValueError("RapidOCR module was loaded")

    receipt = {
        "status": "source_free_table_only_pass",
        "source_pdf_count_opened": 0,
        "gold_count_opened": 0,
        "rapidocr_installed": False,
        "rapidocr_module_loaded": False,
        "ocr_tuple_supplied": True,
        "model_sha256": MODEL_SHA256,
        "model_session_providers": providers,
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
    print(json.dumps({key: value for key, value in result.items() if key != "runtime"}, sort_keys=True))


if __name__ == "__main__":
    main()
