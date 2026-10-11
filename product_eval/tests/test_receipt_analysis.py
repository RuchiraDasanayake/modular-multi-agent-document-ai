from __future__ import annotations

import json
from pathlib import Path

import pytest

from product_eval.contracts import ContractError
from product_eval.receipt_analysis import summarize_receipts


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    report_dir = tmp_path / "report"
    data_dir = tmp_path / "data"
    run_dir = data_dir / "product_runs" / "gate_a"
    _write_json(report_dir / "provenance.json", {"gate_id": "gate", "git_commit": "abc", "run_ids": ["gate_a"]})
    _write_json(report_dir / "execution-report.json", {
        "run_ids": ["gate_a"], "documents": 2, "distinct_sources": 2,
        "status_counts": {"needs_review": 2, "processed": 0, "unsupported": 0, "failed": 0},
    })
    _write_json(run_dir / "run.json", {
        "run_id": "gate_a", "model_configured": False, "doc_count": 2,
        "resource_usage": {
            "worker_process_cpu_ms": 10.0,
            "worker_rss_start_bytes": 100,
            "worker_rss_end_bytes": 200,
        },
    })
    rows = []
    for doc_id, page in [
        ("native", {"page": 1, "engine": "native_text", "pdf_page_index": 0}),
        ("scan", {
            "page": 1, "engine": "tesseract", "pdf_page_index": 0,
            "pdf_renderer": "poppler", "pdf_renderer_fallback_reason": "pdfium_render_failed",
            "pdf_rendered_dpi": 300, "pdf_render_size_px": [1000, 1500], "retry_path": "quick",
        }),
    ]:
        rows.append({
            "doc_id": doc_id, "source_file": f"{doc_id}.pdf", "document_status": "needs_review",
            "page_count": 1, "model_call_count": 0, "model_sdk_attempt_count": 0,
            "resource_usage": {
                "worker_process_cpu_ms": 4.0, "worker_rss_before_bytes": 100,
                "worker_rss_after_bytes": 150,
            },
        })
        _write_json(run_dir / "docs" / doc_id / "result.json", {
            "run_id": "gate_a", "document_status": "needs_review",
            "candidate": {"doc_id": doc_id, "document_status": "needs_review"},
            "ocr_pages": [page], "model_calls": [],
            "api_cost_usd": None, "compute_cost_usd": None, "total_cost_usd": None,
        })
    (run_dir / "manifest.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return report_dir, data_dir


def test_receipt_summary_separates_native_and_rendered_pdf_pages(tmp_path: Path) -> None:
    report_dir, data_dir = _fixture(tmp_path)
    result = summarize_receipts(report_dir, data_dir)

    assert result["documents"] == result["distinct_sources_verified"] == 2
    assert result["pdf_pages"] == 2
    assert result["pdf_ocr_pages"] == 1
    assert result["pdf_ocr_renderers"] == {"poppler": 1}
    assert result["pdf_renderer_fallback_reasons"] == {"pdfium_render_failed": 1}
    assert result["ocr_retry_paths"] == {"quick": 1}
    assert result["sum_document_worker_process_cpu_ms"] == 8.0
    assert result["sum_run_worker_process_cpu_ms"] == 10.0
    assert result["maximum_observed_worker_rss_boundary_bytes"] == 200
    assert result["missing_provenance_or_resource"] == {}
    assert result["cost_coverage"]["documents_unpriced_total_cost_usd"] == 2


def test_receipt_summary_reports_missing_ocr_renderer_without_inventing_it(tmp_path: Path) -> None:
    report_dir, data_dir = _fixture(tmp_path)
    path = data_dir / "product_runs" / "gate_a" / "docs" / "scan" / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["ocr_pages"][0].pop("pdf_renderer")
    _write_json(path, result)

    summary = summarize_receipts(report_dir, data_dir)
    assert summary["pdf_ocr_pages"] == 1
    assert summary["pdf_ocr_renderers"] == {}
    assert summary["missing_provenance_or_resource"]["pdf_ocr_renderer"] == 1


def test_receipt_summary_rejects_status_mismatch(tmp_path: Path) -> None:
    report_dir, data_dir = _fixture(tmp_path)
    path = data_dir / "product_runs" / "gate_a" / "docs" / "scan" / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    result["document_status"] = "failed"
    _write_json(path, result)

    with pytest.raises(ContractError, match="sidecar status differs"):
        summarize_receipts(report_dir, data_dir)
