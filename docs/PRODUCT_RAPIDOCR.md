# Optional local RapidOCR adapter

Classification: supporting; action: keep. This adapter is opt-in and is not the
default OCR engine. It recognizes lines; it does not infer tables, field values,
calibrated confidence, or correct extraction from an OCR quotation alone.

## Contract

`idpo.product_auto.rapid_ocr.recognize_image(image, config=...)` accepts one PIL
image and returns `RapidOcrResult(text, metadata)`. Use an already selected page
or image frame. The caller retains source identity, page number and raster plan.
The adapter rejects images above 4096 pixels on either edge or 12 million pixels
before allocating its RGB copy. It never renders PDFs or silently resizes input.

The caller must preserve returned text verbatim and copy `ocr_lines` and
`ocr_provenance` into the page artifact. Offsets are Python Unicode code point
offsets in the exact returned text; lines are joined by one newline, without
trimming or normalization. Polygons are original input-raster pixels in engine
output order. They are line polygons, not word boxes. Do not use nominal DPI to
map them to PDF coordinates: retain the actual `pdf_render_plan` and dimensions.
JavaScript consumers must account for UTF-16 offsets before slicing Unicode.

`RapidOcrError.reason` is a content-free failure code. An unconfigured engine,
wrong models, resource limit, or empty OCR result is a failure, never a successful
empty extraction. The caller may present review or an explicitly recorded
fallback. It must not replace a failed OCR result with rejected PDF text.

## Local configuration

Select it with `python -m idpo.cli process-auto --input <path> --ocr-engine rapidocr`
or `process_auto(..., ocr_engine="rapidocr")`. These variables configure it;
setting them alone does not change the default engine:

| Variable | Requirement |
| --- | --- |
| `IDPO_RAPIDOCR_PYTHON` | Absolute path to the separate, provisioned interpreter |
| `IDPO_RAPIDOCR_TIMEOUT_S` | Default 120; 1–180 seconds per page including initialization |
| `IDPO_RAPIDOCR_MAX_RSS_MIB` | Default 1536; 128–2048 MiB sampled process-tree RSS |
| `IDPO_RAPIDOCR_WORK_DIR` | Optional existing absolute private scratch directory |

The integration uses the existing bounded PDF rasterizer, performs at most one
RapidOCR attempt per page, and preserves OCR text and line metadata without the
legacy repair or Tesseract fallback. The effective child timeout is the smaller
of the configured RapidOCR timeout and the product `--ocr-page-budget-s`. Image
containers with multiple frames currently fail with
`rapidocr_multiframe_requires_split`: split them into individual images first.
Oversized image rasters are rejected explicitly rather than resized silently.

Run `python scripts/check_product_runtime.py --ocr-engine rapidocr --json` with
the environment above for an additional synthetic local OCR check. Its
`optional_ocr` result controls overall readiness. Existing Tesseract checks remain
required because schema sampling currently uses Tesseract. Omitting the engine
flag preserves the original preflight contract. Native launcher configuration
must explicitly pass the engine flag and worker environment when enabling this
profile; the adapter does not change a running deployment by itself.

The parent needs Pillow and psutil, already in `requirements-worker.txt`. The
separate interpreter needs the optional `requirements-rapidocr.txt` environment.
The tested deployment is Windows x64 / Python 3.11. Install no GPU or desktop
OpenCV provider into that environment. The adapter checks RapidOCR 3.10.0,
ONNX Runtime 1.31.0 and headless OpenCV 5.0.0.93 before loading models.

Provision these files under the installed `rapidocr/models` directory:

| File | SHA-256 |
| --- | --- |
| PP-OCRv6_det_small.onnx | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| PP-OCRv6_rec_small.onnx | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |
| ch_ppocr_mobile_v2.0_cls_mobile.onnx | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

Hashes and original model/license provenance come from
`product_eval/fixtures/tatr_rapidocr_word_lock.json`. Preserve those third-party
license notices when distributing assets. No TATR or table weights are needed.
The fixture also identifies the previously verified complete wheel closure.
Per-page product checks verify model bytes and package versions, not the entire
installed package payload. Full runtime provenance verification remains a
deployment/provisioning step using that existing locked verifier.

## Isolation and limits

Each page runs in its own interpreter with `-I -B`, a private temporary directory,
an allowlisted environment and no inherited API keys, proxy settings or provider
configuration. Input is a lossless RGB PNG, tied to the result by hash and size.
Models use four CPU intra-operation threads, one inter-operation thread and only
CPUExecutionProvider. The recognition line-score threshold is pinned at 0.5.

Model files are hashed before loading, all model paths are explicit, and the
RapidOCR downloader is disabled. A Python audit hook denies networking and child
process events during third-party import and inference. This is defense in depth,
not an OS security sandbox; native extensions remain trusted local software.
Standard-library platform detection is primed before enabling the process guard
because Python 3.11 can run the local Windows `ver` command for platform discovery.

The parent monitors the worker and descendants every 50 ms, terminates the tree
on timeout or excessive sampled RSS, and discards raw stdout/stderr. RSS sampling
is not a hard kernel allocation limit: a process can briefly exceed the threshold
between samples. Temporary raster/result files are removed on exit; the caller
stores returned provenance. Results are capped at 16 MiB, 10,000 lines and two
million text characters. Input PNGs are capped at 64 MiB.

## Validation

Run `python -m pytest idpo/tests/test_product_rapid_ocr.py`. The normal suite tests
source/model/provider mismatches, geometry and text offsets, configuration bounds,
secret-free environment construction, real timeout/descendant cleanup and real
memory-limit termination. It never contacts a provider.

For the optional real OCR synthetic test, set `TEST_RAPIDOCR_PYTHON` to the separate
verified interpreter and `TEST_RAPIDOCR_FONT` to a local TrueType font. It recognizes
two generated text lines and rejects a blank page; no benchmark documents or gold
are loaded. Product wiring and end-to-end development evaluation must pass before
considering a default change. The prior two-receipt text replay is insufficient
evidence for changing that default, especially for linked table rows.
