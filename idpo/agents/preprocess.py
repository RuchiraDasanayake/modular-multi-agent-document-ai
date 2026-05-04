"""Document preprocessing agents: OCR, deskew, denoise, and table/form detection."""

from __future__ import annotations

import os
import re
import shutil
import time
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
        for page in doc.pages:
            raw = page.raw_text or page.text
            page_failure = None
            is_garbled_page = page.metadata.get("garbled_pdf", False) or is_garbled(raw)
            if page.image_path:
                ocr_text, page_used, page_failure, ocr_meta = self._ocr_image(page, settings)
                used_image_ocr = used_image_ocr or page_used
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
                ocr_meta = {"ocr_lang": lang, "ocr_psm": psm, "ocr_oem": oem, "ocr_variant": "mock"}
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
                        "ocr_dpi": dpi,
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
        confidence = 0.4 + 0.5 * alpha_ratio
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

    def _ocr_image(self, page: Page, settings: dict[str, object]) -> tuple[str, bool, str | None, dict[str, object]]:
        path = page.image_path or ""
        try:
            from PIL import Image, ImageFilter, ImageOps, ImageSequence
        except Exception:
            return "", False, "pillow_not_available", {}
        try:
            import pytesseract
        except Exception:
            return "", False, "tesseract_not_available", {}
        tessdata_dir = self._configure_tesseract(pytesseract)
        lang = str(settings.get("lang") or "eng")
        psm = int(settings.get("psm") or 6)
        oem = int(settings.get("oem") or 3)
        alt_psm = settings.get("alt_psm") or []
        dpi = int(settings.get("dpi") or 300)

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
                return text.strip(), True, None, meta
            with Image.open(path) as img:
                cleaned = self._normalize_image(img, Image, ImageOps, ImageFilter)
                text, meta = self._run_ocr_variants(
                    cleaned,
                    pytesseract,
                    tessdata_dir,
                    lang,
                    psm,
                    oem,
                    alt_psm,
                    ImageOps,
                )
            return text.strip(), True, None, meta
        except Exception as exc:
            message = str(exc)
            if "TESSDATA_PREFIX" in message or "tessdata" in message:
                return "", True, "tessdata_missing", {}
            return "", True, "ocr_failed", {}

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
                text, meta = self._run_ocr_variants(
                    cleaned,
                    pytesseract,
                    tessdata_dir,
                    lang,
                    psm,
                    oem,
                    alt_psm,
                    ImageOps,
                )
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
                        text, meta = self._run_ocr_variants(
                            cleaned,
                            pytesseract,
                            tessdata_dir,
                            lang,
                            psm,
                            oem,
                            alt_psm,
                            ImageOps,
                        )
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
    ) -> tuple[str, dict[str, object]]:
        variants = [("base", img)]
        # Only add inverted variant if we have alt_psm (i.e. multi-pass mode)
        if alt_psm:
            try:
                variants.append(("invert", ImageOps.invert(img.convert("RGB")).convert("L")))
            except Exception:
                pass
        psm_values = [psm] + [value for value in alt_psm if value != psm]
        best_text = ""
        best_score = -1.0
        best_meta = {"ocr_psm": psm, "ocr_oem": oem, "ocr_variant": "base"}
        for variant_name, variant_img in variants:
            for psm_value in psm_values:
                config = self._tessdata_config(tessdata_dir, psm_value, oem)
                try:
                    text = pytesseract.image_to_string(variant_img, lang=lang, config=config)
                except Exception:
                    continue
                score = self._score_text(text)
                if score > best_score:
                    best_score = score
                    best_text = text
                    best_meta = {"ocr_psm": psm_value, "ocr_oem": oem, "ocr_variant": variant_name}
                    # Early exit: if first variant scores well, skip rest
                    if best_score > 0.65 and not alt_psm:
                        return self._postprocess_ocr(best_text), best_meta
        return self._postprocess_ocr(best_text), best_meta

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
        for page in doc.pages:
            text = normalize_text(page.text)
            updated.append(Page(number=page.number, text=text, raw_text=page.raw_text, image_path=page.image_path))
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
        signal = StageSignal(stage=self.name, confidence=0.8, uncertainty=0.2)
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
        signal = StageSignal(stage=self.name, confidence=0.75, uncertainty=0.25)
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
        for step in ["ocr", "deskew", "denoise", "table_form"]:
            if step in route:
                ordered.append(step)
        return ordered
