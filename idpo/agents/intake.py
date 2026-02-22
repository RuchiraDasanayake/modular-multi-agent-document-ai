from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

from idpo.core.types import Document, Page


class IntakeAgent:
    name = "intake"
    version = "v1"

    def ingest(self, input_path: str) -> List[Document]:
        path = Path(input_path)
        if path.is_dir():
            docs = []
            for file_path in sorted(path.glob("*.json")):
                docs.extend(self._load_json(file_path))
            for file_path in sorted(path.glob("*.txt")):
                docs.append(self._load_text(file_path))
            for file_path in sorted(path.glob("*.pdf")):
                docs.extend(self._load_pdf(file_path))
            for file_path in sorted(path.glob("*.*")):
                if file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
                    docs.append(self._load_image(file_path))
            return docs
        if path.suffix.lower() == ".json":
            return self._load_json(path)
        if path.suffix.lower() == ".txt":
            return [self._load_text(path)]
        if path.suffix.lower() == ".pdf":
            return self._load_pdf(path)
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            return [self._load_image(path)]
        raise ValueError(f"Unsupported input path: {input_path}")

    def _load_text(self, path: Path) -> Document:
        content = path.read_text(encoding="utf-8")
        page = Page(number=1, text=content, raw_text=content)
        return Document(
            doc_id=path.stem,
            source="digital",
            path=str(path),
            pages=[page],
            metadata={},
        )

    def _load_json(self, path: Path) -> List[Document]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = [payload]
        docs = []
        for entry in payload:
            pages = []
            for page in entry.get("pages", []):
                pages.append(
                    Page(
                        number=page.get("number", len(pages) + 1),
                        text=page.get("text", ""),
                        raw_text=page.get("raw_text"),
                        image_path=page.get("image_path"),
                        metadata=page.get("metadata", {}),
                    )
                )
            doc = Document(
                doc_id=entry["doc_id"],
                source=entry.get("source", "synthetic"),
                path=str(path),
                pages=pages,
                metadata=entry.get("metadata", {}),
            )
            docs.append(doc)
        return docs

    def _load_image(self, path: Path) -> Document:
        page = Page(number=1, text="", raw_text="", image_path=str(path), metadata={"file_type": path.suffix.lower()})
        return Document(
            doc_id=path.stem,
            source="scanned",
            path=str(path),
            pages=[page],
            metadata={},
        )

    def _load_pdf(self, path: Path) -> List[Document]:
        pages, has_text = self._extract_pdf_text(path)
        source = "digital" if has_text else "scanned"
        doc = Document(
            doc_id=path.stem,
            source=source,
            path=str(path),
            pages=pages,
            metadata={},
        )
        return [doc]

    def _extract_pdf_text(self, path: Path) -> Tuple[List[Page], bool]:
        try:
            from pypdf import PdfReader
        except Exception:
            pages = [Page(number=1, text="", raw_text="", image_path=str(path), metadata={"file_type": ".pdf", "pdf_page_index": 0})]
            return pages, False
        reader = PdfReader(str(path))
        pages: List[Page] = []
        has_text = False
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            raw_text = text
            if text.strip():
                has_text = True
            pages.append(
                Page(
                    number=idx,
                    text=text,
                    raw_text=raw_text,
                    image_path=str(path),
                    metadata={"file_type": ".pdf", "pdf_page_index": idx - 1},
                )
            )
        if not pages:
            pages = [Page(number=1, text="", raw_text="", image_path=str(path), metadata={"file_type": ".pdf", "pdf_page_index": 0})]
        return pages, has_text
