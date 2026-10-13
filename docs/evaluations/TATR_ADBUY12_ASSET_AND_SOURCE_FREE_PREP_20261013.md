# TATR ad-buy 12: asset acquisition and source-free preparation

**Status:** preparatory only. The locked 12 PDFs were not opened, no Table Transformer model was loaded or used for inference, no row or cell was scored, and `I:\DocAI-Benchmarks\tatr-adbuy12-v1` does not exist. This receipt does not change the [frozen research protocol](TATR_ADBUY12_RESEARCH_PROTOCOL_20261013.md) or its thresholds.

## Pinned assets

The two [Microsoft Table Transformer](https://github.com/microsoft/table-transformer/tree/16d124f616109746b7785f03085100f1f6247575) safetensors were acquired at the protocol's immutable Hugging Face revisions into `I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage`. Both local SHA-256 values and byte lengths match the remotely declared LFS metadata:

| Checkpoint | Local bytes | Local SHA-256 |
| --- | ---: | --- |
| Detection `2357cbe2b5a5d1c03e54f32764f06058933b65ab` | 115,317,516 | `8f1aa73170102c038d40155e2734b343bf07e0fe12594228a8590943b01dccf7` |
| Structure v1.1-All `7587a7ef111d9dcbf8ac695f1376ab7014340a0c` | 115,437,156 | `9df416575a3a36ebd0129342d4f597f14d6e5170268f3d52d28584ab4466a501` |

The stage also contains each revision's exact model config, processor config and model card; the author's card at `30e6112ea20d72cc9fb8f443e34ca119d497cfe6`; and Microsoft's pinned MIT notice, inference source, postprocessor source and inference guide. `product_eval/tatr_asset_preflight.py` verifies all 14 files by independent local size/hash and both class maps. Its asset-only receipt is `I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage\assets-only-receipt-v1.json`, SHA-256 `f0bdd0a8000258b898d1b8900784f79304447e170de966df1b10e9b35c221df3`. It records the active package snapshot but explicitly marks runtime closure, OCR words, cell postprocessing and inference permission **false**. The snapshot has `pypdfium2 5.14.0`, `transformers 4.57.6`, `torch 2.10.0+cpu`, `safetensors 0.7.0`, and no installed `torchvision`. This is not a sealed isolated runtime.

The Hugging Face structure processor config says 800 pixels on its longest edge; the pinned [original inference source](https://github.com/microsoft/table-transformer/blob/16d124f616109746b7785f03085100f1f6247575/src/inference.py) uses 1,000 for structure and 800 for detection. The later runner must explicitly honor the frozen 800/1,000 profile and validate the resize/box convention. No inference has tested that integration.

## Source-free geometry and output adapter

`product_eval/tatr_native_geometry.py` uses PDFium's bitmap position converter to map native character boxes through rendering, crop and page rotation. It derives word tokens from PDFium character order and splits at whitespace or a large page-coordinate spatial break. The split originally failed synthetic rotated pages when computed in image coordinates; the source-free test caught that, and the implementation now uses PDF page coordinates. Tests use a generated synthetic PDF at 0°, 90°, 180° and 270°, including nonzero crop boxes, verify `Alpha`/`Beta` word order, pixel-to-page roundtrips and rendered dark ink inside each claimed box. Invalid or out-of-page boxes fail closed. This is a proposed **native text** feed only; it has not been checked against the selected public PDFs or nontrivial layouts.

`product_eval/tatr_output_adapter.py` maps synthetic DETR logits and normalized boxes to the pinned class names and original image scale, retaining no-object and out-of-image queries with their scores. It is a shape/coordinate adapter, not the [official cell reconstruction](https://github.com/microsoft/table-transformer/blob/16d124f616109746b7785f03085100f1f6247575/src/inference.py). No actual model output has been passed through it.

Validation: `python -m pytest -q product_eval/tests/test_tatr_native_geometry.py product_eval/tests/test_tatr_asset_preflight.py product_eval/tests/test_tatr_output_adapter.py` passed **18/18**. Ruff passed for the six new Python files. Source-only acquisition used no metered AI API; local disk contains 230,919,892 bytes across the 14 verified files. There is no measured inference time, RAM peak, parser score or cost per correct row. A review regression rejects raster clips with zero or inverted area and keeps high-scoring `no object` queries in raw output while marking them ineligible. Native word reading order remains unsealed until multi-column fixtures are checked.

## Remaining gates

The research run remains blocked on a sealed CPU dependency closure, OCR **word** boxes for the two image-only PDFs, semantic compatibility of safetensors model output with Microsoft's structure-to-cell postprocessor using a permissive rectangle implementation, a guarded one-document-per-process runner, and source-pixel overlays on a real first PDF. The protocol's 219-row denominator and continuation bar remain unchanged. Even a completed parser score would not establish end-to-end field extraction quality or satisfy the separate 2,000-source product gate.
