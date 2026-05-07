from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from docai_core.api.app import create_app
from docai_core.persistence import ensure_database_schema
from docai_core.text_acquisition.image_ocr_extractor import ImageOCRDependencyError, ImageOCRExtractor
from docai_core.text_acquisition.router import TextAcquisitionRouter

_INVOICE_TEXT = (
    "Invoice Number: INV-2026-009\n"
    "Invoice Date: 2026-05-04\n"
    "Total Amount: $2,345.67\n"
    "Status: Due\n"
)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "test.db"
    ensure_database_schema(db)
    return db


@pytest.fixture()
def client(tmp_path: Path, db_path: Path) -> TestClient:
    app = create_app(db_path=db_path, runs_dir=tmp_path / "runs")
    return TestClient(app)


def _create_project_and_job(client: TestClient) -> tuple[str, str]:
    project = client.post("/projects", json={"name": "ScannedPdfOCR"}).json()
    project_id = project["project_id"]
    job = client.post(
        f"/projects/{project_id}/jobs",
        json={"schema_id": "invoice_basic", "name": "ocr-job"},
    ).json()
    return project_id, job["job_id"]


def _attach_and_execute(
    client: TestClient,
    job_id: str,
    document_id: str,
) -> tuple[dict, str]:
    run = client.post(f"/jobs/{job_id}/runs", json={"mode": "local_text"}).json()
    run_id = run["run_id"]
    attach = client.post(f"/runs/{run_id}/documents", json={"document_id": document_id})
    assert attach.status_code in (200, 201)
    execute = client.post(f"/runs/{run_id}/execute", json={"index_artifacts": True})
    return execute.json(), run_id


def _upload_document(client: TestClient, job_id: str, file_path: Path, filename: str, content_type: str) -> str:
    with open(file_path, "rb") as fh:
        doc = client.post(
            f"/jobs/{job_id}/documents/upload",
            files={"file": (filename, fh, content_type)},
        ).json()
    return doc["document_id"]


def _make_native_text_pdf(path: Path, pages: list[str]) -> None:
    streams: list[bytes] = []
    for text in pages:
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = b"BT\n/F1 12 Tf\n50 750 Td\n(" + escaped.encode() + b") Tj\nET\n"
        streams.append(stream)

    n = len(pages)
    page_obj_ids = list(range(3, 3 + n))
    stream_obj_ids = list(range(3 + n, 3 + 2 * n))
    font_obj_id = 3 + 2 * n

    def obj(num: int, content: bytes) -> bytes:
        return b"%d 0 obj\n" % num + content + b"\nendobj\n"

    page_refs = b" ".join(b"%d 0 R" % i for i in page_obj_ids)
    objects: list[bytes] = [
        obj(1, b"<<\n/Type /Catalog\n/Pages 2 0 R\n>>"),
        obj(2, b"<<\n/Type /Pages\n/Kids [" + page_refs + b"]\n/Count %d\n>>" % n),
    ]
    for pid, sid in zip(page_obj_ids, stream_obj_ids):
        objects.append(
            obj(
                pid,
                b"<<\n/Type /Page\n/Parent 2 0 R\n"
                b"/MediaBox [0 0 612 792]\n"
                b"/Contents %d 0 R\n" % sid
                + b"/Resources <<\n/Font <<\n/F1 %d 0 R\n>> >> >>" % font_obj_id,
            )
        )
    for sid, stream in zip(stream_obj_ids, streams):
        objects.append(obj(sid, b"<<\n/Length %d\n>>\nstream\n" % len(stream) + stream + b"endstream"))
    objects.append(obj(font_obj_id, b"<<\n/Type /Font\n/Subtype /Type1\n/BaseFont /Helvetica\n>>"))

    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for item in objects:
        offsets.append(len(body))
        body += item

    xref_offset = len(body)
    xref = b"xref\n0 %d\n" % (len(objects) + 1)
    xref += b"0000000000 65535 f \n"
    for off in offsets:
        xref += b"%010d 00000 n \n" % off
    body += xref
    body += b"trailer\n<<\n/Size %d\n/Root 1 0 R\n>>\n" % (len(objects) + 1)
    body += b"startxref\n%d\n%%%%EOF\n" % xref_offset

    path.write_bytes(body)


def _make_scanned_pdf(path: Path, image_path: Path) -> None:
    image = Image.new("RGB", (1500, 1100), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text((70, 80), _INVOICE_TEXT, fill="black", spacing=20)
    image.save(image_path, format="PNG")
    image.save(path, format="PDF", resolution=200.0)


def _artifact_path(artifact_root: str, document_id: str, filename: str) -> Path:
    return Path(artifact_root) / "documents" / document_id / filename


def test_native_text_pdf_still_works_without_scanned_fallback(client: TestClient, tmp_path: Path) -> None:
    _, job_id = _create_project_and_job(client)

    native_pdf = tmp_path / "native.pdf"
    _make_native_text_pdf(native_pdf, [_INVOICE_TEXT.replace("\n", "  ")])
    doc_id = _upload_document(client, job_id, native_pdf, "native.pdf", "application/pdf")

    execute, run_id = _attach_and_execute(client, job_id, doc_id)
    assert execute["status"] == "completed"
    assert execute["is_stub"] is False

    ocr = json.loads(_artifact_path(execute["artifact_root"], doc_id, "ocr_output.json").read_text(encoding="utf-8"))
    assert ocr["engine_id"] == "native_pdf_text_extractor"
    assert "--- page 1 ---" not in ocr["text"]

    final_output = client.get(f"/runs/{run_id}/documents/{doc_id}/final-output").json()
    assert final_output["is_stub"] is False


def test_scanned_pdf_ocr_fallback_extracts_invoice_fields(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, job_id = _create_project_and_job(client)

    scanned_pdf = tmp_path / "scanned.pdf"
    source_image = tmp_path / "source_page.png"
    _make_scanned_pdf(scanned_pdf, source_image)

    render_calls: list[str] = []

    def _fake_render(pdf_path: str, out_dir: Path) -> list[str]:
        render_calls.append(pdf_path)
        page_path = out_dir / "page_1.png"
        page_path.write_bytes(source_image.read_bytes())
        return [str(page_path)]

    monkeypatch.setattr(TextAcquisitionRouter, "_render_pdf_pages_to_images", staticmethod(_fake_render))
    monkeypatch.setattr(ImageOCRExtractor, "_run_tesseract", lambda self, path: _INVOICE_TEXT)

    doc_id = _upload_document(client, job_id, scanned_pdf, "scanned.pdf", "application/pdf")
    execute, run_id = _attach_and_execute(client, job_id, doc_id)

    assert execute["status"] == "completed"
    assert execute["is_stub"] is False
    assert render_calls, "Expected scanned-PDF fallback renderer to be invoked"

    ocr = json.loads(_artifact_path(execute["artifact_root"], doc_id, "ocr_output.json").read_text(encoding="utf-8"))
    assert ocr["engine_id"] == "pdf_scanned_ocr_fallback"
    assert "--- page 1 ---" in ocr["text"]
    assert "Invoice Number: INV-2026-009" in ocr["text"]

    final_output_resp = client.get(f"/runs/{run_id}/documents/{doc_id}/final-output")
    assert final_output_resp.status_code == 200
    final_output = final_output_resp.json()
    assert final_output["is_stub"] is False

    fields = final_output.get("fields", [])
    assert fields
    assert not any(str(field.get("value", "")).startswith("fake_") for field in fields)

    field_map = {field["field_name"]: field for field in fields}
    assert field_map["invoice_number"]["value"] == "INV-2026-009"
    assert field_map["invoice_date"]["value"] == "2026-05-04"
    assert field_map["total_amount"]["value"] == "$2,345.67"

    artifacts = client.get(f"/runs/{run_id}/artifacts").json()["artifacts"]
    names = {Path(item).name for item in artifacts}
    assert "ocr_output.json" in names
    assert "final_output.json" in names
    assert "validation_report.json" in names


def test_scanned_pdf_missing_renderer_dependency_fails_clearly(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, job_id = _create_project_and_job(client)

    scanned_pdf = tmp_path / "scanned_missing_dep.pdf"
    source_image = tmp_path / "source_dep.png"
    _make_scanned_pdf(scanned_pdf, source_image)

    def _raise_missing_renderer(pdf_path: str, out_dir: Path) -> list[str]:
        raise ImageOCRDependencyError(
            "PyMuPDF is required for scanned PDF OCR fallback. Install with: pip install pymupdf"
        )

    monkeypatch.setattr(
        TextAcquisitionRouter,
        "_render_pdf_pages_to_images",
        staticmethod(_raise_missing_renderer),
    )

    doc_id = _upload_document(client, job_id, scanned_pdf, "scanned_missing_dep.pdf", "application/pdf")
    run = client.post(f"/jobs/{job_id}/runs", json={"mode": "local_text"}).json()
    run_id = run["run_id"]
    client.post(f"/runs/{run_id}/documents", json={"document_id": doc_id})

    execute = client.post(f"/runs/{run_id}/execute", json={"index_artifacts": False})
    assert execute.status_code == 424
    detail = execute.json().get("detail", "")
    assert "PyMuPDF" in detail

    # Ensure failure is persisted, not fake completion.
    with sqlite3.connect(client.app.state.db_path) as conn:
        status_row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert status_row is not None
    assert status_row[0] == "failed"
