"""Audit the cached RapidTable wheels against a source-free installed runtime.

This reads package metadata, wheels and installed files only. It never imports a
vendor package or opens a selected PDF, gold record or model checkpoint.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.metadata
import json
import sys
import zipfile
from io import StringIO
from pathlib import Path
from typing import Any

from product_eval.rapidtable_adbuy12_preflight import (
    RUNTIME_LOCK_SHA256,
    sha256_file,
    write_receipt_exclusive,
)

NOTICE_ADDENDUM_SHA256 = "a7924e0ad7130156485d1bfff659c92f485ddb8fe19155900fb07dc9cf51fa01"


def _record_rows(content: str) -> dict[str, tuple[str, str]]:
    rows = {}
    for row in csv.reader(StringIO(content)):
        if len(row) != 3 or row[0] in rows:
            raise ValueError("invalid or duplicate wheel RECORD row")
        rows[row[0]] = (row[1], row[2])
    return rows


def _record_sha256(content: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest())
    return "sha256=" + encoded.rstrip(b"=").decode("ascii")


def _entry_matches(content: bytes, fields: tuple[str, str]) -> bool:
    digest, size = fields
    return digest == _record_sha256(content) and size == str(len(content))


def audit_wheel(
    wheel: Path, distribution: importlib.metadata.Distribution
) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    """Compare one wheel payload and both RECORDs to installed bytes."""
    installed_record_text = distribution.read_text("RECORD")
    if installed_record_text is None:
        raise ValueError(f"installed RECORD missing: {distribution.metadata['Name']}")
    installed_record = _record_rows(installed_record_text)
    mismatches: list[dict[str, Any]] = []
    owned_paths: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(wheel) as archive:
        members = {item.filename for item in archive.infolist() if not item.is_dir()}
        record_name = next(
            (name for name in members if name.endswith(".dist-info/RECORD")), None
        )
        if record_name is None:
            raise ValueError(f"wheel RECORD missing: {wheel.name}")
        wheel_record = _record_rows(archive.read(record_name).decode("utf-8"))
        if wheel_record.keys() != members:
            raise ValueError(f"wheel RECORD member list differs: {wheel.name}")
        if (wheel_record[record_name] != ("", "")
                or installed_record.get(record_name) != ("", "")):
            raise ValueError(f"wheel or installed RECORD self row invalid: {wheel.name}")
        if any(
            ".data/" in name or name.startswith("/") or ".." in Path(name).parts
            for name in members
        ):
            raise ValueError(f"unsupported wheel payload path: {wheel.name}")
        for name in sorted(members - {record_name}):
            content = archive.read(name)
            if not _entry_matches(content, wheel_record[name]):
                raise ValueError(f"wheel RECORD hash or size differs: {wheel.name}: {name}")
            expected_sha256 = hashlib.sha256(content).hexdigest()
            installed_path = Path(distribution.locate_file(name))
            actual_sha256 = (
                sha256_file(installed_path) if installed_path.is_file() else "missing"
            )
            owned_paths.append((str(installed_path).casefold(), name, expected_sha256))
            installed_fields = installed_record.get(name)
            if actual_sha256 != expected_sha256 or installed_fields != wheel_record[name]:
                mismatches.append(
                    {
                        "path": name,
                        "expected_wheel_sha256": expected_sha256,
                        "installed_sha256": actual_sha256,
                        "installed_record_matches_wheel": installed_fields
                        == wheel_record[name],
                    }
                )
    extra_record_paths = sorted(installed_record.keys() - members)
    unhashed_extras = [
        name for name in extra_record_paths if not installed_record[name][0]
    ]
    hashed_extra_mismatches = []
    for name in extra_record_paths:
        fields = installed_record[name]
        if not fields[0]:
            continue
        path = Path(distribution.locate_file(name))
        content = path.read_bytes() if path.is_file() else None
        if content is None or not _entry_matches(content, fields):
            hashed_extra_mismatches.append(name)
    installed_record_sha256 = sha256_file(Path(distribution.locate_file(record_name)))
    return (
        {
            "package": distribution.metadata["Name"],
            "version": distribution.version,
            "wheel_payload_files": len(members) - 1,
            "installed_record_sha256": installed_record_sha256,
            "extra_installed_record_files": len(extra_record_paths),
            "unhashed_extra_installed_record_files": len(unhashed_extras),
            "hashed_extra_installed_record_mismatches": hashed_extra_mismatches,
            "mismatches": mismatches,
        },
        owned_paths,
    )


def verify_notice_addendum(
    addendum_file: Path, wheel_dir: Path, flatbuffers_license: Path
) -> dict[str, Any]:
    """Bind notice bytes to the pinned wheels and the upstream tagged source."""
    if sha256_file(addendum_file) != NOTICE_ADDENDUM_SHA256:
        raise ValueError("RapidTable notice addendum changed")
    addendum = json.loads(addendum_file.read_text(encoding="utf-8"))
    embedded = addendum["embedded_notice_additions"]
    external = addendum["external_notices"]
    if (
        addendum["schema_version"] != 1
        or addendum["base_runtime_lock_sha256"] != RUNTIME_LOCK_SHA256
        or {row["package"] for row in embedded}
        != {"onnxruntime", "opencv-python", "opencv-python-headless", "protobuf", "six"}
        or len(external) != 1
        or external[0]["package"] != "flatbuffers"
    ):
        raise ValueError("RapidTable notice addendum is incomplete")
    notice_count = 0
    for row in embedded:
        wheel = wheel_dir / row["wheel_filename"]
        with zipfile.ZipFile(wheel) as archive:
            for notice in row["notices"]:
                content = archive.read(notice["path"])
                if (
                    len(content) != notice["size_bytes"]
                    or hashlib.sha256(content).hexdigest() != notice["sha256"]
                ):
                    raise ValueError(f"embedded notice differs: {row['package']}")
                notice_count += 1
    flatbuffers = external[0]
    flatbuffers_wheel = next(wheel_dir.glob("flatbuffers-25.12.19-*.whl"))
    with zipfile.ZipFile(flatbuffers_wheel) as archive:
        embedded_flatbuffers_notices = [
            name
            for name in archive.namelist()
            if not name.endswith("/")
            and any(
                term in name.lower()
                for term in ("license", "licence", "notice", "copying")
            )
        ]
    if (
        flatbuffers["source"] != "official_tag"
        or flatbuffers["version"] != "25.12.19"
        or flatbuffers["wheel_has_embedded_notice"] is not False
        or embedded_flatbuffers_notices
        or flatbuffers_license.stat().st_size != flatbuffers["size_bytes"]
        or sha256_file(flatbuffers_license) != flatbuffers["sha256"]
    ):
        raise ValueError("tagged FlatBuffers license differs from addendum")
    return {
        "addendum_sha256": NOTICE_ADDENDUM_SHA256,
        "embedded_notice_files_verified": notice_count,
        "embedded_notice_packages_verified": len(embedded),
        "external_flatbuffers_license_sha256": flatbuffers["sha256"],
        "external_flatbuffers_license_url": flatbuffers["url"],
        "packaging_attribution_complete": False,
    }


def audit_runtime(
    lock_file: Path,
    wheel_dir: Path,
    addendum_file: Path,
    flatbuffers_license: Path,
) -> dict[str, Any]:
    """Verify the pinned wheel bytes and installed wheel payload provenance."""
    if sha256_file(lock_file) != RUNTIME_LOCK_SHA256:
        raise ValueError("RapidTable wheel lock changed")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    wheels = lock.get("wheels")
    if lock.get("schema_version") != 1 or not isinstance(wheels, list) or len(wheels) != 23:
        raise ValueError("RapidTable wheel lock incomplete")
    packages = []
    owners: dict[str, list[tuple[str, str]]] = {}
    for row in wheels:
        filename = row["filename"]
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("unsafe wheel filename")
        wheel = wheel_dir / filename
        if wheel.stat().st_size != row["size_bytes"] or sha256_file(wheel) != row["sha256"]:
            raise ValueError(f"wheel differs from frozen lock: {filename}")
        distribution = importlib.metadata.distribution(row["package"])
        if distribution.version != row["version"]:
            raise ValueError(f"installed version differs: {row['package']}")
        result, owned_paths = audit_wheel(wheel, distribution)
        packages.append(result)
        for absolute_path, member, expected_sha256 in owned_paths:
            owners.setdefault(absolute_path, []).append(
                (row["package"], expected_sha256)
            )
    collisions = [
        {
            "path": path,
            "owners": [
                {"package": package, "expected_sha256": sha256}
                for package, sha256 in owner_rows
            ],
        }
        for path, owner_rows in sorted(owners.items())
        if len({sha256 for _, sha256 in owner_rows}) > 1
    ]
    mismatch_count = sum(len(row["mismatches"]) for row in packages)
    hashed_extra_mismatch_count = sum(
        len(row["hashed_extra_installed_record_mismatches"]) for row in packages
    )
    unhashed_extra_count = sum(
        row["unhashed_extra_installed_record_files"] for row in packages
    )
    notices = verify_notice_addendum(addendum_file, wheel_dir, flatbuffers_license)
    return {
        "status": (
            "installed_wheel_payload_pass"
            if mismatch_count == 0 and hashed_extra_mismatch_count == 0
            else "installed_wheel_payload_hold"
        ),
        "source_pdf_count_opened": 0,
        "gold_count_opened": 0,
        "audit_source_sha256": sha256_file(Path(__file__).resolve()),
        "wheel_lock_sha256": RUNTIME_LOCK_SHA256,
        "python_executable": str(Path(sys.executable).resolve()),
        "wheel_count": len(packages),
        "installed_wheel_payload_files_checked": sum(
            row["wheel_payload_files"] for row in packages
        ),
        "installed_wheel_payload_mismatches": mismatch_count,
        "installed_wheel_payload_contents_verified": mismatch_count == 0,
        "hashed_extra_installed_record_mismatches": hashed_extra_mismatch_count,
        "installed_distribution_contents_verified": mismatch_count == 0
        and hashed_extra_mismatch_count == 0 and unhashed_extra_count == 0,
        "unhashed_extra_installed_record_files": unhashed_extra_count,
        "conflicting_shared_paths": collisions,
        "notices": notices,
        "packages": packages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-lock", type=Path, required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--notice-addendum", type=Path, required=True)
    parser.add_argument("--flatbuffers-license", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite runtime provenance receipt")
    receipt = audit_runtime(
        args.wheel_lock,
        args.wheel_dir,
        args.notice_addendum,
        args.flatbuffers_license,
    )
    write_receipt_exclusive(args.output, receipt)
    print(
        json.dumps(
            {key: value for key, value in receipt.items() if key != "packages"},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
