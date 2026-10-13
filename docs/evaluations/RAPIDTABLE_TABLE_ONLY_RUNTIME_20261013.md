# RapidTable 3.0.2 clean table-only runtime

**13 October 2026 — source-free table runtime PASS; selected-PDF inference HOLD.** This is a separate Windows CPython 3.11 CPU environment. The original 23-wheel RapidTable/RapidOCR v1 environment and its failed OpenCV ownership audit remain unchanged. No selected PDF, gold annotation, OCR model, or product extractor was opened or changed.

## Boundary checked

The `rapid_table==3.0.2` wheel declares no RapidOCR dependency. Its `RapidTable.__call__(..., ocr_results=[tuple])` path formats supplied per-image OCR polygons, texts and scores and passes them to the table matcher. With `use_ocr=True`, the constructor still calls `importlib.import_module("rapidocr")` and catches `ModuleNotFoundError`; it logs that RapidOCR is absent. This is an **attempted import**, although no RapidOCR distribution or module is installed or loaded. Omitting `ocr_results` would try to call the absent OCR engine. Callers must therefore supply and validate one OCR tuple per image. A real OCR source and coordinate adapter remain separate work.

## Installed closure

The clean environment is `I:\DocAI-Benchmarks\rapidtable-table-only-runtime-v1`. It was created with `venv --without-pip`; the external Python 3.11 pip installed the [18 hash-pinned wheels](locks/rapidtable_table_only_py311_windows.txt) offline with `--no-compile`. The [table-only lock](../../product_eval/fixtures/rapidtable_table_only_runtime_lock.json), canonical LF SHA-256 `c817cd6e6043e4dad24ca05889362d57d7e7f7f952cf339bd7899706011dff24`, pins their exact wheel hashes, sizes, declared licence metadata, notice bytes and **18 installed `RECORD` content hashes**. The verifier accepts Git's Windows CRLF checkout of the same text. The wheels total 80,545,536 compressed bytes. `opencv-python==5.0.0.93` is the sole `cv2` owner; neither `opencv-python-headless` nor `rapidocr` is installed. `tqdm==4.70.1` is pinned because RapidTable imports it at runtime despite not declaring it in wheel metadata.

The [preflight](../../product_eval/rapidtable_table_only_preflight.py) compares all installed distributions with the lock, verifies each wheel and its internal `RECORD`, compares **1,980 wheel payload files** and installed `RECORD` rows and bytes, and checks **43 hashed installer extras**. It found zero payload mismatches, zero hashed-extra mismatches, zero unhashed extra entries, and zero multiply owned installed paths. Pinning the installed `RECORD` hashes prevents an extra hashed importable file from being silently admitted. The checker also inventories all **2,034 site-packages files** against installed `RECORD` entries, rejects extra files, namespace directories and import-path extensions, verifies each vendor import root resolves inside the sealed runtime, and checks **372 loaded vendor module files** after inference. Its only permitted unrecorded directory is RapidTable's empty model-cache directory. Byte-for-byte copies of all 18 installed `RECORD` files are retained in the external `installed-records` directory. `installed_distribution_contents_verified=true`. A second audit after inference returned the same closure. `pip check` reported no broken requirements.

The lock verifies **44 embedded licence/notice files**, including three NumPy source-tree licences that the old 23-wheel inventory omitted. The `flatbuffers==25.12.19` wheel has no embedded licence; a copy of the official v25.12.19 licence is retained with the external provenance at `I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\flatbuffers-v25.12.19-LICENSE`, SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. This is precise notice evidence, not approval of a product attribution bundle or redistribution.

## Synthetic result and reproduction

The [publisher provenance receipt](RAPIDTABLE_PUBLISHER_ASSET_RIGHTS_20261013.md) binds the exact 7,758,305-byte SLANet-plus ONNX file to SHA-256 `d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b`. The clean runtime's source-free smoke supplied six `float32[4,2]` OCR polygons with six texts and scores for one 900×300 artificial 2×3 table. The supplied texts use `SUPPLIED_` markers absent from the painted raster, so exact HTML matches demonstrate that RapidTable used the tuple. The actual ONNX Runtime session used only `CPUExecutionProvider`. It returned six physical HTML cells, six cell boxes, six logic points, and all six marked text values at the expected logical positions; the returned image matched the input. RapidOCR remained absent before and after the call. The receipt records model-stage timing for this artificial crop with supplied text; that excludes OCR, localization, PDF rasterization and review.

The hardened external receipt at `I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\source-free-six-cell-receipt-review-v4.json` has SHA-256 `0ad337e64445f12354f9a0eba88aa6be99f316f7d0ca685dca9689a9c2e21edb`. After integrating the checker into the main checkout and applying lint-only edits, a fresh hardened source-free run at `I:\DocAI-Benchmarks\rapidtable-table-only-provenance-v1\source-free-six-cell-main-hardened-001.json`, SHA-256 `81698f67c49232d0e4082e7ce6c4850bb4c22f7a732832b4fc22725aa01b6ae2`, verified the same six supplied-text cells, 2,034 site-package files, 372 loaded vendor modules and CPU-only model session. An earlier main-checkout receipt at `source-free-six-cell-main-001.json`, SHA-256 `8b3c929c8b980b5671777449fc27b433749bad090734e66a89806146cf6b9b2f`, predates the import-path and inventory checks above. These are source-free synthetic results, not selected-PDF results. The staged wheelhouse, install log, hashed requirements and FlatBuffers licence are beside the receipts. To rerun the read-only audit and synthetic smoke, choose a new absent output filename:

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

The existing RapidTable `RECORD` and synthetic contract suites plus nine new fail-closed fixtures passed **23 focused tests**. After validation, free host memory was 9.55 GiB and C: had 4.63 GiB free. The next gate is the separate OCR word source and its crop-coordinate alignment, followed by table localization, source-page cell evidence and a reviewed guarded runner. Selected-PDF inference, the 12-source score and product promotion remain held by those gates.
