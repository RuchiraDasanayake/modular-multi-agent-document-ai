"""Offline Granite-Docling API smoke on a self-drawn table, never a benchmark PDF.

This only tests the pinned model/runtime interface. It cannot establish cell
accuracy, source grounding, or product readiness.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import time
from pathlib import Path
from typing import Any

MODEL_REVISION = "982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe"
MODEL_SHA256 = "1cdad234deb1cde18ee6a586f849057f19851daf1fedce2e40aff791dbe46f61"
ACQUISITION_SHA256 = "142457cfd4d023afd71983dc0afbbad821a4baff78a1f36163ae6d81d949dccc"
PACKAGES = {
    "torch": "2.9.1+cu128",
    "transformers": "4.56.1",
    "docling-core": "2.101.1",
    "Pillow": "12.3.0",
}
MAX_NEW_TOKENS = 2048
MIN_FREE_GPU_BYTES = 512 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_assets(model_dir: Path, acquisition: Path) -> dict[str, Any]:
    """Require every local asset byte to match the publisher-revision receipt."""
    if sha256_file(acquisition) != ACQUISITION_SHA256:
        raise ValueError("model acquisition receipt hash differs from frozen profile")
    receipt = json.loads(acquisition.read_text(encoding="utf-8"))
    if (receipt.get("status") != "assets_verified_no_inference"
            or receipt.get("revision") != MODEL_REVISION
            or receipt.get("model_id") != "ibm-granite/granite-docling-258M"
            or receipt.get("inference_performed") is not False):
        raise ValueError("model acquisition receipt differs from frozen profile")
    rows = receipt.get("file_receipts")
    if not isinstance(rows, list) or len(rows) != 13:
        raise ValueError("model asset manifest is incomplete")
    names = [row.get("path") for row in rows]
    if (len(set(names)) != len(names)
            or any(not isinstance(name, str) or Path(name).name != name for name in names)
            or {path.name for path in model_dir.iterdir() if path.is_file()} != set(names)):
        raise ValueError("model asset inventory differs from frozen profile")
    for row in rows:
        path = model_dir / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise ValueError(f"model asset differs from frozen profile: {row['path']}")
    weights = next(row for row in rows if row["path"] == "model.safetensors")
    if weights["sha256"] != MODEL_SHA256:
        raise ValueError("model weights differ from pinned revision")
    return {
        "model_revision": MODEL_REVISION,
        "weights_sha256": MODEL_SHA256,
        "acquisition_sha256": sha256_file(acquisition),
        "asset_count": len(rows),
    }


def synthetic_table():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    for x in (0, 300, 600, 899):
        draw.line((x, 10, x, 270), fill="black", width=3)
    for y in (10, 140, 270):
        draw.line((0, y, 899, y), fill="black", width=3)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    for index, value in enumerate(("Item", "Qty", "Price", "Widget", "2", "10.00")):
        row, col = divmod(index, 3)
        draw.text((col * 300 + 25, row * 130 + 45), value, fill="black", font=font)
    return image


def _table_summary(document) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table in document.tables:
        cells = []
        for cell in table.data.table_cells:
            cells.append({
                "text": cell.text,
                "row_start": cell.start_row_offset_idx,
                "row_end": cell.end_row_offset_idx,
                "col_start": cell.start_col_offset_idx,
                "col_end": cell.end_col_offset_idx,
                "bbox": cell.bbox.model_dump(mode="json") if cell.bbox else None,
            })
        tables.append({"cells": cells, "table_provenance": [
            item.model_dump(mode="json") for item in table.prov
        ]})
    return tables


def run(model_dir: Path, acquisition: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError("source-free smoke output already exists")
    assets = verify_assets(model_dir, acquisition)
    versions = {name: importlib.metadata.version(name) for name in PACKAGES}
    if versions != PACKAGES:
        raise ValueError("Granite smoke runtime differs from pinned packages")
    os.environ.update({
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false",
    })
    import torch
    from docling_core.types.doc import DoclingDocument
    from docling_core.types.doc.document import DocTagsDocument
    from transformers import AutoModelForVision2Seq, AutoProcessor

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise ValueError("pinned CUDA BF16 profile is unavailable")
    free_bytes, total_bytes = torch.cuda.mem_get_info()
    if free_bytes < MIN_FREE_GPU_BYTES:
        raise ValueError("GPU free-memory floor is not met")
    output_dir.mkdir(parents=True)
    image = synthetic_table()
    image.save(output_dir / "synthetic.png")
    started = time.perf_counter()
    try:
        processor = AutoProcessor.from_pretrained(model_dir, local_files_only=True,
                                                  trust_remote_code=False)
        model = AutoModelForVision2Seq.from_pretrained(
            model_dir, local_files_only=True, trust_remote_code=False,
            torch_dtype=torch.bfloat16, attn_implementation="sdpa",
        ).to("cuda").eval()
        messages = [{"role": "user", "content": [
            {"type": "image"}, {"type": "text", "text": "Convert this page to docling."},
        ]}]
        prompt = processor.apply_chat_template(messages, add_generation_prompt=True)
        inputs = processor(text=prompt, images=[image], return_tensors="pt").to("cuda")
        torch.manual_seed(20261013)
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS,
                                       do_sample=False, num_beams=1)
        new_ids = generated[:, inputs.input_ids.shape[1]:]
        doctags = processor.batch_decode(new_ids, skip_special_tokens=False)[0].lstrip()
        (output_dir / "synthetic.doctags.txt").write_text(doctags, encoding="utf-8")
        doctags_doc = DocTagsDocument.from_doctags_and_image_pairs([doctags], [image])
        document = DoclingDocument.load_from_doctags(doctags_doc, document_name="Synthetic")
        tables = _table_summary(document)
        result = {
            "status": "source_free_api_completed",
            **assets,
            "versions": versions,
            "model_device": "cuda",
            "dtype": "bfloat16",
            "gpu_free_before_bytes": free_bytes,
            "gpu_total_bytes": total_bytes,
            "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "wall_ms": round((time.perf_counter() - started) * 1000, 3),
            "generated_tokens": int(new_ids.shape[1]),
            "max_new_tokens": MAX_NEW_TOKENS,
            "truncated_or_at_limit": int(new_ids.shape[1]) >= MAX_NEW_TOKENS,
            "table_count": len(tables),
            "tables": tables,
            "synthetic_image_sha256": sha256_file(output_dir / "synthetic.png"),
            "raw_doctags_sha256": sha256_file(output_dir / "synthetic.doctags.txt"),
            "source_pdf_count_opened": 0,
            "gold_count_opened": 0,
            "product_extraction_changed": False,
        }
        (output_dir / "smoke.json").write_text(
            json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return result
    except Exception as exc:
        (output_dir / "failure.json").write_text(json.dumps({
            "status": "failed", "error_type": type(exc).__name__,
            "source_pdf_count_opened": 0, "gold_count_opened": 0,
        }, sort_keys=True) + "\n", encoding="utf-8")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--acquisition", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.model_dir, args.acquisition, args.output_dir),
                     sort_keys=True))


if __name__ == "__main__":
    main()
