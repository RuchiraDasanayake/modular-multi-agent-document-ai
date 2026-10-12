# Mixed VRDU + CORD v2 train 2,000-source gate protocol

Status: **builder implemented; full gate not run**. This is an evaluation-only
development cohort. It is not the ICTAR paper's dataset or an untouched product
holdout. The touched surface is `research_evidence`; its primary action is
`keep` until a sealed run and separate quality analysis exist.

## Frozen sources and selection

- CORD v2 is the [NAVER CLOVA creator-hosted dataset](https://huggingface.co/datasets/naver-clova-ix/cord-v2/blob/7f0115a4b758a71d6473b8d085751692da2fef98/README.md)
  at commit `7f0115a4b758a71d6473b8d085751692da2fef98`, whose dataset card
  states CC-BY-4.0. The builder accepts **only** its four `data/train-*` Parquet
  files, verifies their exact names, byte sizes, and LFS SHA-256s, and requires
  800 rows with embedded PNG bytes and `meta.split=train`, `version=2.0.0`.
  The pins are in [`mixed_vrdu_cord_train.py`](../../product_eval/datasets/mixed_vrdu_cord_train.py).
  Neither validation nor test Parquet is read or staged.
- The existing [CORD test adapter](../../product_eval/datasets/cord_test.py)
  pins all 100 local test source receipts, including the 40 reserved holdout.
  The builder checks the test cohort receipt SHA-256, source bytes, creator
  revision, and test-file pin before selecting train images. Any train image
  with the same raw SHA-256 as a test image is excluded. This does **not**
  establish visual, vendor, or raw-image disjointness from validation, whose
  images are not available to this builder.
- The [VRDU cohort](../../product_eval/datasets/vrdu.py) is pinned to creator
  commit `04a4df7ac5cc694e51c48115c03fe428f0e240cc` and the existing
  2,000-PDF cohort/gold SHA-256s. The builder checks the complete frozen
  receipts, selects sources, checks the gold join, then rehashes each selected
  PDF before and after staging. CORD train images overlapping a VRDU source
  by raw SHA are excluded.

Selection uses image bytes and frozen source receipts **before** reading either
dataset's annotations. It retains each eligible distinct train image once, up to 1,999,
then fills to exactly 2,000 with a fixed SHA rank over the pinned VRDU PDF
cohort. Fewer than one eligible CORD image, insufficient distinct sources,
unexpected splits/files, missing bytes, changed hashes, or incomplete gold
fail the build. Staged files retain filenames needed by product `doc_id` and
are distributed into eight bounded shards. A temporary directory is renamed
into place only after all files and gold pass validation; an existing output
directory is never overwritten.

## Gold and scoring boundary

CORD train gold reuses the [positive-only mapping](../../product_eval/datasets/cord_test.py):
raw-string totals, cash, change, subtotal and tax when present, plus ordered
`menu.nm`, `cnt`, and `price` cells with shared zero-based row ordinals. Missing,
non-scalar, and other CORD classes are **unscored**, not negative labels.
Image/word boxes are not product OCR text spans. VRDU gold keeps its original
published field IDs and derived linked rows. No labels influence source choice.

The bundle writes `cohort.jsonl`, `gold.jsonl`, CORD-only cohort/gold files,
`metadata.json`, and `shards/shard_00` through `shard_07`. The first two and
the shard paths match `product_eval.run_gate` inputs. A completed run's
2,000-source receipt measures execution and integrity. Its combined strict
precision/F1 mixes VRDU's derived gold with CORD's positive-only gold and is
**not** a CORD precision estimate or arbitrary-document quality claim. Score
CORD positive scalar, linked-cell, and complete-row recall separately with
[`mixed_cord_positive.py`](../../product_eval/datasets/mixed_cord_positive.py),
which verifies the completed gate's 2,000-source count, subprocess exits,
product run manifests, raw source bytes, sealed result files, and exact
cohort/candidate join. It recomputes the full-cohort quality report before
filtering candidates to CORD train IDs and calling the existing
[`cord_positive_score.py`](../../product_eval/datasets/cord_positive_score.py).
The
current `run_gate` family report inherits VRDU-specific interpretation text;
do not quote that text as a CORD finding. No model, review-minute, or dollar
cost conclusion follows from this no-model gate.

## Reproduction sequence

Build from a **complete** local train download into a new directory. The
reader requires PyArrow and Pillow; use the repository's frozen requirements
for the final build. It records the installed reader versions in
`metadata.json`:

```powershell
python -m product_eval.datasets.mixed_vrdu_cord_train `
  --cord-train-root 'I:\DocAI-Benchmarks\cord-v2-train-7f0115a' `
  --vrdu-cohort-dir 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7' `
  --cord-test-cohort-dir 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a' `
  --output-dir 'I:\DocAI-Benchmarks\mixed-vrdu-cord-train-gate-v1'
```

After reviewing `metadata.json`, run from a clean product checkout with a new
gate ID, a working English Tesseract preflight, and a new report directory:

```powershell
$bundle = 'I:\DocAI-Benchmarks\mixed-vrdu-cord-train-gate-v1'
$shards = Get-ChildItem -LiteralPath "$bundle\shards" -Directory | Sort-Object Name | Select-Object -ExpandProperty FullName
python -m product_eval.run_gate $shards `
  --gold "$bundle\gold.jsonl" --cohort "$bundle\cohort.jsonl" `
  --data-dir 'E:\DocAI-Benchmarks\runtime' `
  --report-dir 'I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1' `
  --gate-id mixed_vrdu_cord_train_v1 --min-unique 2000 --workers 4
```

Only after that gate completes and its receipt is sealed:

```powershell
python -m product_eval.datasets.mixed_cord_positive `
  --bundle-dir 'I:\DocAI-Benchmarks\mixed-vrdu-cord-train-gate-v1' `
  --gate-report-dir 'I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1' `
  --output 'I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1\cord-positive.json'
```

The builder has **not** run on the full train Parquet download, and no mixed
2,000-source product run or CORD train accuracy result exists yet. The
acceptance receipt must verify 2,000 distinct original-source hashes, exact
gold/candidate IDs, source-byte integrity, and no automatic releases before
any quality or cost discussion.
