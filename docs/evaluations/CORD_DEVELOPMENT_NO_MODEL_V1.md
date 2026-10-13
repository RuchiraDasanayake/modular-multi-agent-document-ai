# CORD v2 development receipts: no-model product baseline

**Run completed 12 October 2026.** This is a separate 60-image receipt diagnostic,
not part of the 2,000-source VRDU gate. The [source and rights receipt](CORD_SECONDARY_SLICE.md)
pins the creator-hosted CORD v2 revision, original test parquet, image hashes,
positive-only label mapping, and source-only 60/40 split. Only
`input_development` was passed to the runner. The 40 reserved receipts were not
processed by this workflow.

## Frozen run

| Item | Value |
| --- | --- |
| Product commit | `c04be830b3e038d16022595b6f0d9f3de561f388` (no tracked dirty files at start) |
| Run ID | `cord_v2_development_v1` |
| Local run | `E:\DocAI-Benchmarks\runtime\product_runs\cord_v2_development_v1` |
| Input | `E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\input_development` |
| Model/provider | None; `model_configured=false`, zero model calls and SDK attempts |
| OCR | Tesseract `eng`, `psm6_single_initial_quality_retry`, at most 8 retry candidates, 30 s call and 120 s page budgets |
| Tesseract executable SHA256 | `c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420` |
| `eng.traineddata` SHA256 | `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` |
| Candidate JSONL SHA256 | `065c7190d51bdbe24043e197e3bb04d9298292c0f67f2d9bad722d1e57a962cf` |

The run used `python -m idpo.cli process-auto --input
E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\input_development --run-id
cord_v2_development_v1` with `IDPO_DATA_DIR=E:\DocAI-Benchmarks\runtime`
and the pinned `TESSERACT_CMD`/`TESSDATA_PREFIX` paths under
`E:\DocAI-Benchmarks\tools\Tesseract-OCR`. It completed with exit code 0.
The separate execution verifier also exited 0 with `--min-unique 60`.

## Source and quality accounting

| Measure | Result |
| --- | ---: |
| Distinct verified source hashes / candidate outputs / missing | 60 / 60 / 0 |
| Repeated source outputs | 0 |
| `needs_review` / `processed` / `failed` / `unsupported` | 60 / 0 / 0 / 0 |
| Documents with nonempty OCR page text | 60 / 60 |
| OCR text characters across 60 pages | 11,869 |
| Documents with any proposed schema fields | 16 / 60 |
| Proposed fields / linked columns | 31 / 0 |

The no-model path produced some scalar proposals, but none used the eight
field IDs in the CORD gold mapping. The observed zero recall is therefore
also a schema-discovery failure for this receipt family. Nonempty OCR text
does not establish that its recognition or reading order was correct.

## Published positive-only exact recall

The dedicated scorer exited 0 after verifying the 60 development image hashes.
It compares raw strings and the published menu row ordinals. A proposed value
pending human review is counted separately from an accepted extraction.

| Published positive unit | Annotated | Exact proposed | Exact accepted |
| --- | ---: | ---: | ---: |
| Summary values | 195 | 0 | 0 |
| Linked menu cells | 458 | 0 | 0 |
| Complete menu rows | 157 | 0 | 0 |

Every mapped positive was `not_proposed`: `total_amount` 58,
`cash_amount` 38, `change_amount` 33, `subtotal_amount` 40,
`tax_amount` 26, `item_name` 162, `item_price` 157, and
`item_quantity` 139. No human review was performed for this run.
CORD v2 removes merchant and payment labels, and this projection includes
only five summary keys and three menu columns. False positives, true
negatives, precision, schema F1, and OCR evidence accuracy are undefined here.
These numbers are not official CORD parsing scores and do not measure
arbitrary-document accuracy.

## Runtime and resource observations

The run receipt records **604,423.466 ms wall time** for 60 sequential
documents; summed document durations were 604,373.257 ms. Per-document
latency was 9,830.605 ms median and 19,447.004 ms at the nearest-rank 95th
percentile (minimum 703.858 ms, maximum 25,732.048 ms). Worker-process CPU
time was 146,546.875 ms. Its accounting excludes Tesseract subprocesses,
so it is not total host CPU time. Worker RSS was 77,103,104 bytes at start
and 83,005,440 bytes at end; these boundary snapshots are not peak memory.
API, compute, and total dollar costs are unknown, not zero. Zero model calls
means no model-provider charge was incurred by this run.

The verifier report is
`E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\development-execution-report.json`
(SHA256 `405507e9b2151b480751a6719c0fb30e51395266de5a60f5ef1425553a21f96b`).
The positive-only scorer report is
`E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\development-positive-recall-report.json`
(SHA256 `03249263bb2e5756672805daca1d49d41c9f906315a8132f0884a7e19098beda`).
Images, labels, sidecars, and reports stay outside Git.
