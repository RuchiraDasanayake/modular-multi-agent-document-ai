# Secondary FUNSD form slice: frozen inputs and no-model extraction result

**Status, 12 October 2026:** the source and sparse gold adapter is staged locally,
and the 30 forms have been processed once by the no-model `process-auto` path.
All 30 execution receipts verified. The sparse gold supports positive recall only;
it does not support precision, false-acceptance, or arbitrary-document accuracy claims.

## Why this slice

The VRDU 2,000-document gate contains two related form families. A separate
set of scanned business forms exposes different OCR, layout, and field naming
failures. The 20 forms in `datasets/funsd_pack_20.json` were used in the old
October research comparison, so this slice takes the **other 30** test image
filenames. Selection is by set difference before reading their annotations.
Some of these 30 may have appeared in older exploratory runs; this is a
secondary development slice, **not an untouched holdout**.

The repository contains 50 FUNSD test annotations but no test images. A local
older workspace contains all 50 matching test images and annotations at
`E:\Research Project\Code\IDPO\datasets\FUNSD\testing_data`. All 50
checked-in annotations parse to the same JSON objects as that workspace's
copies, although their byte formatting differs. The creator's original test
archive was not available for byte comparison. The committed
`product_eval/datasets/funsd_test_remainder_lock.json` pins every selected raw
image and checked-in annotation SHA256, and the adapter refuses changed
sources. This proves repeatability of these local bytes, not chain of custody
to an original creator archive.

## Rights and scope

The [FUNSD creator terms](https://guillaumejaume.github.io/FUNSD/work/) limit
dataset use to non-commercial research and education and warn that the source
images have separate copyright considerations. Keep the image cohort outside
the application repository, use it only for local research evaluation, and
do not send it to a cloud model or use it for commercial training or a public
product demo without a separate rights review. The code and SHA256 lock contain
no dataset images or answer text. The repository already tracks 50 FUNSD test
annotation JSON files; that existing redistribution also needs a rights review
before a commercial release.

The independent [CORD v2 receipt slice](CORD_SECONDARY_SLICE.md) now pins a
creator-hosted test parquet and stages its images outside Git. The old CORD
benchmark packs still have missing local image paths and cannot substantiate
a new extraction run.

## Frozen local receipt

| Item | Count or SHA256 |
| --- | --- |
| Test images present in older local workspace | 50 |
| Historical FUNSD-20 images excluded | 20 |
| Selected, distinct image bytes | 30 |
| Documents with at least one linked target answer | 18 |
| Documents without linked target answer, execution only | 12 |
| Positive values | 26: date 14, recipient 7, sender 5 |
| Source lock | `f34d6611f88f7e666a42c1559cb20f9c40b2109ba1207cf108b25fb5f8c5ddb7` |
| `cohort.jsonl` | `ca76235cad31b00a756a7008d24ca0d7d36c6f6b8b349de5d0693b59855984e6` |
| `gold.jsonl` | `0fef99a83c7ac21959e443eb51c49654421b9bc41a4d1a1e93c6d4d0aeb6148d` |
| `exclusions.jsonl` | `22a48abc7e0f55afb369123fb64032fd07630b4578b739eb22893b32096b5e29` |

The staged directory is
`E:\DocAI-Benchmarks\funsd-test-remainder-30-v1`. It has an `input` directory
with the 30 images, `cohort.jsonl`, `gold.jsonl`, `exclusions.jsonl`, and
`metadata.json`. Each cohort row points to the staged image, its SHA256 and
the product runtime's stable document ID. The gold and labels are separate
from `input` so the extraction runner sees no answers.

## Gold interpretation

Only published FUNSD `question`→`answer` links whose question text is exactly
`DATE`, `TO`, or `FROM` are mapped to `date`, `recipient`, and `sender`. Values
remain the raw annotated strings. A missing link is **unknown**, not proof a
field is absent. Twelve sources have no linked answer for these targets and
are omitted from `gold.jsonl`, while remaining in `cohort.jsonl` and any
throughput/failure count. No gold OCR spans are asserted because FUNSD has
image boxes rather than the product scorer's character-offset evidence.

The standard `product_eval` JSONL contract accepts the 18 gold records, but
global schema F1, value precision, false-accept rates and evidence scores would
be misleading with these partial labels. The dedicated scorer reports only
exact raw-string **positive recall** for accepted values, plus exact proposed
values pending review. It verifies every staged image hash and reports missing
candidate documents. Its precision and absent-field metrics are intentionally
undefined. The date fields are raw strings, so formatting changes count as
non-exact even if a human would judge the date equivalent.

## Completed no-model run

`python -m idpo.cli process-auto` completed as
`E:\DocAI-Benchmarks\runtime\product_runs\funsd_remainder_30_v1`, with
`TESSERACT_CMD` and `TESSDATA_PREFIX` set to Tesseract `v5.5.3.20260724`.
The executable SHA-256 was
`c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420` and
`eng.traineddata` SHA-256 was
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
The repository HEAD at report time was `90f26fc1e0751092bea0d93c6ae883c406549bcb`;
the most recent product OCR implementation in that checkout was the bounded
Tesseract change used in the [VRDU v6 gate](VRDU_2000_NO_MODEL_V6.md).
No model was configured and no cloud call was made. This is a secondary
development-slice diagnostic, not a new 2,000-source implementation gate.

| Measure | Result |
| --- | ---: |
| Distinct input hashes / candidate outputs / missing | 30 / 30 / 0 |
| `needs_review` / `failed` / `unsupported` / released | 30 / 0 / 0 / 0 |
| Documents with published positive target links | 18 |
| Published positive `date` / `recipient` / `sender` values | 14 / 7 / 5 |
| Exact accepted positive values | **0 / 26** |
| Exact values pending review | **1 / 26** |
| Target values not proposed at all | 22 / 26 |
| Target values proposed with wrong or no value | 3 / 26 |

The one exact pending value is a `date`. No `recipient` or `sender` positive
value was proposed under its mapped field name. A missing FUNSD target link
remains unknown, so these counts must not be converted into false-positive
rates or schema F1. The execution verifier found 30 distinct verified source
hashes and no duplicate outputs. Sum of document durations was 223,668.935 ms;
this sum is neither wall time nor a deployment throughput measurement.

The candidate JSONL SHA-256 is
`4a9b8c77deb91feb6a19073171a640087965d66dfcc1dc843cbfe6dec99caaed`.
The local execution-report and positive-recall-report SHA-256 values are
`d78a40b0006aa60e11b44de64f8725ae62767639b1f2649639266fe3b92dc48d`
and `f39f321823c5b2028e6da7e449bab643795d665980007a299bc0b9d15e1bb957`.
These reports remain outside Git beside the staged images. This run confirms
that the baseline extractor fails badly on a third scanned-form family; it
does not test the PP-OCRv6 challenger or a model-backed schema path.

## Reproduce and execute

Use a new output directory and the same 50 FUNSD test images as the committed
source lock; a different downloaded version will fail fast rather than silently
change the cohort. From the repository root:

```powershell
python -m product_eval.datasets.funsd_remainder `
  --image-root 'E:\Research Project\Code\IDPO\datasets\FUNSD\testing_data\images' `
  --output-dir 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1'

# With the pinned Tesseract installation configured:
python -m idpo.cli process-auto `
  --input 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\input' `
  --run-id funsd_remainder_30_v1

python -m product_eval.verify_execution `
  'E:\DocAI-Benchmarks\runtime\product_runs\funsd_remainder_30_v1' `
  --min-unique 30 --report 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\execution-report.json'

python -m product_eval.datasets.funsd_positive_score `
  --cohort 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\cohort.jsonl' `
  --gold 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\gold.jsonl' `
  --candidate 'E:\DocAI-Benchmarks\runtime\product_runs\funsd_remainder_30_v1\candidates.jsonl' `
  --report 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\positive-recall-report.json'
```

Do not merge this 30-document score into the 2,000-source VRDU gate or use it
to claim arbitrary-document accuracy. The CORD slice adds one separate
receipt family; broader claims still need a team-owned, adjudicated document
set with stronger split controls.
