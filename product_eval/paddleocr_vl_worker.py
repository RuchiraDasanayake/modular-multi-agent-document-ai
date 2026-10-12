"""Isolated PaddleOCR-VL 1.6 full-pipeline child for a single public PDF.

This module runs inside the separate Paddle environment. It has no gold access.
The parent process imposes resource and time limits and hashes saved page JSON.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--layout-dir", required=True, type=Path)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.source.is_file() or not args.layout_dir.is_dir():
        parser.error("source PDF and local layout directory must exist")
    if not args.server_url.startswith("http://127.0.0.1:") or not args.server_url.endswith("/v1"):
        parser.error("the VLM server must be loopback llama.cpp /v1")
    args.output_dir.mkdir(parents=True, exist_ok=False)

    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(
        pipeline_version="v1.6",
        layout_detection_model_name="PP-DocLayoutV3",
        layout_detection_model_dir=str(args.layout_dir),
        vl_rec_backend="llama-cpp-server",
        vl_rec_server_url=args.server_url,
        vl_rec_max_concurrency=1,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_layout_detection=True,
        use_chart_recognition=False,
        use_seal_recognition=False,
        use_ocr_for_image_block=False,
        format_block_content=False,
        use_queues=False,
        device="cpu",
    )
    pages = list(pipeline.predict(input=str(args.source), layout_shape_mode="rect",
                                  temperature=0.0, max_new_tokens=3072))
    rebuilt = list(pipeline.restructure_pages(pages, merge_tables=True,
                                              relevel_titles=False, concatenate_pages=False))
    if len(rebuilt) != len(pages):
        raise RuntimeError("PaddleOCR-VL page reconstruction changed page count")
    for page_number, result in enumerate(rebuilt):
        result.save_to_json(save_path=str(args.output_dir / f"page-{page_number:02d}.json"))
    print(f"saved_pages={len(rebuilt)}")


if __name__ == "__main__":
    main()
