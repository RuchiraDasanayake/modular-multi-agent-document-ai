# Image-only table OCR word prerequisite: source-free receipt

**Decision (13 October 2026): synthetic word-token handoff PASS; selected-PDF inference remains NO-GO.** RapidOCR 3.10.0 with `return_word_box=True` yielded separate word polygons, text and reported scores from a drawn raster. Four `ocr_word` records passed the existing TATR token contract. No selected PDF, gold record, cloud service, or product extractor was opened. This is no claim about the two scanned PDFs, table text quality, or parser accuracy.

## Choice and limits

| Local CPU path | Word geometry and score | Decision |
| --- | --- | --- |
| RapidOCR default output | `boxes`, `txts`, `scores` are **line** regions and scores. | Cannot feed TATR as words. Still the existing RapidTable line-tuple shape. |
| RapidOCR 3.10.0 `return_word_box=True` | `word_results` supplies separate English word text, four-point polygons and numeric reported scores. It computes word geometry within a detected line using recognizer positions; these are not independent word detections. | **Chosen for source-free TATR geometry handoff**, using the same OCR pass that can supply RapidTable's line tuple. Keep raw lines and words. |
| Tesseract 5.5.3 TSV | Level-5 rows directly supply one word, rectangular pixel box and a 0–100 score. The already pinned local binary/English data returned the same four words on this raster. | Viable fallback if confidence must be demonstrably word scoped; would need a separate pinned binary/DLL and notice closure for this trial. |

The [RapidOCR usage reference](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/) distinguishes line `boxes` from `word_results`. Its [parameter reference](https://rapidai.github.io/RapidOCRDocs/v3.1.1/install_usage/rapidocr/parameters/) documents `return_word_box` and English word grouping. [Tesseract's official manual](https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc) states that TSV writes each recognized word with a box, confidence and text.

**Confidence qualification:** The RapidOCR tuple score is recorded exactly as emitted, in `ocr_confidence`, with `ocr_confidence_basis` marked uncalibrated. In the [v3.10.0 decoder](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/ch_ppocr_rec/utils.py), `WordInfo.confs` receives a character score list; the [word-box code](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/cal_rec_boxes/main.py) zips that list to grouped word strings and polygons. This appears to associate the first *N* character scores with *N* grouped words, rather than aggregating each word's own characters. This is an inference from the pinned source. **Do not use these scores as calibrated or verified per-word probabilities or to set acceptance thresholds.** The current TATR contract only validates a finite 0–1 provenance value; if downstream ranking needs genuine word-specific confidence, use the Tesseract fallback or a separately reviewed score adapter.

## Pin and rights evidence

The isolated OCR runtime is `I:\DocAI-Benchmarks\tatr-ocr-word-runtime-v1`, Python 3.11.0, installed offline from the 21 cached dependency wheels in `I:\DocAI-Benchmarks\rapidtable-adbuy12-wheels-v1`. It contains `rapidocr==3.10.0`, `onnxruntime==1.31.0`, and **only** `opencv-python-headless==5.0.0.93`; the regular OpenCV wheel is absent. This avoids the conflicting double-OpenCV installation in the earlier RapidTable v1 runtime, where the first exploratory synthetic check ran. The independent repeat in the headless-only runtime gave the same four words and CPU sessions. `pip check` passed.

The source release is [RapidOCR v3.10.0](https://github.com/RapidAI/RapidOCR/tree/v3.10.0), Git tag commit `38ed48d802cfb9f91d24153258427beef2b3d50c`. The exact cached wheel is `rapidocr-3.10.0-py3-none-any.whl`, SHA-256 `2fc34e26cd0f48514804a94f8832283039c7334076bff60768b1fed9ad068050`. The [v3.10.0 model registry](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/rapidocr/default_models.yaml) is pinned to SHA-256 `90e0159dead16c21adbf000014a46043c981ae097f041d92d8b19a52c2f2ed9a` and names these [Apache-2.0 models](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/):

| Bundled ONNX file | SHA-256 | Registry revision |
| --- | --- | --- |
| `PP-OCRv6_det_small.onnx` | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` | RapidAI ModelScope `v3.10.0` |
| `PP-OCRv6_rec_small.onnx` | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` | RapidAI ModelScope `v3.10.0` |
| `ch_ppocr_mobile_v2.0_cls_mobile.onnx` | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` | RapidAI ModelScope `v3.10.0` |

The bundled Apache license SHA-256 is `3e0af25fdd06aa9586ae97adb00ea927ebe5a3805ac77d2d3a81ce5f55693333`; `MODEL_LICENSES.md` SHA-256 is `c5fd0e8603d3df743355b546121e6fe0f4ef8ff455c5a85c1681fd3ae520e153`. These and all three weights are checked before inference. The model notice links ModelScope `v3.9.2`, while the installed authoritative registry links `v3.10.0`; both list the same three hashes. The byte hashes, not the mutable tag labels, identify the trial artifacts. Upstream PP-OCRv6 [detection](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_det_onnx) and [recognition](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx) model cards also state Apache-2.0.

The full dependency wheel inventory and embedded notice hashes are in [`rapidtable_v3_runtime_lock.json`](../../product_eval/fixtures/rapidtable_v3_runtime_lock.json), SHA-256 `1264a56da9c666676deb1a442eae8811aff296001340c105d07acd90e3042f4a`. The [OCR lock](../../product_eval/fixtures/tatr_rapidocr_word_lock.json), SHA-256 `c23bc6774d867e477ba279b8e0651865668f54c791a027907d8dde24179ab8ed`, selects those wheels except `rapid_table` and regular `opencv-python`, and pins the RapidOCR wheel, model files, registry and notices. Preflight verified all 21 cached wheel hashes and embedded notices, 2,206 installed payload files directly against wheel bytes, and 2,236 hashed installed `RECORD` entries. Generated `.pyc`, bootstrap `pip`/`setuptools`, and host DLLs are outside this closure. Five dependency wheels have no embedded notice in the cached lock (`flatbuffers`, `onnxruntime`, `opencv-python-headless`, `protobuf`, `six`). Eight official release license/third-party notice files for those packages and OpenCV core were staged at `I:\DocAI-Benchmarks\tatr-ocr-word-notices-v1`; the OCR lock pins each source URL and SHA-256, and preflight rehashes all eight. Redistributors must actually include applicable notices in their package; this local stage is not a redistributed build. No packages or model assets were copied into the repository.

## Synthetic output and reproducibility

The runner drew `NORTH SOUTH` and `ALPHA BETA` on a new 1100×340 raster with a hashed Arial font. The PNG SHA-256 is `9fd947dc815c49343a52b2d44d09bc9e79b3367273ea1be5ac4417a8cc8d4c48`. The table below lists every OCR word polygon's enclosing pixel box and its **raw RapidOCR-reported** score; the receipt preserves all four original quadrilaterals and line regions.

| Word | Pixel box `[left,top,right,bottom]` | Reported score |
| --- | --- | ---: |
| `NORTH` | `[49,58,256,124]` | 0.99997 |
| `SOUTH` | `[269,58,476,124]` | 0.99995 |
| `ALPHA` | `[59,190,239,252]` | 0.99995 |
| `BETA` | `[266,190,404,252]` | 0.99988 |

Detection, classification and recognition ONNX sessions each reported exactly `CPUExecutionProvider`; `onnxruntime.get_available_providers()` alone was not used as proof of actual session selection. The adapter preserves engine order as contiguous `reading_order`, carries the exact word quad, emits a finite word bbox and unique source ID, and rejects absent word results, multiword tokens, malformed scores, out-of-raster or degenerate polygons, and line/word text mismatch. It does not fabricate boxes by splitting line polygons.

Run from this checkout with the isolated interpreter:

```powershell
$env:PYTHONPATH = (Get-Location).Path
& I:\DocAI-Benchmarks\tatr-ocr-word-runtime-v1\Scripts\python.exe -m product_eval.tatr_ocr_word_source_free `
  --runtime-root I:\DocAI-Benchmarks\tatr-ocr-word-runtime-v1 `
  --wheelhouse I:\DocAI-Benchmarks\rapidtable-adbuy12-wheels-v1 `
  --notices-root I:\DocAI-Benchmarks\tatr-ocr-word-notices-v1 `
  --font C:\Windows\Fonts\arial.ttf `
  --output-dir I:\DocAI-Benchmarks\tatr-ocr-word-assets-v1\sealed-smoke-NEW
```

The final append-only receipt is `I:\DocAI-Benchmarks\tatr-ocr-word-assets-v1\sealed-smoke-005\receipt.json`, SHA-256 `af5e393646fa158245df0739f63fe39ba9bd10a138c421aea2ed225b3a8a6524`. The CLI only draws its own image; it has no PDF, gold, or arbitrary image argument. Before each inference, C: free space exceeded 4 GiB and host available RAM exceeded 6 GiB.

Validation: `python -m pytest -q product_eval/tests/test_tatr_ocr_word_source_free.py product_eval/tests/test_tatr_cell_compat.py` (24 passed); `python -m ruff check product_eval/tatr_ocr_word_source_free.py product_eval/tests/test_tatr_ocr_word_source_free.py` (passed); offline wheel, installed-byte and staged-notice preflight (passed); synthetic CPU OCR and TATR token preparation (passed). The selected-PDF gate still needs page/crop transforms, source-pixel overlay, table model output compatibility and its guarded runner. The OCR confidence limitation must be respected, and a distributable runtime must package applicable notices and resolve its host DLL boundary.
