# Secondary FUNSD form slice: frozen inputs, no extraction result yet

**Status, 12 October 2026:** the source and sparse gold adapter is implemented
and staged locally. The 30 forms have **not** been processed by the new product
runtime as part of this receipt. No extraction accuracy is claimed here.

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

[CORD v2](https://github.com/clovaai/cord) is a future receipt slice candidate;
the creator's [dataset page](https://huggingface.co/datasets/naver-clova-ix/cord-v2)
labels it CC BY 4.0. The current repository's CORD benchmark packs contain
derived labels but all 50 holdout image paths are missing, and no CORD parquet
exists at `datasets/external/cord-v2/data`. Those packs cannot currently be
used to substantiate a new extraction run. A CORD acquisition should pin the
creator dataset revision and raw validation parquet SHA256, retain attribution,
and stage only the needed images outside this repository.

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

## Reproduce and execute

Use a new output directory and the same 50 FUNSD test images as the committed
source lock; a different downloaded version will fail fast rather than silently
change the cohort. From the repository root:

```powershell
python -m product_eval.datasets.funsd_remainder `
  --image-root 'E:\Research Project\Code\IDPO\datasets\FUNSD\testing_data\images' `
  --output-dir 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1'

# After the separate 2,000-source implementation gate, with Tesseract configured:
python -m idpo.cli process-auto `
  --input 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\input' `
  --run-id funsd_remainder_30_v1

python -m product_eval.verify_execution `
  'PATH_TO_IDPO_DATA_DIR\product_runs\funsd_remainder_30_v1' `
  --min-unique 30 --report 'PATH_TO_EXECUTION_REPORT.json'

python -m product_eval.datasets.funsd_positive_score `
  --cohort 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\cohort.jsonl' `
  --gold 'E:\DocAI-Benchmarks\funsd-test-remainder-30-v1\gold.jsonl' `
  --candidate 'PATH_TO_IDPO_DATA_DIR\product_runs\funsd_remainder_30_v1\candidates.jsonl' `
  --report 'PATH_TO_POSITIVE_RECALL_REPORT.json'
```

Record the product Git commit, model/provider configuration, OCR executable and
traineddata hashes, candidate JSONL hash, execution receipt, and all 30 statuses.
Do not merge this 30-document score into the 2,000-source VRDU gate or use it
to claim arbitrary-document accuracy. The next independent real receipt slice
needs freshly pinned CORD inputs or a team-owned, adjudicated document set.
