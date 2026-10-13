"""Focused fail-closed fixtures for the isolated RapidTable runtime audit."""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from product_eval import rapidtable_table_only_preflight as preflight


class _Distribution:
    version = "1.0"

    def __init__(self, root: Path, name: str, files: tuple[str, ...] = ()) -> None:
        self.root = root
        self.metadata = {"Name": name}
        self.files = [Path(file) for file in files]

    def locate_file(self, member: Path) -> Path:
        return self.root / member


class RapidTableTableOnlyPreflightTests(TestCase):
    @staticmethod
    def _site_fixture(root: Path) -> tuple[Path, _Distribution]:
        site = root / "site-packages"
        files = ("example/__init__.py", "example-1.0.dist-info/RECORD")
        for name in files:
            path = site / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture\n")
        return site, _Distribution(site, "example", files)

    def test_exact_site_packages_inventory_passes(self) -> None:
        with TemporaryDirectory() as directory:
            site, distribution = self._site_fixture(Path(directory))
            self.assertEqual(
                len(preflight._site_packages_inventory(site.resolve(), [distribution])),
                2,
            )

    def test_unrecorded_importable_file_fails(self) -> None:
        with TemporaryDirectory() as directory:
            site, distribution = self._site_fixture(Path(directory))
            (site / "rogue.py").write_text("value = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1 unrecorded"):
                preflight._site_packages_inventory(site.resolve(), [distribution])

    def test_unrecorded_namespace_directory_fails(self) -> None:
        with TemporaryDirectory() as directory:
            site, distribution = self._site_fixture(Path(directory))
            (site / "rogue_namespace").mkdir()
            with self.assertRaisesRegex(ValueError, "unrecorded or missing directories"):
                preflight._site_packages_inventory(site.resolve(), [distribution])

    def test_recorded_import_path_extension_still_fails(self) -> None:
        with TemporaryDirectory() as directory:
            site, distribution = self._site_fixture(Path(directory))
            (site / "redirect.pth").write_text("../rogue\n", encoding="utf-8")
            distribution.files.append(Path("redirect.pth"))
            with self.assertRaisesRegex(ValueError, "import-path extension"):
                preflight._site_packages_inventory(site.resolve(), [distribution])

    def test_duplicate_normalized_distribution_names_fail(self) -> None:
        first = _Distribution(Path("."), "opencv_python")
        second = _Distribution(Path("."), "opencv-python")
        with self.assertRaisesRegex(ValueError, "duplicate installed distribution"):
            preflight._installed_distributions(
                [first, second], {"opencv-python": "1.0"}
            )

    def test_installed_record_content_hash_is_anchored_to_lock(self) -> None:
        row = {"package": "example", "installed_record_sha256": "expected"}
        preflight._require_installed_record_hash(
            row, {"installed_record_sha256": "expected"}
        )
        with self.assertRaisesRegex(ValueError, "installed RECORD differs"):
            preflight._require_installed_record_hash(
                row, {"installed_record_sha256": "rogue-extra-file"}
            )

    def test_shadowed_vendor_import_root_fails(self) -> None:
        with TemporaryDirectory() as directory:
            site = (Path(directory) / "site-packages").resolve()
            site.mkdir()
            shadow = Path(directory) / "rapid_table.py"
            shadow.write_text("", encoding="utf-8")
            spec = SimpleNamespace(origin=str(shadow), submodule_search_locations=None)
            with (
                patch.object(preflight, "VENDOR_IMPORT_ROOTS", ("rapid_table",)),
                patch.object(preflight.importlib.util, "find_spec", return_value=spec),
                self.assertRaisesRegex(ValueError, "unsealed file"),
            ):
                preflight._verify_import_roots(site, set())

    def test_loaded_vendor_module_from_unsealed_file_fails(self) -> None:
        with TemporaryDirectory() as directory:
            site = (Path(directory) / "site-packages").resolve()
            site.mkdir()
            module = ModuleType("fixture_vendor")
            module.__file__ = str(Path(directory) / "fixture_vendor.py")
            with (
                patch.object(preflight, "VENDOR_TOP_LEVEL", {"fixture_vendor"}),
                patch.dict(sys.modules, {"fixture_vendor": module}),
                self.assertRaisesRegex(ValueError, "unsealed file"),
            ):
                preflight._verify_loaded_vendor_modules(site, set())

    def test_supplied_ocr_text_is_distinct_from_drawn_text(self) -> None:
        boxes = object()
        scores = (0.99, 0.99)
        result = preflight._supplied_ocr_tuple((boxes, ("Item", "Qty"), scores))
        self.assertIs(result[0], boxes)
        self.assertEqual(result[1], ("SUPPLIED_0_Item", "SUPPLIED_1_Qty"))
        self.assertEqual(result[2], scores)
