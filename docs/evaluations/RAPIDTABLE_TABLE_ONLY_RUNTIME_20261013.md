# RapidTable 3.0.2 clean table-only runtime

**13 October 2026 — source-free table runtime PASS; selected-PDF inference HOLD.** This is a separate Windows CPython 3.11 CPU environment. The original 23-wheel RapidTable/RapidOCR v1 environment and its failed OpenCV ownership audit remain unchanged. No selected PDF, gold annotation, OCR model, or product extractor was opened or changed.

## Boundary checked

The `rapid_table==3.0.2` wheel declares no RapidOCR dependency. Its `RapidTable.__call__(..., ocr_results=[tuple])` path formats supplied per-image OCR polygons, texts and scores and passes them to the table matcher. With `use_ocr=True`, the constructor still calls `importlib.import_module("rapidocr")` and catches `ModuleNotFoundError`; it logs that RapidOCR is absent. This is an **attempted import**, although no RapidOCR distribution or module is installed or loaded. Omitting `ocr_results` would try to call the absent OCR engine. Callers must therefore supply and validate one OCR tuple per image. A real OCR source and coordinate adapter remain separate work.

## Installed closure

The clean environment is `I:\DocAI-Benchmarks\rapidtable-table-only-runtime-v1`. It was created with `venv --without-pip`; the external Python 3.11 pip installed the [18 hash-pinned wheels](locks/rapidtable_table_only_py311_windows.txt) offline with `--no-compile`. The [table-only lock](../../product_eval/fixtures/rapidtable_table_only_runtime_lock.json), canonical LF SHA-256 `487135bf5438212ea5ac46778b0e53e15c0314fb34b28cec83043e29834447a6`, pins their exact wheel hashes, sizes, declared licence metadata and notice bytes. The verifier accepts Git's Windows CRLF checkout of the same text. The wheels total 80,545,536 compressed bytes. `opencv-python==5.0.0.93` is the sole `cv2` owner; neither `opencv-python-headless` nor `rapidocr` is installed. `tqdm==4.70.1` is pinned because RapidTable imports it at runtime despite not declaring it in wheel metadata.

The [preflight](../../product_eval/rapidtable_table_only_preflight.py) compares all installed distributions with the lock, verifies each wheel and its internal `RECORD`, compares **1,980 wheel payload files** and installed `RECORD` rows and bytes, and checks **43 hashed installer extras**. It found zero payload mismatches, zero hashed-extra mismatches, zero unhashed extra entries, and zero multiply owned installed paths. The receipt pins the SHA-256 of each installed distribution's `RECORD`; byte-for-byte copies of all 18 installed `RECORD` files are retained in the external `installed-records` directory. `installed_distribution_contents_verified=true`. A second audit after inference returned the same closure. `pip check` reported no broken requirements.

The lock verifies **44 embedded licence/notice files**, including three NumPy source-tree licences that the old 23-wheel inventory omitted. The `flatbuffers==25.12.19` wheel has no embedded licence; a copy of the official v25.12.19 licence is retained with the external provenance at `I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\flatbuffers-v25.12.19-LICENSE`, SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. This is precise notice evidence, not approval of a product attribution bundle or redistribution.

## Synthetic result and reproduction

The [publisher provenance receipt](RAPIDTABLE_PUBLISHER_ASSET_RIGHTS_20261013.md) binds the exact 7,758,305-byte SLANet-plus ONNX file to SHA-256 `d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b`. The clean runtime's source-free smoke supplied six `float32[4,2]` OCR polygons with six texts and scores for one 900×300 artificial 2×3 table. The actual model session used only `CPUExecutionProvider`. It returned six physical HTML cells, six cell boxes, six logic points, and all six exact text values at the expected logical positions. RapidOCR remained absent before and after the call. The model stage reported 0.064 seconds for this artificial crop with supplied text; that excludes OCR, localization, PDF rasterization and review.

The external receipt at `I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\source-free-six-cell-receipt-final-v2.json` has SHA-256 `84b93422e9410577fdc6c6ffd539428265273060d756c69dc3bf22b43e873dfd`. The staged wheelhouse, install log, hashed requirements and FlatBuffers licence are beside it. To rerun the read-only audit and synthetic smoke, choose a new absent output filename:

```powershell
$env:PYTHONPATH = 'I:\DocAI-Benchmarks\rapidtable-table-only-wt'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = 'I:\DocAI-Benchmarks\rapidtable-table-only-temp-v1'
$env:TMP = $env:TEMP
I:\DocAI-Benchmarks\rapidtable-table-only-runtime-v1\Scripts\python.exe -m product_eval.rapidtable_table_only_preflight `
  --wheel-lock I:\DocAI-Benchmarks\rapidtable-table-only-wt\product_eval\fixtures\rapidtable_table_only_runtime_lock.json `
  --wheel-dir I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\wheels `
  --model I:\DocAI-Benchmarks\rapidtable-clean-asset-publisher-v1\slanet-plus.onnx `
  --flatbuffers-license I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\flatbuffers-v25.12.19-LICENSE `
  --output I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\NEW-absent-receipt.json
```

The existing RapidTable `RECORD` and synthetic contract suites passed 14 focused tests. After validation, free host memory was 9.63 GiB and C: had 4.68 GiB free. The next gate is the separate OCR word source and its crop-coordinate alignment, followed by table localization, source-page cell evidence and a reviewed guarded runner. Selected-PDF inference, the 12-source score and product promotion remain held by those gates.
