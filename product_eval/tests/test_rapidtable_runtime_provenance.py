"""Focused checks for source-free wheel/installed-byte comparison."""

import csv
import hashlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZipFile

from product_eval.rapidtable_runtime_provenance import (
    _record_sha256,
    audit_wheel,
)


class _Distribution:
    version = "1.0"

    def __init__(self, root: Path, record: str) -> None:
        self.metadata = {"Name": "example"}
        self.root = root
        self.record = record

    def read_text(self, name: str) -> str | None:
        return self.record if name == "RECORD" else None

    def locate_file(self, name: str) -> Path:
        return self.root / name


def _record(files: dict[str, bytes]) -> str:
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for name, content in files.items():
        writer.writerow((name, _record_sha256(content), len(content)))
    writer.writerow(("example-1.0.dist-info/RECORD", "", ""))
    return output.getvalue()


class RapidTableRuntimeProvenanceTests(TestCase):
    def _fixture(self, root: Path) -> tuple[Path, _Distribution]:
        files = {
            "example/__init__.py": b"value = 1\n",
            "example-1.0.dist-info/METADATA": b"Name: example\nVersion: 1.0\n",
        }
        record = _record(files)
        wheel = root / "example-1.0-py3-none-any.whl"
        with ZipFile(wheel, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr("example-1.0.dist-info/RECORD", record)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (root / "example-1.0.dist-info/RECORD").write_text(
            record, encoding="utf-8", newline=""
        )
        return wheel, _Distribution(root, record)

    def test_exact_installed_payload_and_record_pass(self) -> None:
        with TemporaryDirectory() as directory:
            wheel, distribution = self._fixture(Path(directory))
            result, owned_paths = audit_wheel(wheel, distribution)
            self.assertEqual(result["mismatches"], [])
            self.assertEqual(result["wheel_payload_files"], 2)
            self.assertEqual(len(owned_paths), 2)

    def test_modified_installed_byte_fails_even_with_original_record(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, distribution = self._fixture(root)
            (root / "example/__init__.py").write_bytes(b"value = 2\n")
            result, _ = audit_wheel(wheel, distribution)
            self.assertEqual(len(result["mismatches"]), 1)
            self.assertEqual(result["mismatches"][0]["path"], "example/__init__.py")
            self.assertTrue(result["mismatches"][0]["installed_record_matches_wheel"])

    def test_modified_installed_record_fails_even_with_original_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, distribution = self._fixture(root)
            distribution.record = distribution.record.replace(
                _record_sha256(b"value = 1\n"), _record_sha256(b"value = 2\n")
            )
            (root / "example-1.0.dist-info/RECORD").write_text(
                distribution.record, encoding="utf-8", newline=""
            )
            result, _ = audit_wheel(wheel, distribution)
            self.assertEqual(len(result["mismatches"]), 1)
            self.assertEqual(
                result["mismatches"][0]["installed_sha256"],
                hashlib.sha256(b"value = 1\n").hexdigest(),
            )
            self.assertFalse(result["mismatches"][0]["installed_record_matches_wheel"])

    def test_hashed_installer_extra_is_checked_against_installed_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, distribution = self._fixture(root)
            installer = root / "example-1.0.dist-info/INSTALLER"
            installer.write_bytes(b"pip")
            distribution.record += (
                f"example-1.0.dist-info/INSTALLER,{_record_sha256(b'pip')},3\n"
            )
            (root / "example-1.0.dist-info/RECORD").write_text(
                distribution.record, encoding="utf-8", newline=""
            )
            result, _ = audit_wheel(wheel, distribution)
            self.assertEqual(result["hashed_extra_installed_record_mismatches"], [])
            installer.write_bytes(b"uv")
            result, _ = audit_wheel(wheel, distribution)
            self.assertEqual(
                result["hashed_extra_installed_record_mismatches"],
                ["example-1.0.dist-info/INSTALLER"],
            )

    def test_corrupt_wheel_record_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, distribution = self._fixture(root)
            with ZipFile(wheel, "w") as archive:
                archive.writestr("example/__init__.py", b"value = 1\n")
                archive.writestr(
                    "example-1.0.dist-info/METADATA",
                    b"Name: example\nVersion: 1.0\n",
                )
                archive.writestr("example-1.0.dist-info/RECORD", "bad,row\n")
            with self.assertRaisesRegex(ValueError, "RECORD row"):
                audit_wheel(wheel, distribution)

    def test_installed_record_requires_unhashed_self_row(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            wheel, distribution = self._fixture(root)
            distribution.record = distribution.record.replace(
                "example-1.0.dist-info/RECORD,,\n", ""
            )
            with self.assertRaisesRegex(ValueError, "self row"):
                audit_wheel(wheel, distribution)
