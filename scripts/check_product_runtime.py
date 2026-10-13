"""Offline capability checks for the native product extraction Python runtime.

Runs only tiny synthetic local fixtures. Never contacts an AI endpoint, downloads
models, or prints configuration values, credentials, or dependency exception text.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MARKER = "RUNTIME CHECK 12345"
FORMAT_REQUIREMENTS = {
    "text_json": ("core", "text_json"),
    "pdf_native_text": ("core", "pdf_native"),
    "image_ocr": ("core", "image_codecs", "tesseract_ocr"),
    "pdf_scan_extraction": ("core", "pdf_native", "pdf_rasterizer", "tesseract_ocr"),
    # The schema-sampling helper currently requires PDFium; extraction also has Poppler.
    "pdf_scan_schema_sampling": ("core", "pdf_native", "pdfium", "scan_sample"),
    **{extension: ("core", extension) for extension in ("docx", "xlsx", "pptx", "html", "eml")},
}
REMEDIES = {
    "core": "Install the product requirements in this Python environment and run from a complete repository checkout.",
    "text_json": "Check the product intake module and UTF-8 text/JSON support.",
    "pdf_native": "Install a working pypdf package; product PDF intake requires it even when OCR is available.",
    "image_codecs": "Install a working Pillow build with PNG, JPEG, TIFF and BMP codecs.",
    "pdfium": "Install a working pypdfium2 package and Pillow; scanned-PDF schema sampling requires PDFium.",
    "pdf_rasterizer": "Install pypdfium2, or pdf2image plus Poppler (pdftoppm and pdfinfo).",
    "tesseract_ocr": "Install pytesseract and Tesseract with eng language data; check TESSERACT_CMD and TESSDATA_PREFIX.",
    "scan_sample": "Check pypdf, PDFium, Pillow and Tesseract with eng data for scanned-PDF schema samples.",
    "docx": "Install python-docx and lxml; keep the checked-in synthetic Office fixtures.",
    "xlsx": "Install openpyxl; keep the checked-in synthetic Office fixtures.",
    "pptx": "Install python-pptx and lxml; keep the checked-in synthetic Office fixtures.",
    "html": "Install lxml; keep the checked-in synthetic HTML fixture.",
    "eml": "Install lxml for HTML email bodies; keep the checked-in synthetic email fixture.",
    "model_client": "Install a working openai client for the OpenAI-compatible local/cloud provider adapter.",
}


class ConfigurationError(ValueError):
    def __init__(self, code: str, remedy: str):
        super().__init__(code)
        self.code = code
        self.remedy = remedy


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("synthetic_probe_failed")


def _write_pdf(path: Path) -> None:
    """One small standard-font text PDF, without requiring a PDF creation package."""
    stream = f"BT /F1 24 Tf 25 55 Td ({MARKER}) Tj ET".encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 100] "
               b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"]
    body = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(body))
        body.extend(f"{index} 0 obj\n".encode("ascii") + value + b"\nendobj\n")
    xref = len(body)
    body.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        body.extend(f"{offset:010} 00000 n \n".encode("ascii"))
    body.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    path.write_bytes(body)


def _core_probe() -> None:
    importlib.import_module("idpo.cli")
    importlib.import_module("idpo.product_auto.workflow")


def _intake_probe(root: Path) -> None:
    from idpo.agents.intake import IntakeAgent

    sources = {"sample.txt": MARKER, "sample.json": json.dumps({
        "doc_id": "runtime-check", "pages": [{"number": 1, "text": MARKER}],
    })}
    for name, content in sources.items():
        source = root / name
        source.write_text(content, encoding="utf-8")
        documents = IntakeAgent().ingest(str(source))
        _require(len(documents) == 1 and documents[0].pages[0].text == MARKER)


def _pdf_probe(path: Path) -> None:
    from pypdf import PdfReader
    from idpo.agents.intake import IntakeAgent

    _require(len(PdfReader(path).pages) == 1)
    documents = IntakeAgent().ingest(str(path))
    _require(len(documents) == 1 and MARKER in documents[0].pages[0].text)


def _image_fixture():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (640, 100), "white")
    ImageDraw.Draw(image).text((20, 20), MARKER, fill="black", font=ImageFont.load_default(size=40))
    return image


def _image_probe() -> None:
    from PIL import Image

    with _image_fixture() as image:
        for codec in ("PNG", "JPEG", "TIFF", "BMP"):
            with io.BytesIO() as buffer:
                image.save(buffer, format=codec)
                buffer.seek(0)
                with Image.open(buffer) as decoded:
                    decoded.load()
                    _require(decoded.size == image.size)


def _pdfium_probe(path: Path) -> None:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        page = document[0]
        try:
            bitmap = page.render(scale=1)
            try:
                with bitmap.to_pil() as image:
                    _require(image.width > 0 and image.height > 0)
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def _rasterizer_probe(path: Path, pdfium_ready: bool) -> None:
    if pdfium_ready:
        return
    from pdf2image import convert_from_path
    from idpo.core.preflight import find_poppler_path

    # Use the same discovery as extraction, but bound the external probe.
    images = convert_from_path(str(path), first_page=1, last_page=1, dpi=72,
                               poppler_path=find_poppler_path(), timeout=10)
    try:
        _require(len(images) == 1 and images[0].width > 0)
    finally:
        for image in images:
            image.close()


def _ocr_probe() -> None:
    import pytesseract
    from idpo.agents.preprocess import OcrAgent
    from idpo.core.preflight import find_tesseract_cmd

    _require(find_tesseract_cmd() is not None)
    configured = os.environ.get("TESSERACT_CMD", "").strip()
    if configured:
        _require(Path(configured).is_file())
    tessdata = os.environ.get("TESSDATA_PREFIX", "").strip()
    if tessdata:
        _require(Path(tessdata).is_dir())
    agent = OcrAgent()
    data = agent._configure_tesseract(pytesseract)
    with _image_fixture() as image:
        text = pytesseract.image_to_string(image, lang="eng", config=agent._tessdata_config(data, 6, 3), timeout=10)
    _require("12345" in text)


def _scan_sample_probe(root: Path) -> None:
    from idpo.product_auto.brief_draft import _sample_text

    source = root / "scan.pdf"
    with _image_fixture() as image:
        image.save(source, format="PDF", resolution=150)
    text, parser = _sample_text(source, hashlib.sha256(source.read_bytes()).hexdigest())
    _require(parser == "pdfium-tesseract-first-two-pages" and "12345" in text)


def _native_probe(extension: str) -> None:
    from idpo.product_auto.native_formats import parse_native_document
    from product_eval.mixed_format_docling_diagnostic import HEADERS, ROWS, verify_fixtures

    directory = REPO_ROOT / "product_eval" / "fixtures" / "mixed_format_docling_v1"
    manifest = verify_fixtures(directory)
    name = f"order.{extension}"
    document, parsed = parse_native_document(directory / name, manifest["files"][name])
    _require(bool(document.pages) and len(parsed.tables) == 1)
    _require([cell.text for cell in parsed.tables[0].cells] == [value for row in (HEADERS, *ROWS) for value in row])


def _model_client_probe() -> None:
    from openai import OpenAI

    # Construction checks the installed SDK/http client combination. No request is made.
    client = OpenAI(api_key="local-no-auth", base_url="http://127.0.0.1:1/v1", max_retries=0)
    client.close()


def run_check(check_id: str, probe: Callable[[], None]) -> dict[str, object]:
    try:
        # Third-party import warnings and raw exception messages are not part of the public report.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            probe()
        return {"id": check_id, "ready": True, "code": "synthetic_probe_passed"}
    except Exception:
        return {"id": check_id, "ready": False, "code": "synthetic_probe_failed", "remedy": REMEDIES[check_id]}


def provider_report(client_ready: bool, environment: dict[str, str]) -> dict[str, object]:
    model = environment.get("IDPO_AUTO_MODEL", "").strip()
    endpoint = environment.get("IDPO_AUTO_API_BASE_URL", "").strip()
    report: dict[str, object] = {"mode": "disabled", "state": "not_configured", "network_checked": False,
                               "client_ready": client_ready, "configuration_valid": True}
    if not model and not endpoint:
        return report
    report.update(mode="invalid", state="unavailable", configuration_valid=False)
    if not model or not endpoint:
        return {**report, "code": "model_and_endpoint_required"}
    try:
        url = urlsplit(endpoint)
        local = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        if not url.hostname or url.username or url.password or not (local or url.scheme == "https"):
            raise ValueError("invalid_endpoint")
        _ = url.port  # Reject malformed port values without printing the URL.
    except ValueError:
        return {**report, "code": "https_or_loopback_http_endpoint_required"}
    report["mode"] = "local" if local else "cloud"
    if not local and not environment.get("ICORE_API_KEY", "").strip():
        return {**report, "code": "provider_credential_missing"}
    if not client_ready:
        return {**report, "code": "model_client_unavailable"}
    return {**report, "state": "configured_unverified", "configuration_valid": True,
            "code": "endpoint_model_and_credential_not_contacted"}


def build_report(checks: list[dict[str, object]], environment: dict[str, str]) -> dict[str, object]:
    ready = {str(check["id"]): check["ready"] is True for check in checks}
    capabilities = {name: {"ready": all(ready.get(key, False) for key in dependencies),
                           "missing_checks": [key for key in dependencies if not ready.get(key, False)]}
                    for name, dependencies in FORMAT_REQUIREMENTS.items()}
    provider = provider_report(ready.get("model_client", False), environment)
    all_formats = all(capability["ready"] for capability in capabilities.values())
    return {"contract_version": 1, "status": "ready" if all_formats and provider["configuration_valid"] else "unavailable",
            "python_version": sys.version.split()[0], "checks": checks, "capabilities": capabilities,
            "provider": provider, "network_calls_made": False,
            "limits": ["Synthetic dependency checks do not establish extraction accuracy or production capacity.",
                       "Model endpoint reachability, model availability and credential validity are unverified.",
                       "Parser size, page, nested-content and language limits still apply; OCR smoke uses English."]}


def check_runtime() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="docai-runtime-check-") as temporary:
        root = Path(temporary)
        pdf = root / "native.pdf"
        _write_pdf(pdf)
        checks = [run_check("core", _core_probe), run_check("text_json", lambda: _intake_probe(root)),
                  run_check("pdf_native", lambda: _pdf_probe(pdf)), run_check("image_codecs", _image_probe),
                  run_check("pdfium", lambda: _pdfium_probe(pdf))]
        pdfium_ready = checks[-1]["ready"] is True
        checks.append(run_check("pdf_rasterizer", lambda: _rasterizer_probe(pdf, pdfium_ready)))
        checks.append(run_check("tesseract_ocr", _ocr_probe))
        checks.append(run_check("scan_sample", lambda: _scan_sample_probe(root)))
        checks.extend(run_check(extension, lambda suffix=extension: _native_probe(suffix))
                      for extension in ("docx", "xlsx", "pptx", "html", "eml"))
        checks.append(run_check("model_client", _model_client_probe))
    return build_report(checks, dict(os.environ))


@contextlib.contextmanager
def native_environment(config_path: Path | None):
    previous: dict[str, str | None] = {}
    try:
        if config_path is not None:
            try:
                if config_path.stat().st_size > 65536:
                    raise ValueError("config_too_large")
                config = json.loads(config_path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                raise ConfigurationError("invalid_native_config", "Provide a readable private JSON config of at most 64 KiB.") from None
            if not isinstance(config, dict) or not isinstance(config.get("pythonPath"), str):
                raise ConfigurationError("invalid_native_config", "The private native config must define pythonPath as text.")
            # Do not resolve interpreter symlinks: different virtualenvs can point
            # to the same base executable while containing different dependencies.
            if not Path(config["pythonPath"]).is_absolute() or os.path.normcase(os.path.abspath(config["pythonPath"])) != os.path.normcase(os.path.abspath(sys.executable)):
                raise ConfigurationError("wrong_python_runtime", "Run this check with the interpreter named by pythonPath in the native config.")
            for source, target in {"autoModel": "IDPO_AUTO_MODEL", "autoApiBaseUrl": "IDPO_AUTO_API_BASE_URL",
                                   "icoreApiKey": "ICORE_API_KEY", "tesseractPath": "TESSERACT_CMD",
                                   "tessdataDir": "TESSDATA_PREFIX"}.items():
                value = config.get(source)
                if value is not None and not isinstance(value, str):
                    raise ConfigurationError("invalid_native_config", "Provider and OCR settings in the native config must be text.")
                if value:
                    previous[target] = os.environ.get(target)
                    os.environ[target] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit one machine-readable JSON report.")
    parser.add_argument("--native-config", type=Path, help="Read private native settings; run with its pythonPath interpreter.")
    args = parser.parse_args(argv)
    try:
        with native_environment(args.native_config):
            report = check_runtime()
    except ConfigurationError as exc:
        report = {"contract_version": 1, "status": "unavailable", "code": exc.code,
                  "remedy": exc.remedy, "network_calls_made": False}
    except Exception:
        report = {"contract_version": 1, "status": "unavailable", "code": "runtime_preflight_failed",
                  "remedy": "Check that temporary storage is writable and the repository checkout is complete.",
                  "network_calls_made": False}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Product runtime: {report['status']}")
        for name, capability in report.get("capabilities", {}).items():
            print(f"  {'PASS' if capability['ready'] else 'FAIL'} {name}")
        for check in report.get("checks", []):
            if not check["ready"]:
                print(f"  {check['id']}: {check['remedy']}")
        if "provider" in report:
            provider = report["provider"]
            print(f"  Provider: {provider['mode']} / {provider['state']} (no API calls)")
            if not provider["configuration_valid"]:
                print(f"  Provider setup: {provider['code']}")
        if "remedy" in report:
            print(report["remedy"])
        print("These checks establish runtime capability only, not extraction quality or model availability.")
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
