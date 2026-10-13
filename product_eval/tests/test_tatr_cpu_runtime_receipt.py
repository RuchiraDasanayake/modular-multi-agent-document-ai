"""Integrity checks for the source-free TATR runtime receipt."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from product_eval.tatr_cpu_runtime_receipt import (
    _notice_files,
    _raw_installed_record,
    _verify_installed_record,
    _verify_site_packages_inventory,
    _write_new,
)


class FixtureDistribution:
    def __init__(self, root: Path, files: list[str], name: str = "fixture"):
        self.root = root
        self.files = files
        self.metadata = {"Name": name}

    def locate_file(self, name: str) -> Path:
        return self.root / name


def test_record_verifies_installed_bytes_and_rejects_tampering(tmp_path: Path) -> None:
    file = tmp_path / "fixture" / "module.py"
    file.parent.mkdir()
    file.write_bytes(b"pinned")
    digest = base64.urlsafe_b64encode(hashlib.sha256(b"pinned").digest()).decode().rstrip("=")
    record = (f"fixture/module.py,sha256={digest},6\n"
              "fixture/__pycache__/module.pyc,,\nfixture-1.dist-info/RECORD,,\n")
    bytecode = tmp_path / "fixture" / "__pycache__" / "module.pyc"
    bytecode.parent.mkdir()
    bytecode.write_bytes(b"compiled")
    self_record = tmp_path / "fixture-1.dist-info" / "RECORD"
    self_record.parent.mkdir()
    self_record.write_text(record, encoding="utf-8")
    dist = FixtureDistribution(tmp_path, ["fixture/module.py"])

    verified, count, unhashed, bytecode_digest, owned, aliases = _verify_installed_record(
        dist, record, tmp_path
    )
    assert (verified, count, unhashed) == (1, 1, 0)
    assert aliases == 0
    assert {file, bytecode, self_record} <= owned
    bytecode.write_bytes(b"modified")
    assert _verify_installed_record(dist, record, tmp_path)[3] != bytecode_digest
    file.write_bytes(b"damage")
    with pytest.raises(ValueError, match="wheel RECORD"):
        _verify_installed_record(dist, record, tmp_path)


def test_site_packages_inventory_rejects_unowned_importable_files(tmp_path: Path) -> None:
    site_packages = tmp_path / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    owned = site_packages / "owned.py"
    owned.write_text("pass\n", encoding="utf-8")
    assert _verify_site_packages_inventory(site_packages, {owned.resolve()}) == 1
    (site_packages / "sitecustomize.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unowned installed site-packages file"):
        _verify_site_packages_inventory(site_packages, {owned.resolve()})


def test_raw_record_preserves_crlf_and_torchvision_aliases_are_scoped(tmp_path: Path) -> None:
    module = tmp_path / "torchvision" / "module.py"
    module.parent.mkdir()
    module.write_bytes(b"pinned")
    digest = base64.urlsafe_b64encode(hashlib.sha256(b"pinned").digest()).decode().rstrip("=")
    record = ("torchvision/module.py,,\r\n"
              f"torchvision\\module.py,sha256={digest},6\r\n"
              "torchvision-1.dist-info/RECORD,,\r\n"
              "torchvision-1.dist-info\\RECORD,,\r\n")
    record_path = tmp_path / "torchvision-1.dist-info" / "RECORD"
    record_path.parent.mkdir()
    record_path.write_bytes(record.encode())
    dist = FixtureDistribution(tmp_path, ["torchvision-1.dist-info/RECORD"], "torchvision")
    assert _raw_installed_record(dist) == record.encode()
    assert _verify_installed_record(dist, record, tmp_path)[:3] == (1, 0, 1)
    assert _verify_installed_record(dist, record, tmp_path)[-1] == 2
    other = FixtureDistribution(tmp_path, [], "other")
    with pytest.raises(ValueError, match="duplicate installed RECORD path"):
        _verify_installed_record(other, record, tmp_path)


def test_nested_licenses_are_included_in_notice_inventory(tmp_path: Path) -> None:
    name = "fixture-1.dist-info/licenses/data/windows_x64/BUILD_LICENSES/pdfium.txt"
    file = tmp_path / name
    file.parent.mkdir(parents=True)
    file.write_bytes(b"PDFium notice")

    notices = _notice_files(FixtureDistribution(tmp_path, [name]))

    assert notices == [{"path": name, "sha256": hashlib.sha256(b"PDFium notice").hexdigest(),
                        "size_bytes": len(b"PDFium notice")}]


def test_new_receipt_hash_uses_bytes_written_on_this_host(tmp_path: Path) -> None:
    path = tmp_path / "lock.json"
    reported = _write_new(path, {"package": "fixture"})
    assert reported == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        _write_new(path, {"package": "changed"})
