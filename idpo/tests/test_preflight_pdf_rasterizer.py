from __future__ import annotations

import sys
import types
from pathlib import Path

from idpo.core import preflight


def test_pdfium_satisfies_pdf_rasterizer_preflight(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pypdfium2", types.ModuleType("pypdfium2"))
    assert preflight._check_pdf_rasterizer() == []  # noqa: SLF001


def test_poppler_fallback_requires_pdf2image_and_executable(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    monkeypatch.setitem(sys.modules, "pdf2image", types.ModuleType("pdf2image"))
    monkeypatch.setenv("POPPLER_PATH", r"C:\tools\poppler\bin")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(
        preflight.shutil,
        "which",
        lambda name, path=None: "pdftoppm.exe" if path == r"C:\tools\poppler\bin" else None,
    )
    assert preflight._check_pdf_rasterizer() == []  # noqa: SLF001

    monkeypatch.setattr(preflight.shutil, "which", lambda name, path=None: None)
    assert "No PDF rasterizer" in preflight._check_pdf_rasterizer()[0]  # noqa: SLF001

    monkeypatch.setitem(sys.modules, "pdf2image", None)
    assert "pdf2image" in preflight._check_pdf_rasterizer()[0]  # noqa: SLF001


def test_poppler_winget_install_is_discovered(tmp_path: Path, monkeypatch) -> None:
    binary_dir = tmp_path / "Microsoft" / "WinGet" / "Packages" / "Poppler.Test" / "Library" / "bin"
    binary_dir.mkdir(parents=True)
    (binary_dir / "pdftoppm.exe").touch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("POPPLER_PATH", raising=False)
    monkeypatch.setattr(preflight.shutil, "which", lambda name, path=None: None)

    assert preflight.find_poppler_path() == str(binary_dir)
