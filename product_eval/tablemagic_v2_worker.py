"""Run one source PDF through the pinned local PP-TableMagic v2 CPU pipeline.

The worker receives no gold or schema. Its parent enforces resource/time limits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CONFIG_SHA256 = "7ae76188079fed0e4cadc3ea5570ca85b506b7144b2cf0c3adbad84eb8d0f4a0"


def _model(config: dict, path: tuple[str, ...], root: Path, name: str) -> None:
    node = config
    for key in path:
        node = node[key]
    if node["model_name"] != name:
        raise RuntimeError(f"PaddleX default changed at {path}: {node['model_name']}")
    node["model_dir"] = str(root / name)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--models-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not args.source.is_file() or not args.models_root.is_dir() or args.output_dir.exists():
        parser.error("source/models must exist and output directory must be new")
    args.output_dir.mkdir(parents=True)

    import cv2
    import paddlex
    import yaml
    from paddleocr import TableRecognitionPipelineV2

    config_path = Path(paddlex.__file__).parent / "configs" / "pipelines" / "table_recognition_v2.yaml"
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != CONFIG_SHA256:
        raise RuntimeError("installed PaddleX table pipeline YAML differs from frozen config")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("pipeline_name") != "table_recognition_v2":
        raise RuntimeError("wrong PaddleX table pipeline")
    config["use_doc_preprocessor"] = False
    config["use_layout_detection"] = True
    config["use_ocr_model"] = True
    config["SubPipelines"]["DocPreprocessor"]["use_doc_orientation_classify"] = False
    config["SubPipelines"]["DocPreprocessor"]["use_doc_unwarping"] = False
    modules = config["SubModules"]
    general_ocr = config["SubPipelines"]["GeneralOCR"]["SubModules"]
    top = ("SubModules",)
    for key, name in (
        ("LayoutDetection", "PP-DocLayout-L"),
        ("TableOrientationClassify", "PP-LCNet_x1_0_doc_ori"),
        ("TableClassification", "PP-LCNet_x1_0_table_cls"),
        ("WiredTableStructureRecognition", "SLANeXt_wired"),
        ("WirelessTableStructureRecognition", "SLANeXt_wireless"),
        ("WiredTableCellsDetection", "RT-DETR-L_wired_table_cell_det"),
        ("WirelessTableCellsDetection", "RT-DETR-L_wireless_table_cell_det"),
    ):
        if key not in modules:
            raise RuntimeError(f"missing model node: {key}")
        _model(config, top + (key,), args.models_root, name)
    for key, name in (("TextDetection", "PP-OCRv4_server_det"),
                      ("TextRecognition", "PP-OCRv4_server_rec_doc")):
        if key not in general_ocr:
            raise RuntimeError(f"missing OCR node: {key}")
        _model(config, ("SubPipelines", "GeneralOCR", "SubModules", key),
               args.models_root, name)
    if any(not (args.models_root / name).is_dir() for name in (
        "PP-DocLayout-L", "PP-LCNet_x1_0_doc_ori", "PP-LCNet_x1_0_table_cls",
        "SLANeXt_wired", "SLANeXt_wireless", "RT-DETR-L_wired_table_cell_det",
        "RT-DETR-L_wireless_table_cell_det", "PP-OCRv4_server_det",
        "PP-OCRv4_server_rec_doc",
    )):
        raise RuntimeError("an active local model directory is missing")

    pipeline = TableRecognitionPipelineV2(
        paddlex_config=config,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_layout_detection=True,
        use_ocr_model=True,
        device="cpu",
        engine="paddle_static",
    )
    _write_json(args.output_dir / "startup.json", {"status": "ready"})
    page_count = 0
    for result in pipeline.predict(
        str(args.source), use_doc_orientation_classify=False,
        use_doc_unwarping=False, use_layout_detection=True, use_ocr_model=True,
        use_table_orientation_classify=True, use_ocr_results_with_table_cells=True,
        use_e2e_wired_table_rec_model=False, use_e2e_wireless_table_rec_model=False,
        use_wired_table_cells_trans_to_html=False,
        use_wireless_table_cells_trans_to_html=False,
    ):
        if result["page_index"] != page_count:
            raise RuntimeError("TableMagic returned non-contiguous PDF page indices")
        image = result["doc_preprocessor_res"]["output_img"]
        height, width = image.shape[:2]
        geometry = {
            "page_index": page_count,
            "image_width": int(width),
            "image_height": int(height),
            "table_region_ids": [int(table["table_region_id"])
                                 for table in result["table_res_list"]],
        }
        if not cv2.imwrite(str(args.output_dir / f"page-{page_count:02d}.png"), image):
            raise RuntimeError("failed to save exact TableMagic page raster for visual audit")
        result.save_to_json(save_path=str(args.output_dir / f"page-{page_count:02d}.json"))
        _write_json(args.output_dir / f"geometry-{page_count:02d}.json", geometry)
        page_count += 1
    print(f"saved_pages={page_count}")


if __name__ == "__main__":
    main()
