# CORD development text-box recognition diagnostic

**Status, 12 October 2026:** crop manifest frozen; OCR inference and scores pending the active 2,000-document product gate and coordination with the separate CORD extraction run. This is a recognition-only diagnostic, not a product OCR or extraction result.

## Question and locked scope

Does PP-OCRv6 small recognize the *same creator-annotated CORD text boxes* more accurately than pinned Tesseract on the 60 source-locked development receipts? Every engine receives the identical saved PNG crop. Neither performs text detection, page reading order, field assignment, or table reconstruction. The 40 reserved receipts are excluded from source selection, prompt/model/threshold choice, and inference. This experiment cannot estimate full-page OCR precision, recall, CER, WER, or downstream extraction quality.

[CORD's creator annotation format](https://github.com/clovaai/cord/blob/master/README.md) supplies `valid_line.words[].text` and four-point `quad` coordinates. The frozen development slice contains 796 semantic `valid_line` entries and 1,389 nonblank annotated text boxes across 60 receipts. Twenty box texts contain internal spaces, so the unit is an **annotated text box**, not necessarily a lexical word. `valid_line` covers menu, subtotal, and total categories; creator `dontcare` and repeating symbols are outside this diagnostic. The [source split and rights receipt](CORD_SECONDARY_SLICE.md) records CORD v2's CC BY 4.0 attribution and the source-only development/reserved separation.

| Frozen input | SHA-256 |
| --- | --- |
| Creator CORD v2 test Parquet, revision `7f0115a4b758a71d6473b8d085751692da2fef98` | `51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7` |
| `cohort_development.jsonl` | `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a` |
| 1,389-crop `manifest.jsonl` | `03eeddf3526b28031582460419b3c1ed27bcacc285e194d193b19110fbb610f5` |

The manifest and crop PNGs are outside Git at `E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\word-ocr-dev-v1`. Each row carries the original PNG SHA-256, stable Parquet row, line/word indices, original quad, gold text, crop path, and crop SHA-256. The runner rechecks every crop and rejects paths outside that frozen directory. The creator Parquet has one row group, so Arrow decompresses its annotation column, but code parses and uses only the 60 development row indices. It does not read the 40 reserved PNGs or parse their annotations.

## Fixed crop and recognizers

CORD quad points are interpreted as top-left, top-right, bottom-right, bottom-left. [Pillow's QUAD transform](https://pillow.readthedocs.io/en/stable/reference/ImageTransform.html) receives them in its required top-left, bottom-left, bottom-right, top-right order. The deterministic crop uses bicubic rectification, a two-pixel white margin, RGB conversion, and 3× Lanczos upscale. One source quad extends one pixel outside the image; outside fill is white. The saved crop hash proves both engines saw the same pixels, though annotation bounds may themselves omit or include characters.

| Recognizer | Fixed setup |
| --- | --- |
| Tesseract | Windows 5.5.3.20260724, executable SHA `c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420`; `eng.traineddata` SHA `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`; `--oem 3 --psm 7`, `OMP_THREAD_LIMIT=4`, 15-second crop timeout. Every crop launches a separate process. |
| [RapidOCR 3.10.0](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/) / ONNX Runtime 1.23.2 | Recognition only (`use_det=False`, `use_cls=False`, `use_rec=True`), English PP-OCRv6 small ONNX recognition model SHA `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`; CPU provider, four intra-op and one inter-op threads, CUDA/DirectML off. The model loads lazily on the first real crop, whose latency stays in raw output. |

The [RapidOCR model attribution](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/) and [PaddlePaddle PP-OCRv6 small recognition model card](https://huggingface.co/PaddlePaddle/PP-OCRv6_small_rec_onnx) identify Apache-2.0 for this model. Redistribution still requires the upstream license and notices. The isolated RapidOCR environment is `E:\DocAI-Benchmarks\tools\rapidocr-3.10-venv`; no API or private PDF is involved.

## Predeclared measures

Unicode NFKC normalization and whitespace collapse are applied to both gold and prediction; **case and punctuation remain significant**. Per-box exact match and code-point Levenshtein character error rate (CER) are legitimate because each annotation supplies a string for its fixed crop. CER can exceed 1 when the recognizer inserts characters. Report micro totals and the unweighted mean of per-receipt rates, plus all four paired exact outcomes (both correct, Tesseract only, RapidOCR only, neither). Failures and timeouts yield empty predictions and remain in the denominator. A 10,000-replicate paired bootstrap resamples the 60 receipts as clusters with seed `20261012`; its 95% interval is for the fixed development slice only.

Raw per-crop records include both predictions, failures, confidence where supplied, and elapsed milliseconds. The summary gives p50/p95 and total sequential crop time for each engine. Tesseract's per-crop process launch and RapidOCR's first-call model load make these timings a reproducible diagnostic, **not** a deployment throughput or price comparison. Neither engine uses page detection here; no claim about OCR polygons, source evidence, row order, HITL workload, or total system cost follows from a better crop CER.

The separate [30-page PP-OCRv6 scan pilot](RAPIDOCR_PPOCRV6_THIRTY_SCAN_PILOT.md#windows-gpu-feasibility-and-next-cost-comparison-read-only-plan) specifies a post-gate, full-pipeline CPU-versus-Windows-CUDA comparison using the exact detector and recognizer ONNX weights. This CORD recognition-only crop experiment does not substitute for that local CPU/GPU cost test.

## Reproduction

Run from the repository root. Preparation requires Python 3.13 with PyArrow 22.0.0 and Pillow 12.1.0. The local PyArrow bundle is compiled for Python 3.13 and cannot load in the Python 3.11 RapidOCR environment. The following preparation has already completed and must use a new output directory if repeated:

```powershell
$env:PYTHONPATH='E:\DocAI-Benchmarks\tools\cord-parquet-runtime'
python -m product_eval.cord_word_ocr_diagnostic prepare `
  --stage-root 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a' `
  --parquet 'E:\DocAI-Benchmarks\cord-v2-7f0115a\data\test-00000-of-00001-9c204eb3f4e11791.parquet' `
  --output-dir 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\word-ocr-dev-v1'
```

Only after the active product gate finishes and the CORD jobs are sequenced, run the paired OCR pass in the isolated Python 3.11 environment. The runner refuses existing output paths; a one-hour wall budget leaves an explicitly incomplete raw file rather than issuing a partial score:

```powershell
& 'E:\DocAI-Benchmarks\tools\rapidocr-3.10-venv\Scripts\python.exe' `
  -m product_eval.cord_word_ocr_diagnostic run `
  --manifest 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\word-ocr-dev-v1\manifest.jsonl' `
  --output 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\word-ocr-dev-v1\paired_raw.jsonl' `
  --summary 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\word-ocr-dev-v1\paired_summary.json' `
  --tesseract 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tesseract.exe' `
  --tessdata 'E:\DocAI-Benchmarks\tools\Tesseract-OCR\tessdata' `
  --max-wall-seconds 3600
```

Before choosing a production OCR route, verify any crop-level gain on source-locked scanned pages with **detection plus recognition**, source geometry and linked-row scoring, review decisions, and measured cost per correct extraction. The 40 reserved CORD receipts should not be used for iterative OCR selection.
