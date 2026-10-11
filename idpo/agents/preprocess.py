"""Document preprocessing agents: OCR, deskew, denoise, and table/form detection."""

from __future__ import annotations

import math
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from idpo.agents.base import Agent, AgentContext
from idpo.agents.degarble import degarble, is_garbled
from idpo.core.contracts import AgentMessage
from idpo.core.preflight import find_poppler_path, find_tesseract_cmd
from idpo.core.types import AgentResult, Document, Page, StageSignal

# A PaddleOCR engine keeps working memory for every input shape it has run (about 0.5 GB per shape at the
# default batch size), so the process shares one engine per language, serialises its calls, and pads
# recognition crops up to a few fixed widths.
_PADDLE_ENGINES: dict[str, Any] = {}
_PADDLE_LOCK = threading.Lock()
# PDFium is not thread-safe, including calls made on different documents.
_PDFIUM_RENDER_LOCK = threading.Lock()
_PADDLE_REC_WIDTH_STEP_PX = 320
_DENOISE_MIN_SHORT_SIDE_PX = 1600
# Boxes whose vertical centres differ by less than this fraction of the shorter box height share a row.
_ROW_CENTER_TOLERANCE = 0.5
_OCR_NOISE_RETRY_THRESHOLD = 0.12


class _TesseractTimeout(Exception):
    def __init__(self, partial_text: str = "") -> None:
        super().__init__("Tesseract exceeded the product OCR time budget")
        self.partial_text = partial_text


@dataclass(frozen=True)
class _TesseractBudget:
    call_timeout_s: float
    deadline: float

    def next_timeout_s(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise _TesseractTimeout()
        return min(self.call_timeout_s, remaining)


def _call_tesseract(method, *args, budget: _TesseractBudget | None = None, **kwargs):
    if budget is not None:
        kwargs["timeout"] = budget.next_timeout_s()
    try:
        return method(*args, **kwargs)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        if budget is not None and (isinstance(exc, subprocess.TimeoutExpired) or "timeout" in str(exc).lower()):
            raise _TesseractTimeout() from exc
        raise


def _bucket_recognition_widths(engine: Any, step: int = _PADDLE_REC_WIDTH_STEP_PX) -> None:
    """Pad each recognition batch up to a multiple of ``step`` pixels wide."""
    recognizer = getattr(engine, "text_recognizer", None)
    resize = getattr(recognizer, "resize_norm_img", None)
    shape = getattr(recognizer, "rec_image_shape", None)
    if resize is None or not shape or len(shape) < 2:
        return
    height = int(shape[1])

    def bucketed(img: Any, max_wh_ratio: float) -> Any:
        width = math.ceil(height * max_wh_ratio / step) * step
        return resize(img, (width + 0.5) / height)

    recognizer.resize_norm_img = bucketed


def _paddle_engine(paddle_ocr_cls: Any, model_lang: str) -> Any:
    """Return the shared engine for ``model_lang``; the caller must hold ``_PADDLE_LOCK``."""
    engine = _PADDLE_ENGINES.get(model_lang)
    if engine is None:
        # Lower det_db_thresh catches more text in degraded/low-contrast scans.
        # det_db_box_thresh set lower to avoid dropping partial characters.
        # use_angle_cls handles rotated/skewed fax pages.
        # Single-crop recognition batches keep the memory held per cached shape small.
        # Paddle's default of 10 math threads oversubscribes consumer CPUs and runs slower than 4.
        engine = paddle_ocr_cls(
            use_angle_cls=True,
            lang=model_lang,
            show_log=False,
            det_db_thresh=0.2,
            det_db_box_thresh=0.4,
            det_db_unclip_ratio=1.8,
            rec_batch_num=1,
            cpu_threads=min(4, os.cpu_count() or 4),
        )
        _bucket_recognition_widths(engine)
        _PADDLE_ENGINES[model_lang] = engine
    return engine


def _box_extent(box: Any) -> tuple[float, float, float] | None:
    """Return (top, bottom, left) of an OCR quadrilateral, or None when it carries no usable geometry."""
    try:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
    except (TypeError, ValueError, IndexError):
        return None
    if not xs or max(ys) <= min(ys):
        return None
    return min(ys), max(ys), min(xs)


def _join_boxes_into_rows(boxes: list[tuple[tuple[float, float, float] | None, str]]) -> list[str]:
    """Rebuild visual lines from OCR boxes so a label and the value printed beside it stay on one line."""
    located: list[tuple[float, float, float, str]] = []
    for extent, text in boxes:
        if extent is None:
            return [text for _, text in boxes]
        located.append((*extent, text))
    rows: list[list[tuple[float, float, float, str]]] = []
    for box in sorted(located, key=lambda b: (b[0] + b[1]) / 2):
        center, height = (box[0] + box[1]) / 2, box[1] - box[0]
        if rows:
            row = rows[-1]
            row_center = sum((b[0] + b[1]) / 2 for b in row) / len(row)
            row_height = sum(b[1] - b[0] for b in row) / len(row)
            if abs(center - row_center) <= _ROW_CENTER_TOLERANCE * min(height, row_height):
                row.append(box)
                continue
        rows.append([box])
    return ["  ".join(b[3] for b in sorted(row, key=lambda b: b[2])) for row in rows]


def normalize_text(text: str) -> str:
    text = text.replace("\u0000", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _save_processed_image(ctx: AgentContext, doc_id: str, page_number: int, stage: str, image) -> str:
    image_root = Path(ctx.artifact_store.root) / "derived_images"
    image_root.mkdir(parents=True, exist_ok=True)
    image_path = image_root / f"{doc_id}_p{page_number}_{stage}_{uuid.uuid4().hex[:8]}.png"
    image.save(image_path, format="PNG")
    return str(image_path)


def _render_pdf_page(pdf_path: str, page_index: int, dpi: int):
    """Render one PDF page to an owned RGB image, using PDFium then Poppler."""
    try:
        import pypdfium2 as pdfium

        with _PDFIUM_RENDER_LOCK:
            pdf = pdfium.PdfDocument(pdf_path)
            try:
                if 0 <= page_index < len(pdf):
                    page = pdf[page_index]
                    try:
                        bitmap = page.render(scale=dpi / 72)
                        try:
                            # to_pil() may share PDFium's buffer. Detach before closing it.
                            return bitmap.to_pil().convert("RGB").copy()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
            finally:
                pdf.close()
    except Exception:
        pass
    try:
        from pdf2image import convert_from_path

        poppler_path = OcrAgent()._find_poppler_path()
        images = convert_from_path(
            pdf_path, first_page=page_index + 1, last_page=page_index + 1, poppler_path=poppler_path, dpi=dpi
        )
        if images:
            return images[0]
    except Exception:
        pass
    return None


def rasterize_pdf_page(page: Page, doc_id: str, ctx: AgentContext, dpi: int = 300) -> Page:
    """Replace a PDF page's image_path with a rendered PNG so image stages operate on one page."""
    path = page.image_path or ""
    if not path.lower().endswith(".pdf"):
        return page
    page_index = int(page.metadata.get("pdf_page_index", max(page.number - 1, 0)) or 0)
    image = _render_pdf_page(path, page_index, dpi)
    if image is None:
        return page
    metadata = dict(page.metadata or {})
    metadata["pdf_source_path"] = path
    metadata["pdf_rendered_dpi"] = dpi
    rendered_path = _save_processed_image(ctx, doc_id, page.number, "pdf_render", image)
    return Page(number=page.number, text=page.text, raw_text=page.raw_text, image_path=rendered_path, metadata=metadata)

def mock_ocr(text: str, passes: int = 1) -> str:
    cleaned = text
    for _ in range(max(passes, 1)):
        cleaned = re.sub(r"[\[\]{}<>_~]", "", cleaned)
        cleaned = re.sub(r"\b[0-9]O\b", "10", cleaned)
        cleaned = re.sub(r"\b1D\b", "ID", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()

class OcrAgent(Agent):
    name = "ocr"
    version = "v1"
    input_contract = {"document": "Document", "input_artifact_id": "str|None"}
    output_contract = {"document": "Document", "artifact_id": "str", "signal": "StageSignal"}
    _cached_tessdata_dir: Path | None = None
    _tessdata_configured: bool = False
    _cached_poppler_path: str | None = None
    _poppler_searched: bool = False

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        input_artifact_id = payload.get("input_artifact_id")
        engine = payload.get("engine") or ctx.config.preprocessing.ocr_engine
        passes = int(payload.get("passes", ctx.config.preprocessing.ocr_passes))
        lang = payload.get("lang") or ctx.config.preprocessing.ocr_lang
        psm = int(payload.get("psm", ctx.config.preprocessing.ocr_psm))
        oem = int(payload.get("oem", ctx.config.preprocessing.ocr_oem))
        dpi = int(payload.get("dpi", ctx.config.preprocessing.ocr_dpi))
        alt_psm = payload.get("alt_psm", ctx.config.preprocessing.ocr_alt_psm)
        # Adaptive OCR: reduce passes/variants for high-quality documents
        quality_bin = payload.get("quality_bin", "")
        content_profile = payload.get("content_profile", "")
        if quality_bin == "A" and passes > 1:
            passes = 1  # Single pass is sufficient for high-quality scans
        if quality_bin == "A" and content_profile == "text-heavy":
            alt_psm = []  # Skip alt PSM variants for clean text-heavy docs
        alt_psm_list = self._normalize_alt_psm(alt_psm, passes)
        initial_single_pass = bool(
            payload.get("initial_single_pass", ctx.config.preprocessing.ocr_initial_single_pass)
        )
        settings = {
            "lang": lang,
            "psm": psm,
            "oem": oem,
            "dpi": dpi,
            "alt_psm": alt_psm_list,
            "single_pass": initial_single_pass,
        }
        cleaned_pages: list[Page] = []
        failure_reason = None
        used_image_ocr = False
        rerun_attempted_pages = 0
        rerun_used_pages = 0
        rerun_min_gain = max(0.0, float(getattr(ctx.config.preprocessing, "ocr_rerun_min_score_gain", 0.03)))
        for page in doc.pages:
            raw = page.raw_text or page.text
            page_failure = None
            is_garbled_page = page.metadata.get("garbled_pdf", False) or is_garbled(raw)
            if page.image_path:
                native_text = normalize_text(raw)
                if native_text and not is_garbled_page and self._looks_like_native_text(native_text):
                    ocr_text = native_text
                    page_used = False
                    ocr_meta = {
                        "ocr_lang": lang,
                        "ocr_psm": psm,
                        "ocr_oem": oem,
                        "ocr_variant": "native_text_short_circuit",
                        "ocr_confidence": 99.0,
                        "ocr_rotation_applied": 0,
                        "ocr_engine_used": "native_text",
                    }
                else:
                    page = rasterize_pdf_page(page, doc.doc_id, ctx, dpi)
                    page_settings = dict(settings)
                    call_timeout = ctx.config.preprocessing.ocr_tesseract_call_timeout_s
                    page_budget = ctx.config.preprocessing.ocr_tesseract_page_budget_s
                    if call_timeout is not None and page_budget is not None:
                        page_settings["tesseract_budget"] = _TesseractBudget(
                            call_timeout_s=call_timeout,
                            deadline=time.monotonic() + page_budget,
                        )
                    ocr_text, page_used, page_failure, ocr_meta = self._ocr_image(
                        page, page_settings, engine_name=str(engine)
                    )
                used_image_ocr = used_image_ocr or page_used
                initial_conf = self._safe_confidence(ocr_meta.get("ocr_confidence"))
                initial_noise_ratio = self._ocr_noise_ratio(ocr_text)
                rerun_reason = self._ocr_rerun_reason(ocr_text, initial_conf, ctx)
                candidate_count = int(ocr_meta.get("ocr_candidate_count") or 0)
                retry_path = None
                rerun_used = False
                if (
                    page_used
                    and not page_failure
                    and (ocr_text or initial_single_pass)
                    and rerun_reason is not None
                    and int(ctx.config.preprocessing.ocr_max_reruns_per_page) > 0
                ):
                    rerun_attempted_pages += 1
                    current_score = self._score_ocr_candidate(ocr_text, initial_conf)
                    quick_accepted = False
                    quick_attempted = False
                    quick_text = ""
                    quick_failure = None
                    quick_meta: dict[str, object] = {}
                    quick_score = -1.0
                    if (
                        initial_single_pass
                        and rerun_reason == "noisy_text"
                        and initial_conf >= 70
                        and ocr_meta.get("ocr_engine_used") == "tesseract"
                    ):
                        quick_attempted = True
                        quick_settings = {**page_settings, "psm": 11, "alt_psm": [], "single_pass": True}
                        quick_text, _, quick_failure, quick_meta = self._ocr_image(
                            page, quick_settings, engine_name=str(engine)
                        )
                        candidate_count += int(quick_meta.get("ocr_candidate_count") or 0)
                        quick_conf = self._safe_confidence(quick_meta.get("ocr_confidence"))
                        quick_score = self._score_ocr_candidate(quick_text, quick_conf) if quick_text else -1.0
                        if quick_failure == "ocr_timeout":
                            page_failure = quick_failure
                            retry_path = "quick_psm11_timeout"
                        if (
                            quick_text
                            and not quick_failure
                            and self._ocr_noise_ratio(quick_text) < _OCR_NOISE_RETRY_THRESHOLD
                            and quick_score >= current_score - rerun_min_gain
                        ):
                            ocr_text = quick_text
                            ocr_meta = dict(quick_meta)
                            quick_accepted = True
                            rerun_used = True
                            retry_path = "quick_psm11"
                    if not quick_accepted and page_failure != "ocr_timeout":
                        retry_settings = self._build_retry_settings(page_settings, ctx)
                        retry_text, _, retry_failure, retry_meta = self._ocr_image(
                            page, retry_settings, engine_name=str(engine)
                        )
                        candidate_count += int(retry_meta.get("ocr_candidate_count") or 0)
                        retry_conf = self._safe_confidence(retry_meta.get("ocr_confidence"))
                        retry_score = self._score_ocr_candidate(retry_text, retry_conf) if retry_text else -1.0
                        if retry_failure == "ocr_timeout":
                            page_failure = retry_failure
                        valid_retries = []
                        if quick_text and not quick_failure:
                            valid_retries.append((quick_score, quick_text, quick_meta))
                        if retry_text and not retry_failure:
                            valid_retries.append((retry_score, retry_text, retry_meta))
                        best_retry = max(valid_retries, key=lambda item: item[0]) if valid_retries else None
                        if best_retry and best_retry[0] > current_score + rerun_min_gain:
                            _, ocr_text, selected_meta = best_retry
                            ocr_meta = dict(selected_meta)
                            if retry_failure != "ocr_timeout":
                                page_failure = None
                            rerun_used = True
                        retry_path = "quick_then_full_bounded" if quick_attempted else "full_bounded"
                    if rerun_used:
                        rerun_used_pages += 1
                    ocr_meta["ocr_rerun_reason"] = rerun_reason
                    ocr_meta["ocr_noise_ratio"] = initial_noise_ratio
                    ocr_meta["ocr_rerun_attempted"] = True
                    ocr_meta["ocr_rerun_used"] = rerun_used
                else:
                    ocr_meta["ocr_rerun_reason"] = rerun_reason
                    ocr_meta["ocr_noise_ratio"] = initial_noise_ratio
                    ocr_meta["ocr_rerun_attempted"] = False
                    ocr_meta["ocr_rerun_used"] = False
                ocr_meta["ocr_retry_path"] = retry_path
                ocr_meta["ocr_candidate_count_total"] = candidate_count
                ocr_meta["ocr_failure_reason"] = page_failure
                if page_failure and failure_reason is None:
                    failure_reason = page_failure
                if not ocr_text:
                    # Fall back to raw text but normalize it
                    fallback = normalize_text(raw)
                    # If text is garbled (bad PDF CMap), try degarbling
                    if is_garbled_page:
                        ocr_text = degarble(fallback)
                    else:
                        ocr_text = fallback
                elif is_garbled_page and is_garbled(ocr_text):
                    # OCR returned text but it's still garbled — degarble it
                    ocr_text = degarble(ocr_text)
            else:
                native_text = normalize_text(raw)
                if native_text and self._looks_like_native_text(native_text):
                    ocr_meta = {
                        "ocr_lang": lang,
                        "ocr_psm": psm,
                        "ocr_oem": oem,
                        "ocr_variant": "native_text_no_image",
                        "ocr_confidence": 99.0,
                        "ocr_engine_used": "native_text",
                    }
                    ocr_text = native_text
                else:
                    ocr_meta = {
                        "ocr_lang": lang,
                        "ocr_psm": psm,
                        "ocr_oem": oem,
                        "ocr_variant": "mock",
                        "ocr_engine_used": "mock",
                    }
                    ocr_text = mock_ocr(raw, passes=passes)
            cleaned_pages.append(
                Page(
                    number=page.number,
                    text=ocr_text,
                    raw_text=raw,
                    image_path=page.image_path,
                    metadata={
                        **page.metadata,
                        "ocr_engine": engine,
                        "ocr_passes": passes,
                        "ocr_lang": lang,
                        "ocr_psm": ocr_meta.get("ocr_psm", psm),
                        "ocr_oem": ocr_meta.get("ocr_oem", oem),
                        "ocr_variant": ocr_meta.get("ocr_variant", "unknown"),
                        "ocr_confidence": ocr_meta.get("ocr_confidence"),
                        "ocr_rotation_applied": ocr_meta.get("ocr_rotation_applied", 0),
                        "ocr_rerun_attempted": ocr_meta.get("ocr_rerun_attempted", False),
                        "ocr_rerun_used": ocr_meta.get("ocr_rerun_used", False),
                        "ocr_rerun_reason": ocr_meta.get("ocr_rerun_reason"),
                        "ocr_retry_path": ocr_meta.get("ocr_retry_path"),
                        "ocr_candidate_count": ocr_meta.get(
                            "ocr_candidate_count_total", ocr_meta.get("ocr_candidate_count", 0)
                        ),
                        "ocr_noise_ratio": ocr_meta.get("ocr_noise_ratio"),
                        "ocr_dpi": dpi,
                        "ocr_engine_used": ocr_meta.get("ocr_engine_used", engine),
                        "ocr_failure_reason": ocr_meta.get("ocr_failure_reason"),
                    },
                )
            )
        doc.pages = cleaned_pages
        input_artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_ocr_input.txt",
            "\n".join(page.raw_text or page.text for page in doc.pages),
            kind="ocr_input",
            raw=True,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {
                    "engine": engine,
                    "passes": passes,
                    "lang": lang,
                    "psm": psm,
                    "oem": oem,
                    "dpi": dpi,
                    "alt_psm": alt_psm_list,
                },
                "source_artifacts": [input_artifact_id] if input_artifact_id else [],
            },
        )
        artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_ocr.txt",
            "\n".join(page.text for page in doc.pages),
            kind="ocr_text",
            raw=False,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {
                    "engine": engine,
                    "passes": passes,
                    "lang": lang,
                    "psm": psm,
                    "oem": oem,
                    "dpi": dpi,
                    "alt_psm": alt_psm_list,
                },
                "source_artifacts": [input_artifact.artifact_id],
            },
        )
        ocr_text = "\n".join(page.text for page in doc.pages)
        alpha_ratio = sum(1 for ch in ocr_text if ch.isalnum()) / max(len(ocr_text), 1)
        ocr_conf_values: list[float] = []
        for page in doc.pages:
            raw_conf = page.metadata.get("ocr_confidence")
            if raw_conf is None:
                continue
            try:
                ocr_conf_values.append(float(raw_conf))
            except Exception:
                continue
        avg_ocr_conf = sum(ocr_conf_values) / len(ocr_conf_values) if ocr_conf_values else 0.0
        confidence = 0.4 + 0.5 * alpha_ratio
        if avg_ocr_conf > 0:
            confidence = max(confidence, min(avg_ocr_conf / 100.0, 0.95))
        signal = StageSignal(
            stage=self.name,
            confidence=min(confidence, 0.95) if not failure_reason else 0.35,
            uncertainty=max(0.0, 1.0 - confidence) if not failure_reason else 0.65,
            failure_reason=failure_reason,
            metadata={
                "image_ocr": used_image_ocr,
                "engine": engine,
                "passes": passes,
                "lang": lang,
                "psm": psm,
                "oem": oem,
                "dpi": dpi,
                "alt_psm": alt_psm_list,
                "avg_ocr_confidence": avg_ocr_conf,
                "rerun_attempted_pages": rerun_attempted_pages,
                "rerun_used_pages": rerun_used_pages,
                "rerun_min_score_gain": rerun_min_gain,
            },
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"pages": len(doc.pages), "artifact_id": artifact.artifact_id},
            parameters={
                "engine": engine,
                "passes": passes,
                "lang": lang,
                "psm": psm,
                "oem": oem,
                "dpi": dpi,
                "alt_psm": alt_psm_list,
            },
            artifacts=[input_artifact.artifact_id, artifact.artifact_id],
            input_artifacts=[input_artifact_id] if input_artifact_id else [],
            output_artifacts=[artifact.artifact_id],
            started=started,
            cost_units=1.0,
        )
        return AgentResult(artifacts={"document": doc, "artifact_id": artifact.artifact_id, "signal": signal})

    def _ocr_image(
        self,
        page: Page,
        settings: dict[str, object],
        engine_name: str = "paddle",
    ) -> tuple[str, bool, str | None, dict[str, object]]:
        path = page.image_path or ""
        try:
            from PIL import Image, ImageFilter, ImageOps, ImageSequence
        except Exception:
            return "", False, "pillow_not_available", {}
        lang = str(settings.get("lang") or "eng")
        psm = int(settings.get("psm") or 6)
        oem = int(settings.get("oem") or 3)
        alt_psm = settings.get("alt_psm") or []
        single_pass = bool(settings.get("single_pass", False))
        max_candidates = settings.get("max_candidates")
        budget = settings.get("tesseract_budget")
        if budget is not None and not isinstance(budget, _TesseractBudget):
            raise TypeError("tesseract_budget must be a _TesseractBudget")
        dpi = int(settings.get("dpi") or 300)
        requested_engine = (engine_name or "").strip().lower()
        if requested_engine in {"paddle", "paddleocr"}:
            paddle_text, paddle_used, paddle_failure, paddle_meta = self._ocr_image_paddle(path, lang)
            if paddle_used and paddle_text:
                paddle_meta.setdefault("ocr_psm", psm)
                paddle_meta.setdefault("ocr_oem", oem)
                paddle_meta.setdefault("ocr_rotation_applied", 0)
                paddle_meta["ocr_engine_used"] = "paddleocr"
                return paddle_text.strip(), True, None, paddle_meta
            # Fallback to Tesseract path below if PaddleOCR is unavailable or fails.
            if paddle_meta:
                paddle_meta["ocr_engine_used"] = "tesseract_fallback"
        try:
            import pytesseract
        except Exception:
            return "", False, "tesseract_not_available", {}
        tessdata_dir = self._configure_tesseract(pytesseract)

        try:
            if path.lower().endswith(".pdf"):
                text, failure, meta = self._ocr_pdf_page(
                    path,
                    page,
                    pytesseract,
                    Image,
                    ImageSequence,
                    tessdata_dir,
                    lang,
                    psm,
                    oem,
                    alt_psm,
                    dpi,
                    single_pass,
                    max_candidates,
                    budget,
                )
                if failure:
                    return text.strip(), True, failure, meta
                meta["ocr_engine_used"] = "tesseract"
                return text.strip(), True, None, meta
            with Image.open(path) as img:
                cleaned = self._normalize_image(img, Image, ImageOps, ImageFilter)
                cleaned, rotation = (
                    self._apply_orientation_correction(cleaned, pytesseract, lang, budget)
                    if budget else self._apply_orientation_correction(cleaned, pytesseract, lang)
                )
                text, meta = self._run_ocr_variants(
                    cleaned,
                    pytesseract,
                    tessdata_dir,
                    lang,
                    psm,
                    oem,
                    alt_psm,
                    ImageOps,
                    ImageFilter,
                    single_pass=single_pass,
                    max_candidates=max_candidates,
                    **({"budget": budget} if budget else {}),
                )
                meta["ocr_rotation_applied"] = rotation
                meta["ocr_engine_used"] = "tesseract"
            return text.strip(), True, "ocr_timeout" if meta.get("ocr_timeout") else None, meta
        except _TesseractTimeout:
            return "", True, "ocr_timeout", {"ocr_engine_used": "tesseract"}
        except Exception as exc:
            message = str(exc)
            if "TESSDATA_PREFIX" in message or "tessdata" in message:
                return "", True, "tessdata_missing", {}
            return "", True, "ocr_failed", {}

    def _preprocess_for_paddle(self, path: str) -> str:
        """Enhance image quality before PaddleOCR — upscale, contrast stretch, sharpen.

        Returns path to a temp enhanced image, or original path if preprocessing fails.
        Degraded fax/scan images benefit significantly from this before OCR.
        """
        try:
            from PIL import Image, ImageFilter, ImageOps
        except Exception:
            return path
        try:
            img = Image.open(path)
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            # Upscale small images — PaddleOCR text detection struggles below ~150 DPI
            w, h = img.size
            if max(w, h) < 1600:
                scale = 1600 / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            # Grayscale + autocontrast to normalise fax scan brightness range
            gray = ImageOps.grayscale(img)
            gray = ImageOps.autocontrast(gray, cutoff=2)
            # Mild sharpening to recover edges lost in fax compression
            gray = gray.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=2))
            # Save to temp file
            tmp_path = path + "_paddle_enhanced.png"
            gray.save(tmp_path, format="PNG")
            return tmp_path
        except Exception:
            return path

    def _ocr_image_paddle(self, path: str, lang: str) -> tuple[str, bool, str | None, dict[str, object]]:
        try:
            from paddleocr import PaddleOCR
        except Exception:
            return "", False, "paddleocr_not_available", {}

        model_lang = self._paddle_lang(lang)
        enhanced_path = self._preprocess_for_paddle(path)
        try:
            with _PADDLE_LOCK:
                result = _paddle_engine(PaddleOCR, model_lang).ocr(enhanced_path, cls=True)
        except Exception as exc:
            return "", True, f"paddleocr_failed:{str(exc)[:80]}", {"ocr_variant": "paddle"}
        finally:
            # Clean up temp enhanced image
            if enhanced_path != path:
                try:
                    import os as _os
                    _os.remove(enhanced_path)
                except Exception:
                    pass

        text, confidence = self._extract_paddle_text(result)
        if not text:
            return "", True, "paddleocr_empty", {"ocr_variant": "paddle", "ocr_confidence": confidence}
        return (
            self._postprocess_ocr(text),
            True,
            None,
            {
                "ocr_variant": "paddle",
                "ocr_confidence": confidence,
                "ocr_lang": model_lang,
                "ocr_enhanced": enhanced_path != path,
            },
        )

    def _extract_paddle_text(self, result: object) -> tuple[str, float]:
        lines: list[str] = []
        confs: list[float] = []
        if not isinstance(result, list):
            return "", 0.0

        for page in result:
            if not isinstance(page, list):
                continue
            boxes: list[tuple[tuple[float, float, float] | None, str]] = []
            for item in page:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                payload = item[1]
                if not isinstance(payload, (list, tuple)) or not payload:
                    continue
                text = str(payload[0] or "").strip()
                if not text:
                    continue
                boxes.append((_box_extent(item[0]), text))
                if len(payload) > 1:
                    try:
                        confs.append(float(payload[1]) * 100.0)
                    except Exception:
                        continue
            lines.extend(_join_boxes_into_rows(boxes))

        avg_conf = sum(confs) / len(confs) if confs else 0.0
        return "\n".join(lines), avg_conf

    def _paddle_lang(self, lang: str) -> str:
        normalized = (lang or "eng").strip().lower()
        if normalized in {"eng", "en"}:
            return "en"
        return normalized or "en"

    def _ocr_pdf_page(
        self,
        path: str,
        page: Page,
        pytesseract,
        Image,
        ImageSequence,
        tessdata_dir: Path | None,
        lang: str,
        psm: int,
        oem: int,
        alt_psm: list[int],
        dpi: int,
        single_pass: bool = False,
        max_candidates: int | None = None,
        budget: _TesseractBudget | None = None,
    ) -> tuple[str, str | None, dict[str, object]]:
        page_index = page.metadata.get("pdf_page_index", 0)
        try:
            from pdf2image import convert_from_path
            poppler_path = self._find_poppler_path()
            images = convert_from_path(
                path,
                first_page=page_index + 1,
                last_page=page_index + 1,
                poppler_path=poppler_path,
                dpi=dpi,
            )
            if images:
                from PIL import ImageFilter, ImageOps

                cleaned = self._normalize_image(images[0], Image, ImageOps, ImageFilter)
                cleaned, rotation = (
                    self._apply_orientation_correction(cleaned, pytesseract, lang, budget)
                    if budget else self._apply_orientation_correction(cleaned, pytesseract, lang)
                )
                text, meta = self._run_ocr_variants(
                    cleaned,
                    pytesseract,
                    tessdata_dir,
                    lang,
                    psm,
                    oem,
                    alt_psm,
                    ImageOps,
                    ImageFilter,
                    single_pass=single_pass,
                    max_candidates=max_candidates,
                    **({"budget": budget} if budget else {}),
                )
                meta["ocr_rotation_applied"] = rotation
                return text, "ocr_timeout" if meta.get("ocr_timeout") else None, meta
        except _TesseractTimeout:
            raise
        except Exception:
            pass

        try:
            texts = []
            with Image.open(path) as doc:
                for idx, frame in enumerate(ImageSequence.Iterator(doc)):
                    if idx == page_index:
                        from PIL import ImageFilter, ImageOps

                        cleaned = self._normalize_image(frame, Image, ImageOps, ImageFilter)
                        cleaned, rotation = (
                            self._apply_orientation_correction(cleaned, pytesseract, lang, budget)
                            if budget else self._apply_orientation_correction(cleaned, pytesseract, lang)
                        )
                        text, meta = self._run_ocr_variants(
                            cleaned,
                            pytesseract,
                            tessdata_dir,
                            lang,
                            psm,
                            oem,
                            alt_psm,
                            ImageOps,
                            ImageFilter,
                            single_pass=single_pass,
                            max_candidates=max_candidates,
                            **({"budget": budget} if budget else {}),
                        )
                        meta["ocr_rotation_applied"] = rotation
                        texts.append(text)
                        break
            if texts:
                return "\n".join(texts), "ocr_timeout" if meta.get("ocr_timeout") else None, meta
        except _TesseractTimeout:
            raise
        except Exception:
            return "", "pdf_render_failed", {}
        return "", "pdf_render_failed", {}

    def _find_poppler_path(self) -> str | None:
        if self._poppler_searched:
            return self._cached_poppler_path
        self._cached_poppler_path = find_poppler_path()
        self._poppler_searched = True
        return self._cached_poppler_path

    def _configure_tesseract(self, pytesseract) -> Path | None:
        if self._tessdata_configured:
            return self._cached_tessdata_dir
        tess_cmd = find_tesseract_cmd()
        if tess_cmd:
            pytesseract.pytesseract.tesseract_cmd = tess_cmd
            tessdata_dir = Path(tess_cmd).parent / "tessdata"
            if tessdata_dir.exists():
                self._cached_tessdata_dir = Path(self._short_path(str(tessdata_dir)))
                self._tessdata_configured = True
                return self._cached_tessdata_dir
        self._tessdata_configured = True
        return None

    def _tessdata_config(self, tessdata_dir: Path | None, psm: int, oem: int) -> str:
        parts = [f"--oem {oem}", f"--psm {psm}"]
        env_dir = os.environ.get("TESSDATA_PREFIX")
        if env_dir and Path(env_dir).is_dir():
            short_path = self._short_path(env_dir)
            parts.append(f"--tessdata-dir {short_path}")
        elif tessdata_dir and tessdata_dir.is_dir():
            short_path = self._short_path(str(tessdata_dir))
            parts.append(f"--tessdata-dir {short_path}")
        return " ".join(parts)

    def _normalize_alt_psm(self, alt_psm: object, passes: int) -> list[int]:
        if alt_psm is None:
            return []
        if isinstance(alt_psm, int):
            return [alt_psm] if passes > 1 else []
        if isinstance(alt_psm, list):
            if passes <= 1:
                return []
            normalized = []
            for item in alt_psm:
                try:
                    normalized.append(int(item))
                except Exception:
                    continue
            return normalized
        return []

    def _safe_confidence(self, value: object) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def _build_retry_settings(self, settings: dict[str, object], ctx: AgentContext) -> dict[str, object]:
        psm = int(settings.get("psm") or ctx.config.preprocessing.ocr_psm)
        retry_settings = dict(settings)
        retry_settings["dpi"] = max(
            int(settings.get("dpi") or ctx.config.preprocessing.ocr_dpi),
            int(ctx.config.preprocessing.ocr_retry_dpi),
        )
        retry_psm = [psm] + list(ctx.config.preprocessing.ocr_retry_alt_psm or [])
        retry_settings["alt_psm"] = self._normalize_alt_psm(retry_psm, passes=2)
        retry_settings["single_pass"] = False
        retry_settings["max_candidates"] = ctx.config.preprocessing.ocr_retry_max_candidates
        return retry_settings

    def _normalize_image(self, img, Image, ImageOps, ImageFilter):
        try:
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            base = ImageOps.autocontrast(img)
            gray = ImageOps.grayscale(base)
            if max(gray.size) < 1400:
                gray = gray.resize((gray.size[0] * 2, gray.size[1] * 2), Image.BICUBIC)
            sharp = gray.filter(ImageFilter.SHARPEN)
            return sharp
        except Exception:
            return img

    def _run_ocr_variants(
        self,
        img,
        pytesseract,
        tessdata_dir: Path | None,
        lang: str,
        psm: int,
        oem: int,
        alt_psm: list[int],
        ImageOps,
        ImageFilter,
        *,
        single_pass: bool = False,
        max_candidates: int | None = None,
        budget: _TesseractBudget | None = None,
    ) -> tuple[str, dict[str, object]]:
        variants = [("base", img)]
        # Product auto starts with one variant; the quality-triggered retry uses the full search.
        if not single_pass and alt_psm:
            try:
                variants.append(("invert", ImageOps.invert(img.convert("RGB")).convert("L")))
            except Exception:
                pass
        # Thresholding and median smoothing improve OCR on noisy scans.
        if not single_pass:
            try:
                binary = img.convert("L").point(lambda px: 255 if px > 170 else 0, mode="1").convert("L")
                variants.append(("binary", binary))
            except Exception:
                pass
            try:
                median = img.convert("L").filter(ImageFilter.MedianFilter(size=3))
                variants.append(("median", median))
            except Exception:
                pass
        psm_values = [psm] if single_pass else [psm] + [value for value in alt_psm if value != psm]
        candidates = [
            (variant_name, variant_img, psm_value)
            for variant_name, variant_img in variants
            for psm_value in psm_values
        ]
        if max_candidates is not None:
            limit = int(max_candidates)
            if limit < 1:
                raise ValueError("max_candidates must be positive")
            candidate_map = {(name, value): (name, image, value) for name, image, value in candidates}
            priority = [
                ("base", psm), ("base", 11), ("base", 3), ("base", 12),
                ("median", 4), ("binary", psm), ("invert", 11), ("median", psm),
            ]
            order = dict.fromkeys([*priority, *candidate_map])
            candidates = [candidate_map[key] for key in order if key in candidate_map][:limit]
        best_text = ""
        best_score = -1.0
        best_meta = {"ocr_psm": psm, "ocr_oem": oem, "ocr_variant": "base", "ocr_confidence": 0.0}
        attempted = 0
        for attempts, (variant_name, variant_img, psm_value) in enumerate(candidates, start=1):
            attempted = attempts
            config = self._tessdata_config(tessdata_dir, psm_value, oem)
            try:
                text, ocr_confidence = (
                    self._extract_with_confidence(pytesseract, variant_img, lang, config, budget=budget)
                    if budget else self._extract_with_confidence(pytesseract, variant_img, lang, config)
                )
            except _TesseractTimeout as exc:
                if exc.partial_text:
                    partial_score = self._score_ocr_candidate(exc.partial_text, 0.0)
                    if partial_score > best_score:
                        best_text = exc.partial_text
                        best_score = partial_score
                        best_meta = {
                            "ocr_psm": psm_value,
                            "ocr_oem": oem,
                            "ocr_variant": variant_name,
                            "ocr_confidence": 0.0,
                        }
                best_meta["ocr_timeout"] = True
                break
            if not text:
                continue
            score = self._score_ocr_candidate(text, ocr_confidence)
            if score > best_score:
                best_score = score
                best_text = text
                best_meta = {
                    "ocr_psm": psm_value,
                    "ocr_oem": oem,
                    "ocr_variant": variant_name,
                    "ocr_confidence": ocr_confidence,
                }
                # Preserve the existing fast exit in the unbounded/default path.
                if best_score > 0.78 and ocr_confidence >= 70 and not alt_psm:
                    best_meta["ocr_candidate_count"] = attempts
                    return self._postprocess_ocr(best_text), best_meta
        best_meta["ocr_candidate_count"] = attempted
        return self._postprocess_ocr(best_text), best_meta

    def _extract_with_confidence(
        self, pytesseract, image, lang: str, config: str, *, budget: _TesseractBudget | None = None,
    ) -> tuple[str, float]:
        try:
            text = _call_tesseract(pytesseract.image_to_string, image, lang=lang, config=config, budget=budget)
        except _TesseractTimeout:
            raise
        except Exception:
            if budget is not None:
                raise
            return "", 0.0
        confidences: list[float] = []
        try:
            data = _call_tesseract(
                pytesseract.image_to_data, image, lang=lang, config=config,
                output_type=pytesseract.Output.DICT, budget=budget,
            )
            for value in data.get("conf", []):
                try:
                    score = float(value)
                except Exception:
                    continue
                if score >= 0:
                    confidences.append(score)
        except _TesseractTimeout as exc:
            raise _TesseractTimeout(partial_text=text) from exc
        except Exception:
            pass
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return text, avg_conf

    def _score_ocr_candidate(self, text: str, ocr_confidence: float) -> float:
        text_quality = self._score_text(text)
        conf_quality = max(0.0, min(ocr_confidence, 100.0)) / 100.0
        return (text_quality * 0.65) + (conf_quality * 0.35)

    def _ocr_rerun_reason(self, text: str, ocr_confidence: float, ctx: AgentContext) -> str | None:
        if ocr_confidence < float(ctx.config.preprocessing.ocr_min_confidence):
            return "low_confidence"
        if self._ocr_noise_ratio(text) >= _OCR_NOISE_RETRY_THRESHOLD:
            return "noisy_text"
        return None

    def _ocr_noise_ratio(self, text: str) -> float:
        if not text:
            return 1.0
        suspicious = 0
        tokens = text.split()
        for token in tokens:
            stripped = token.strip()
            if not stripped:
                continue
            alpha = sum(1 for ch in stripped if ch.isalpha())
            digit = sum(1 for ch in stripped if ch.isdigit())
            punct = sum(1 for ch in stripped if not ch.isalnum())
            if punct >= max(alpha + digit, 1):
                suspicious += 1
            elif len(stripped) >= 6 and alpha > 0 and digit > 0 and (alpha + digit) == len(stripped):
                suspicious += 1
            elif len(stripped) >= 8 and alpha >= 5 and punct >= 2:
                suspicious += 1
        total_tokens = max(len(tokens), 1)
        return min(suspicious / total_tokens, 1.0)

    def _apply_orientation_correction(
        self, img, pytesseract, lang: str, budget: _TesseractBudget | None = None,
    ) -> tuple[object, int]:
        rotation = self._detect_rotation_degrees(img, pytesseract, lang, budget)
        if rotation in {90, 180, 270}:
            try:
                return img.rotate(-rotation, expand=True), rotation
            except Exception:
                return img, 0
        return img, 0

    def _detect_rotation_degrees(
        self, img, pytesseract, lang: str, budget: _TesseractBudget | None = None,
    ) -> int:
        try:
            osd = _call_tesseract(
                pytesseract.image_to_osd, img, config=f"--psm 0 -l {lang}", budget=budget,
            )
        except _TesseractTimeout:
            raise
        except Exception:
            return 0
        match = re.search(r"Rotate:\s*(\d+)", osd or "")
        if not match:
            return 0
        try:
            value = int(match.group(1))
        except Exception:
            return 0
        return value if value in {90, 180, 270} else 0

    def _postprocess_ocr(self, text: str) -> str:
        """Clean common OCR artifacts from extracted text."""
        if not text:
            return text
        # Fix common character confusions
        cleaned = text
        cleaned = re.sub(r'\|([a-z])', r'l\1', cleaned)  # |k -> lk, |e -> le
        cleaned = re.sub(r'([a-z])\|', r'\1l', cleaned)  # a| -> al
        # Remove garbled sequences (5+ consecutive non-alphanumeric chars)
        cleaned = re.sub(r'[^\w\s.,;:!?()\-/]{5,}', '', cleaned)
        # Fix common OCR dash artifacts
        cleaned = re.sub(r'-{3,}_*', '', cleaned)  # -----_ -> empty
        cleaned = re.sub(r'_{3,}', '', cleaned)  # ____ -> empty  
        return cleaned

    def _score_text(self, text: str) -> float:
        if not text:
            return 0.0
        cleaned = text.strip()
        if not cleaned:
            return 0.0
        alpha_ratio = sum(1 for ch in cleaned if ch.isalnum()) / max(len(cleaned), 1)
        length_score = min(len(cleaned), 2000) / 2000
        return (alpha_ratio * 0.7) + (length_score * 0.3)

    def _looks_like_native_text(self, text: str) -> bool:
        cleaned = text.strip()
        if len(cleaned) < 25:
            return False
        alnum_ratio = sum(1 for ch in cleaned if ch.isalnum() or ch.isspace()) / max(len(cleaned), 1)
        word_count = len([w for w in cleaned.split() if w.strip()])
        return alnum_ratio >= 0.75 and word_count >= 4

    def _short_path(self, path: str) -> str:
        if os.name != "nt":
            return path
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(260)
            if ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 260):
                return buffer.value
        except Exception:
            pass
        return path

class DenoiseAgent(Agent):
    name = "denoise"
    version = "v1"
    input_contract = {"document": "Document", "input_artifact_id": "str|None"}
    output_contract = {"document": "Document", "artifact_id": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        input_artifact_id = payload.get("input_artifact_id")
        enabled = payload.get("enabled", True)
        if not enabled:
            signal = StageSignal(stage=self.name, confidence=0.5, uncertainty=0.5, metadata={"skipped": True})
            self._record(
                ctx,
                inputs={"doc_id": doc.doc_id},
                outputs={"skipped": True},
                parameters={"denoise": False},
                started=started,
            )
            return AgentResult(artifacts={"document": doc, "signal": signal})
        input_text = "\n".join(page.text for page in doc.pages)
        updated = []
        denoised_image_pages = 0
        for page in doc.pages:
            if doc.source == "scanned":
                page = rasterize_pdf_page(page, doc.doc_id, ctx, int(ctx.config.preprocessing.ocr_dpi))
            text = normalize_text(page.text)
            image_path = page.image_path
            metadata = dict(page.metadata or {})
            if image_path and Path(image_path).exists():
                processed_path = self._denoise_image(image_path, page.number, doc.doc_id, ctx)
                if processed_path:
                    image_path = processed_path
                    metadata["denoise_applied"] = True
                    denoised_image_pages += 1
            updated.append(
                Page(
                    number=page.number,
                    text=text,
                    raw_text=page.raw_text,
                    image_path=image_path,
                    metadata=metadata,
                )
            )
        doc.pages = updated
        input_artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_denoise_input.txt",
            input_text,
            kind="denoise_input",
            raw=True,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"denoise": True},
                "source_artifacts": [input_artifact_id] if input_artifact_id else [],
            },
        )
        artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_denoise.txt",
            "\n".join(page.text for page in doc.pages),
            kind="denoise_text",
            raw=False,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"denoise": True},
                "source_artifacts": [input_artifact.artifact_id],
            },
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.85 if denoised_image_pages else 0.75,
            uncertainty=0.15 if denoised_image_pages else 0.25,
            metadata={"denoised_image_pages": denoised_image_pages},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"pages": len(doc.pages), "artifact_id": artifact.artifact_id},
            parameters={"denoise": True},
            artifacts=[input_artifact.artifact_id, artifact.artifact_id],
            input_artifacts=[input_artifact_id] if input_artifact_id else [],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"document": doc, "artifact_id": artifact.artifact_id, "signal": signal})

    def _denoise_image(self, image_path: str, page_number: int, doc_id: str, ctx: AgentContext) -> str | None:
        try:
            from PIL import Image, ImageFilter, ImageOps
        except Exception:
            return None
        try:
            with Image.open(image_path) as img:
                gray = ImageOps.grayscale(img)
                # A 3px median erases 1-2px strokes on low-resolution scans, so filter at 2x instead.
                if min(gray.size) < _DENOISE_MIN_SHORT_SIDE_PX:
                    gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
                smooth = gray.filter(ImageFilter.MedianFilter(size=3))
                enhanced = ImageOps.autocontrast(smooth)
                return _save_processed_image(ctx, doc_id, page_number, "denoise", enhanced)
        except Exception:
            return None

class DeskewAgent(Agent):
    name = "deskew"
    version = "v1"
    input_contract = {"document": "Document", "input_artifact_id": "str|None"}
    output_contract = {"document": "Document", "artifact_id": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        input_artifact_id = payload.get("input_artifact_id")
        enabled = payload.get("enabled", True)
        if not enabled:
            signal = StageSignal(stage=self.name, confidence=0.5, uncertainty=0.5, metadata={"skipped": True})
            self._record(
                ctx,
                inputs={"doc_id": doc.doc_id},
                outputs={"skipped": True},
                parameters={"deskew": False},
                started=started,
            )
            return AgentResult(artifacts={"document": doc, "signal": signal})

        updated_pages: list[Page] = []
        deskewed_image_pages = 0
        for page in doc.pages:
            image_path = page.image_path
            metadata = dict(page.metadata or {})
            angle = self._resolve_skew_angle(page, doc)
            if image_path and Path(image_path).exists() and abs(angle) >= 0.3:
                processed_path = self._deskew_image(image_path, angle, page.number, doc.doc_id, ctx)
                if processed_path:
                    image_path = processed_path
                    metadata["deskew_applied"] = True
                    metadata["deskew_angle"] = angle
                    deskewed_image_pages += 1
            updated_pages.append(
                Page(
                    number=page.number,
                    text=page.text,
                    raw_text=page.raw_text,
                    image_path=image_path,
                    metadata=metadata,
                )
            )
        doc.pages = updated_pages

        input_artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_deskew_input.txt",
            "\n".join(page.text for page in doc.pages),
            kind="deskew_input",
            raw=True,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"deskew": True},
                "source_artifacts": [input_artifact_id] if input_artifact_id else [],
            },
        )
        artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_deskew.txt",
            "\n".join(page.text for page in doc.pages),
            kind="deskew_text",
            raw=False,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"deskew": True},
                "source_artifacts": [input_artifact.artifact_id],
            },
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.82 if deskewed_image_pages else 0.7,
            uncertainty=0.18 if deskewed_image_pages else 0.3,
            metadata={"deskewed_image_pages": deskewed_image_pages},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"artifact_id": artifact.artifact_id},
            parameters={"deskew": True},
            artifacts=[input_artifact.artifact_id, artifact.artifact_id],
            input_artifacts=[input_artifact_id] if input_artifact_id else [],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"document": doc, "artifact_id": artifact.artifact_id, "signal": signal})

    def _resolve_skew_angle(self, page: Page, doc: Document) -> float:
        candidates = [
            page.metadata.get("skew_angle"),
            doc.metadata.get("skew_angle"),
        ]
        for value in candidates:
            if value is None:
                continue
            try:
                return float(value)
            except Exception:
                continue
        return 0.0

    def _deskew_image(self, image_path: str, angle: float, page_number: int, doc_id: str, ctx: AgentContext) -> str | None:
        try:
            from PIL import Image
        except Exception:
            return None
        try:
            with Image.open(image_path) as img:
                rotated = img.rotate(-angle, expand=True, fillcolor="white")
                return _save_processed_image(ctx, doc_id, page_number, "deskew", rotated)
        except Exception:
            return None

class TableFormAgent(Agent):
    name = "table_form"
    version = "v1"
    input_contract = {"document": "Document", "input_artifact_id": "str|None"}
    output_contract = {"tables": "list", "artifact_id": "str", "signal": "StageSignal"}

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        input_artifact_id = payload.get("input_artifact_id")
        table_mode = payload.get("table_mode") or payload.get("type") or ctx.config.preprocessing.table_mode
        tables = []
        for page in doc.pages:
            rows = [line for line in page.text.splitlines() if "|" in line or "\t" in line]
            if rows:
                tables.append({"page": page.number, "rows": rows})
        input_artifact = ctx.artifact_store.save_text(
            f"{doc.doc_id}_tables_input.txt",
            "\n".join(page.text for page in doc.pages),
            kind="tables_input",
            raw=True,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"table_mode": table_mode},
                "source_artifacts": [input_artifact_id] if input_artifact_id else [],
            },
        )
        artifact = ctx.artifact_store.save_json(
            f"{doc.doc_id}_tables.json",
            {"tables": tables},
            kind="tables",
            raw=False,
            metadata={
                "doc_id": doc.doc_id,
                "agent": self.name,
                "version": self.version,
                "parameters": {"table_mode": table_mode},
                "source_artifacts": [input_artifact.artifact_id],
            },
        )
        signal = StageSignal(
            stage=self.name,
            confidence=0.7 if tables else 0.5,
            uncertainty=0.3 if tables else 0.5,
            metadata={"table_pages": len(tables)},
        )
        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id},
            outputs={"table_pages": len(tables), "artifact_id": artifact.artifact_id},
            parameters={"table_mode": table_mode},
            artifacts=[input_artifact.artifact_id, artifact.artifact_id],
            input_artifacts=[input_artifact_id] if input_artifact_id else [],
            output_artifacts=[artifact.artifact_id],
            started=started,
        )
        return AgentResult(artifacts={"tables": tables, "artifact_id": artifact.artifact_id, "signal": signal})

