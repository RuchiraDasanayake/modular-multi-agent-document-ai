# CORD development full-page OCR comparison: frozen protocol

**Status, 12 October 2026:** protocol and input preflight were fixed before OCR inference; the completed result is [reported separately](CORD_FULL_PAGE_OCR_DEV_RESULT_20261012.md). This is a 60-receipt development diagnostic, not a production OCR change or an official CORD score. The 40 reserved receipts are excluded from selection, inspection, tuning, and inference.

## Question and source lock

Does full-page [RapidOCR 3.10.0](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/) with PP-OCRv6 small detection and recognition expose more of CORD's creator-annotated receipt text than Tesseract, when both see the same original PNGs? The previous [recognition-only crop comparison](CORD_DEVELOPMENT_TEXT_BOX_OCR_RESULT_20261012.md) gave each engine creator-provided boxes and therefore could not answer this question. [CORD's source format](https://github.com/clovaai/cord) provides `valid_line.words[].text` and quads; those 1,389 nonblank boxes across 796 lines are the full-page OCR positive labels. `dontcare`, non-annotated printed text, and false-positive transcription are outside this partial gold.

| Frozen input | SHA-256 |
| --- | --- |
| CORD v2 creator test Parquet, revision `7f0115a4b758a71d6473b8d085751692da2fef98` | `51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7` |
| 60-source development cohort | `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a` |
| 1,389-box development manifest, prepared before this experiment | `03eeddf3526b28031582460419b3c1ed27bcacc285e194d193b19110fbb610f5` |
| CORD development partial positive extraction gold | `84a097116eaad75fb66265447d1b831f5a2ffa98792e10e9ad7edb517cb8e318` |

The runner checks every selected image SHA and that its resolved path is under `input_development`; it checks the annotation manifest, source identities, unique hashes, and that the 60 hashes do not intersect the frozen reserved cohort. It does not open reserved PNGs or labels. The two engines process the same original PNG file, with no rescale, crop, deskew, rotation, or PDF render. Engine-internal default preprocessing remains part of each engine's fixed implementation.

## Fixed engines and execution

| Engine | Setup |
| --- | --- |
| Tesseract | Windows 5.5.3.20260724 executable SHA `c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420`, English traineddata SHA `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`; `--oem 3 --psm 6 tsv`, `OMP_THREAD_LIMIT=4`, 30-second page timeout. The returned TSV word hierarchy forms line text and rectangular line boxes in original image pixels. |
| RapidOCR | Version 3.10.0, ONNX Runtime 1.23.2, CPU execution only, four intra-op and one inter-op threads; English bundled PP-OCRv6 **small** detector SHA `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`, recognizer SHA `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`, angle classifier SHA `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`. Detection, classification, and recognition are enabled; defaults include maximum image side 2,000 px, detector side 736 px, preprocessing and vertical padding. A synthetic warm-up loads the three sessions; its cold time is separate. Actual session providers must all be `CPUExecutionProvider`. |

The model hashes and rights are recorded in the [30-page pilot](RAPIDOCR_PPOCRV6_THIRTY_SCAN_PILOT.md). Raw output keeps engine line order, text, confidence, original-pixel polygon, and deterministic character offsets into the page text. A separate geometry index sorts by position without rewriting engine order. Every detected box is checked against original PNG dimensions; out-of-bounds boxes are retained and counted, not silently clipped. Both engines' failed or timed-out pages remain in the 60-page denominator with blank text. A 30-minute wall budget stops the run without a summary if incomplete; any rerun needs new output paths.

## Predeclared measures and limits

1. **Creator box positive text availability:** Unicode NFKC, casefold, and alphanumeric-token normalization on both annotation and OCR. A box is page-present if its normalized text appears in the engine's full-page text. This is an optimistic, duplicate-sensitive string proxy, not OCR CER, detection precision, or field extraction. For a geometry-local version, join OCR lines whose rectangular bounds overlap at least half of the annotated quad's bounding rectangle; check the same string in those local lines. This is still a proxy: one OCR line can cover several creator boxes, and quad/box assignment is approximate. Report 1,389 fixed boxes and all four paired outcomes, per-receipt macro rates, and a 10,000-replicate paired receipt bootstrap with seed `20261012`.
2. **Partial extraction-label text ceiling:** Check exact normalized page-text presence separately for the fixed 195 scalar values and 458 linked menu cells. A menu row is *text-complete* when every annotated name, price, and optional quantity string appears somewhere on the page. The row's values can be on unrelated lines; text-complete is **not** a linked or correctly extracted row. Repeated values can over-credit. Keep denominators 195/458/157 and compare paired changes.
3. **Unchanged deterministic downstream logic:** Feed each OCR page string to the current no-model `_process_document` extraction logic without gold, retaining its schema IDs and pending-review status; score the two resulting candidate files with the existing CORD positive-only scorer. This bypasses file intake/OCR routing and is not a full `process-auto` service run. Report exact proposed and accepted scalar/cell/row recall separately. The original full product Tesseract run had 0/195 scalar, 0/458 cell and 0/157 complete-row exact proposed recall; its adaptive retry path is a distinct baseline and its 604-second wall clock must not be compared directly with this single-pass diagnostic.
4. **Operating profile:** Record per-page Tesseract and warm RapidOCR latency (p50/p95/total), synthetic RapidOCR cold load, page failures/empty text, sampled Tesseract child-process RSS versus RapidOCR worker RSS, runtime/version/model/source/output SHA, and CPU provider placement. RSS samples every 20 ms can miss short peaks. This run does not measure energy, reviewer time, production throughput, monetary compute cost, or cloud spend (no cloud calls).

No threshold, page router, or model choice is tuned on these outputs. A PP-OCRv6 product adapter is justified only by a separate adjudicated set showing downstream value/row/evidence benefit at acceptable cost; any actual extraction-path implementation then requires a fresh 2,000-distinct-document gate.

## Reproduction

Run from the repository root with the isolated Python 3.11 environment `E:\DocAI-Benchmarks\tools\rapidocr-3.10-venv`. The `check` mode hashes inputs and validates versions/models without inference; `run` repeats the preflight and refuses an existing output directory. Raw source images, gold, outputs, and candidate files remain outside Git.

```powershell
$py = 'E:\DocAI-Benchmarks\tools\rapidocr-3.10-venv\Scripts\python.exe'
$stage = 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a'
$out = Join-Path $stage 'full-page-ocr-dev-v1'
& $py -m product_eval.cord_page_ocr_diagnostic check --stage-root $stage --output-dir $out --tesseract 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tesseract.exe' --tessdata 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tessdata'
& $py -m product_eval.cord_page_ocr_diagnostic run --stage-root $stage --output-dir $out --tesseract 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tesseract.exe' --tessdata 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tessdata' --max-wall-seconds 1800
```
