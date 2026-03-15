"""Document preprocessing agents: OCR, deskew, denoise, and table/form detection."""

from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from pathlib import Path

from idpo.agents.base import Agent, AgentContext
from idpo.agents.degarble import degarble, is_garbled
from idpo.core.contracts import AgentMessage
from idpo.core.types import AgentResult, Document, Page, StageSignal

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
        settings = {
            "lang": lang,
            "psm": psm,
            "oem": oem,
            "dpi": dpi,
            "alt_psm": alt_psm_list,
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
                    ocr_text, page_used, page_failure, ocr_meta = self._ocr_image(page, settings, engine_name=str(engine))
                used_image_ocr = used_image_ocr or page_used
                initial_conf = self._safe_confidence(ocr_meta.get("ocr_confidence"))
                if (
                    page_used
                    and not page_failure
                    and ocr_text
                    and initial_conf < float(ctx.config.preprocessing.ocr_min_confidence)
                    and int(ctx.config.preprocessing.ocr_max_reruns_per_page) > 0
                ):
                    rerun_attempted_pages += 1
                    retry_settings = self._build_retry_settings(settings, ctx)
                    retry_text, _, retry_failure, retry_meta = self._ocr_image(
                        page, retry_settings, engine_name=str(engine)
                    )
                    retry_conf = self._safe_confidence(retry_meta.get("ocr_confidence"))
                    current_score = self._score_ocr_candidate(ocr_text, initial_conf)
                    retry_score = self._score_ocr_candidate(retry_text, retry_conf) if retry_text else -1.0
                    if retry_text and not retry_failure and retry_score > current_score + rerun_min_gain:
                        ocr_text = retry_text
                        ocr_meta = dict(retry_meta)
                        page_failure = None
                        rerun_used_pages += 1
                    ocr_meta["ocr_rerun_attempted"] = True
                    ocr_meta["ocr_rerun_used"] = bool(retry_text and retry_score > current_score + rerun_min_gain)
                else:
                    ocr_meta["ocr_rerun_attempted"] = False
                    ocr_meta["ocr_rerun_used"] = False
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
                        "ocr_dpi": dpi,
                        "ocr_engine_used": ocr_meta.get("ocr_engine_used", engine),
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
        engine_name: str = "tesseract",
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
                )
                if failure:
                    return "", True, failure, {}
                meta["ocr_engine_used"] = "tesseract"
                return text.strip(), True, None, meta
            with Image.open(path) as img:
                cleaned = self._normalize_image(img, Image, ImageOps, ImageFilter)
                cleaned, rotation = self._apply_orientation_correction(cleaned, pytesseract, lang)
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
                )
                meta["ocr_rotation_applied"] = rotation
                meta["ocr_engine_used"] = "tesseract"
            return text.strip(), True, None, meta
        except Exception as exc:
            message = str(exc)
            if "TESSDATA_PREFIX" in message or "tessdata" in message:
                return "", True, "tessdata_missing", {}
            return "", True, "ocr_failed", {}

    def _ocr_image_paddle(self, path: str, lang: str) -> tuple[str, bool, str | None, dict[str, object]]:
        try:
            from paddleocr import PaddleOCR
        except Exception:
            return "", False, "paddleocr_not_available", {}

        model_lang = self._paddle_lang(lang)
        try:
            ocr = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang=model_lang,
                show_log=False,
            )
            result = ocr.ocr(path)
        except Exception as exc:
            return "", True, f"paddleocr_failed:{str(exc)[:80]}", {"ocr_variant": "paddle"}

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
            for item in page:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                payload = item[1]
                if not isinstance(payload, (list, tuple)) or not payload:
                    continue
                text = str(payload[0] or "").strip()
                if not text:
                    continue
                lines.append(text)
                if len(payload) > 1:
                    try:
                        confs.append(float(payload[1]) * 100.0)
                    except Exception:
                        continue

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
                cleaned, rotation = self._apply_orientation_correction(cleaned, pytesseract, lang)
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
                )
                meta["ocr_rotation_applied"] = rotation
                return text, None, meta
        except Exception:
            pass

        try:
            texts = []
            with Image.open(path) as doc:
                for idx, frame in enumerate(ImageSequence.Iterator(doc)):
                    if idx == page_index:
                        from PIL import ImageFilter, ImageOps

                        cleaned = self._normalize_image(frame, Image, ImageOps, ImageFilter)
                        cleaned, rotation = self._apply_orientation_correction(cleaned, pytesseract, lang)
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
                        )
                        meta["ocr_rotation_applied"] = rotation
                        texts.append(text)
                        break
            if texts:
                return "\n".join(texts), None, meta
        except Exception:
            return "", "pdf_render_failed", {}
        return "", "pdf_render_failed", {}

    def _find_poppler_path(self) -> str | None:
        if self._poppler_searched:
            return self._cached_poppler_path
        env_path = os.environ.get("POPPLER_PATH")
        if env_path and Path(env_path).exists():
            self._cached_poppler_path = env_path
            self._poppler_searched = True
            return env_path
        which_path = shutil.which("pdftoppm")
        if which_path:
            self._cached_poppler_path = str(Path(which_path).parent)
            self._poppler_searched = True
            return self._cached_poppler_path

        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        base = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        if not base.exists():
            return None
        candidates = base.glob("*Poppler*")
        for candidate in candidates:
            for bin_path in [candidate / "Library" / "bin", candidate / "bin"]:
                exe_path = bin_path / "pdftoppm.exe"
                if exe_path.exists():
                    self._cached_poppler_path = str(bin_path)
                    self._poppler_searched = True
                    return self._cached_poppler_path
        self._poppler_searched = True
        return None

    def _configure_tesseract(self, pytesseract) -> Path | None:
        if self._tessdata_configured:
            return self._cached_tessdata_dir
        tess_cmd = shutil.which("tesseract")
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
        if env_dir:
            short_path = self._short_path(env_dir)
            parts.append(f"--tessdata-dir {short_path}")
        elif tessdata_dir and tessdata_dir.exists():
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
    ) -> tuple[str, dict[str, object]]:
        variants = [("base", img)]
        # Only add inverted variant if we have alt_psm (i.e. multi-pass mode)
        if alt_psm:
            try:
                variants.append(("invert", ImageOps.invert(img.convert("RGB")).convert("L")))
            except Exception:
                pass
        # Thresholding and median smoothing improve OCR on noisy scans.
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
        psm_values = [psm] + [value for value in alt_psm if value != psm]
        best_text = ""
        best_score = -1.0
        best_meta = {"ocr_psm": psm, "ocr_oem": oem, "ocr_variant": "base", "ocr_confidence": 0.0}
        for variant_name, variant_img in variants:
            for psm_value in psm_values:
                config = self._tessdata_config(tessdata_dir, psm_value, oem)
                text, ocr_confidence = self._extract_with_confidence(
                    pytesseract,
                    variant_img,
                    lang,
                    config,
                )
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
                    # Early exit: if first variant scores well, skip rest
                    if best_score > 0.78 and ocr_confidence >= 70 and not alt_psm:
                        return self._postprocess_ocr(best_text), best_meta
        return self._postprocess_ocr(best_text), best_meta

    def _extract_with_confidence(self, pytesseract, image, lang: str, config: str) -> tuple[str, float]:
        try:
            text = pytesseract.image_to_string(image, lang=lang, config=config)
        except Exception:
            return "", 0.0
        confidences: list[float] = []
        try:
            data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
            for value in data.get("conf", []):
                try:
                    score = float(value)
                except Exception:
                    continue
                if score >= 0:
                    confidences.append(score)
        except Exception:
            pass
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return text, avg_conf

    def _score_ocr_candidate(self, text: str, ocr_confidence: float) -> float:
        text_quality = self._score_text(text)
        conf_quality = max(0.0, min(ocr_confidence, 100.0)) / 100.0
        return (text_quality * 0.65) + (conf_quality * 0.35)

    def _apply_orientation_correction(self, img, pytesseract, lang: str) -> tuple[object, int]:
        rotation = self._detect_rotation_degrees(img, pytesseract, lang)
        if rotation in {90, 180, 270}:
            try:
                return img.rotate(-rotation, expand=True), rotation
            except Exception:
                return img, 0
        return img, 0

    def _detect_rotation_degrees(self, img, pytesseract, lang: str) -> int:
        try:
            osd = pytesseract.image_to_osd(
                img,
                config=f"--psm 0 -l {lang}",
            )
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

class PreprocessingRouter(Agent):
    name = "preprocess_router"
    version = "v1"
    input_contract = {"document": "Document", "analysis": "dict", "input_artifact_id": "str|None", "policy": "ExtractionPolicy|None"}
    output_contract = {
        "document": "Document",
        "artifacts": "list",
        "route": "list",
        "signals": "list",
    }

    def __init__(self) -> None:
        self.ocr = OcrAgent()
        self.denoise = DenoiseAgent()
        self.deskew = DeskewAgent()
        self.table_form = TableFormAgent()

    def run(self, payload: AgentMessage, ctx: AgentContext) -> AgentResult:
        started = time.time()
        doc: Document = payload["document"]
        analysis = payload.get("analysis", {})
        input_artifact_id = payload.get("input_artifact_id")
        policy = payload.get("policy")
        result = AgentResult(artifacts={"document": doc})
        route = self._route(doc, analysis, ctx, policy)
        artifacts = []
        signals = []
        current_artifact_id = input_artifact_id
        if "ocr" in route:
            ocr_result = self.ocr.run({"document": doc, "input_artifact_id": current_artifact_id}, ctx)
            result = result.merge(ocr_result)
            current_artifact_id = ocr_result.artifacts.get("artifact_id")
            artifacts.append(current_artifact_id)
            signals.append(ocr_result.artifacts.get("signal"))
        if "deskew" in route:
            deskew_result = self.deskew.run({"document": doc, "input_artifact_id": current_artifact_id}, ctx)
            result = result.merge(deskew_result)
            current_artifact_id = deskew_result.artifacts.get("artifact_id")
            artifacts.append(current_artifact_id)
            signals.append(deskew_result.artifacts.get("signal"))
        if "denoise" in route:
            denoise_result = self.denoise.run({"document": doc, "input_artifact_id": current_artifact_id}, ctx)
            result = result.merge(denoise_result)
            current_artifact_id = denoise_result.artifacts.get("artifact_id")
            artifacts.append(current_artifact_id)
            signals.append(denoise_result.artifacts.get("signal"))
        if "table_form" in route:
            table_result = self.table_form.run({"document": doc, "input_artifact_id": current_artifact_id}, ctx)
            result = result.merge(table_result)
            artifacts.append(table_result.artifacts.get("artifact_id"))
            signals.append(table_result.artifacts.get("signal"))

        self._record(
            ctx,
            inputs={"doc_id": doc.doc_id, "profile": doc.profile},
            outputs={"route": route, "artifact_count": len(artifacts)},
            parameters={
                "quality_score": analysis.get("quality_score", doc.quality_score),
                "complexity": analysis.get("complexity_score", doc.complexity_score),
            },
            started=started,
        )
        result.artifacts["route"] = route
        result.artifacts["signals"] = [signal for signal in signals if signal]
        result.artifacts["artifact_ids"] = [art for art in artifacts if art]
        return result

    def _route(self, doc: Document, analysis: dict[str, float], ctx: AgentContext, policy) -> list[str]:
        route = []
        if doc.source in {"scanned", "synthetic"}:
            route.append("ocr")
        quality = analysis.get("quality_score", doc.quality_score or 0.0)
        complexity = analysis.get("complexity_score", doc.complexity_score or 0.0)
        if doc.profile in {"image-heavy", "table-heavy"} or quality < ctx.config.routing.quality_threshold:
            route.append("deskew")
            route.append("denoise")
        if doc.profile in {"table-heavy", "form-centric"} or complexity > ctx.config.routing.complexity_threshold:
            route.append("table_form")
        if doc.profile not in {"image-heavy"} and "denoise" not in route:
            route.append("denoise")
        route = self._apply_policy(route, policy)
        return self._order_route(route)

    def _apply_policy(self, route: list[str], policy) -> list[str]:
        if not policy:
            return route
        updated = [step for step in route if step not in policy.preprocess_skip]
        for step in policy.preprocess_force:
            if step not in updated:
                updated.append(step)
        return updated

    def _order_route(self, route: list[str]) -> list[str]:
        ordered = []
        for step in ["deskew", "denoise", "ocr", "table_form"]:
            if step in route:
                ordered.append(step)
        return ordered
