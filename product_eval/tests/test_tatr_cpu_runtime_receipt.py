"""Integrity checks for the source-free TATR runtime receipt."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest

from product_eval.tatr_cpu_runtime_receipt import (
    _notice_files,
    _verify_installed_record,
)


class FixtureDistribution:
    def __init__(self, root: Path, files: list[str]):
        self.root = root
        self.files = files
        self.metadata = {"Name": "fixture"}

    def locate_file(self, name: str) -> Path:
        return self.root / name


def test_record_verifies_installed_bytes_and_rejects_tampering(tmp_path: Path) -> None:
    file = tmp_path / "fixture" / "module.py"
    file.parent.mkdir()
    file.write_bytes(b"pinned")
    digest = base64.urlsafe_b64encode(hashlib.sha256(b"pinned").digest()).decode().rstrip("=")
    record = (f"fixture/module.py,sha256={digest},6\n"
              "fixture/__pycache__/module.pyc,,\nfixture-1.dist-info/RECORD,,\n")
    dist = FixtureDistribution(tmp_path, ["fixture/module.py"])

    assert _verify_installed_record(dist, record) == (1, 1, 0)
    file.write_bytes(b"damage")
    with pytest.raises(ValueError, match="wheel RECORD"):
        _verify_installed_record(dist, record)


def test_nested_licenses_are_included_in_notice_inventory(tmp_path: Path) -> None:
    name = "fixture-1.dist-info/licenses/data/windows_x64/BUILD_LICENSES/pdfium.txt"
    file = tmp_path / name
    file.parent.mkdir(parents=True)
    file.write_bytes(b"PDFium notice")

    notices = _notice_files(FixtureDistribution(tmp_path, [name]))

    assert notices == [{"path": name, "sha256": hashlib.sha256(b"PDFium notice").hexdigest(),
                        "size_bytes": len(b"PDFium notice")}]
