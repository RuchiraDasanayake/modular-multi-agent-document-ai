from __future__ import annotations

import importlib.util
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from product_eval import mixed_format_native_diagnostic as native


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "mixed_format_docling_v1"
NATIVE_PACKAGES_AVAILABLE = all(importlib.util.find_spec(name) is not None for name in
                                ("docx", "openpyxl", "pptx", "lxml", "psutil"))


@unittest.skipUnless(NATIVE_PACKAGES_AVAILABLE, "native parser diagnostic dependencies absent")
class NativeFormatDiagnosticTests(unittest.TestCase):
    def test_all_locked_formats_have_exact_cells_and_resolvable_native_locators(self) -> None:
        manifest = native.verify_fixtures(FIXTURES)
        expected = [value for row in native.EXPECTED_GRID for value in row]
        for name in native.FIXTURE_NAMES:
            with self.subTest(name=name):
                path = FIXTURES / name
                self.assertEqual(native._sha256(path), manifest["files"][name])
                record = native.parse_source(path)
                self.assertEqual([cell["text"] for cell in record["cells"]], expected)
                self.assertEqual(len(record["cells"]), 9)
                for cell in record["cells"]:
                    self.assertEqual(native.resolve_locator(path, cell["locator"]), cell["text"])
                    self.assertIsNone(cell["cell_bbox"])
                measured = native.worker(FIXTURES, name)
                self.assertEqual(measured["status"], "match")
                self.assertTrue(measured["fixture_exact_match"])

    def test_eml_html_alternative_retains_part_path_and_dom_address(self) -> None:
        record = native.parse_source(FIXTURES / "order.eml")
        self.assertEqual(record["selected_body_type"], "text/html")
        self.assertEqual(record["selected_mime_path"], [1])
        self.assertEqual(record["subject"], "Synthetic order SYN-1001")
        first = record["cells"][0]
        self.assertEqual(first["locator"]["mime_path"], [1])
        self.assertEqual(first["locator"]["xpath"], "/html/body/table/thead/tr/th[1]")

    def test_docx_paragraph_locator_and_source_hash_guard(self) -> None:
        path = FIXTURES / "order.docx"
        record = native.parse_source(path)
        self.assertEqual([native.resolve_locator(path, item["locator"])
                          for item in record["paragraphs"]],
                         ["Synthetic order SYN-1001", "Order date: 2020-01-01"])
        with TemporaryDirectory() as temporary:
            destination = Path(temporary)
            for name in (*native.FIXTURE_NAMES, "manifest.json"):
                shutil.copy2(FIXTURES / name, destination / name)
            (destination / "order.html").write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Source hash mismatch"):
                native.worker(destination, "order.html")


if __name__ == "__main__":
    unittest.main()
