# CORD v2 receipt slice: pinned sources and development baseline

**Status, 12 October 2026:** the creator-hosted test parquet was downloaded,
verified, and converted to a local source cohort with separate gold labels.
The 60-image development split has been processed by the current no-model
product path. Its [separate evaluation report](CORD_DEVELOPMENT_NO_MODEL_V1.md)
records zero exact recall on the mapped positive labels. The 40-image reserved
split remains unprocessed by this workflow.

## Source and rights

[NAVER CLOVA's CORD project](https://github.com/clovaai/cord) links to its
[CORD v2 dataset](https://huggingface.co/datasets/naver-clova-ix/cord-v2) and
licenses the work under [CC BY 4.0](https://github.com/clovaai/cord/blob/master/LICENSE-CC-BY).
Attribution: Park, Shin, Lee, Lee, Surh, Seo, and Lee, *CORD: A Consolidated
Receipt Dataset for Post-OCR Parsing*, Document Intelligence Workshop at
NeurIPS, 2019; NAVER CLOVA. The public repository says v2 corrected labels.
It also says `store_info` and `payment_info` classes were removed for legal
reasons. This slice therefore does not invent merchant or vendor labels.

The creator-hosted dataset is public and could be downloaded with
`token=False`, without accepting a registration gate. Its license permits use
with attribution; keep the images and gold outside Git to avoid repository
bloat and unnecessary redistribution of receipt contents. Review any public
release of images for privacy and attribution needs.

| Pin | Value |
| --- | --- |
| Dataset | `naver-clova-ix/cord-v2` |
| Exact dataset revision | `7f0115a4b758a71d6473b8d085751692da2fef98` |
| File | `data/test-00000-of-00001-9c204eb3f4e11791.parquet` |
| Parquet bytes | `234202795` |
| Parquet SHA256 | `51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7` |
| `cohort.jsonl` SHA256 | `e55bfed44bcba19236f70696092bb7fad96c60f573b947d2ab0c6afbd1e13f31` |
| `gold.jsonl` SHA256 | `dcd7a2cf0a1b42441655b4e0c2412e73aed334c9d95a266e71de09f930efec78` |

The creator's original test split has 100 images. All 100 rows were selected
in pinned file order, using only image bytes. The adapter hashes each original
embedded PNG, rejects duplicate content, and verifies every staged image.
The local stage is `E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a`. Its
`input_development` and `input_reserved` directories contain only images;
`gold*.jsonl` and `metadata.json` remain outside the runner input directories.
The metadata records hashes for every generated JSONL file. Nothing from the
raw dataset or generated gold is committed here.

## Development and reserved split

The adapter fixes a **source-only** split before it reads `ground_truth`. It
groups receipt images into connected components when 64-bit difference hashes
have Hamming distance at most 12 and aspect ratios differ by at most 0.05.
Components are ranked by SHA256 under a fixed seed; whole components enter
the reserved portion until it reaches 40 images. For this pin there are 92
components, four containing multiple images, with a maximum component size of
five. This yields 60 development and 40 reserved receipts. No image pair
meeting this visual rule crosses the split.

| Derived split | Sources | Positive summary values | Positive menu cells | Complete menu rows |
| --- | ---: | ---: | ---: | ---: |
| Development | 60 | 195 | 458 | 157 |
| Reserved | 40 | 127 | 259 | 89 |
| Total | 100 | 322 | 717 | 246 |

This is a derived split *within CORD's published test set*, not an official
CORD score. CORD v2 lacks merchant/vendor IDs in the published `gt_parse`;
the visual rule cannot prove vendor or all-layout disjointness. Some receipts
may have been seen in historical exploratory work or model pretraining. Do
not call the 40 images an untouched holdout. Keep them out of prompt, policy,
threshold, and model selection from now on; report development and reserved
results separately.

## Gold and metric scope

Only source string values, with surrounding whitespace trimmed, are mapped
from five `gt_parse` summary keys:
`total.total_price`, `total.cashprice`, `total.changeprice`,
`sub_total.subtotal_price`, and `sub_total.tax_price`. Their product IDs are
`total_amount`, `cash_amount`, `change_amount`, `subtotal_amount`, and
`tax_amount`. Menu `nm`, `cnt`, and `price` become `item_name`,
`item_quantity`, and `item_price`, preserving the published menu row ordinal.
There are 251 published menu rows and 246 with both a name and price. Four
non-scalar summary annotations are excluded. Nested menu `sub` entries and
all other CORD classes are outside this gold.

The dedicated scorer reports exact raw-string **positive recall** for
summary values, menu cells, and complete rows. A complete row requires all
its annotated name, price, and any annotated quantity at the same row
ordinal. Exact proposed and exact accepted counts are separate; a candidate
pending human review is not an accepted extraction. Missing candidate
documents stay in the denominator, and staged image SHA256 values are
verified before scoring. Field IDs must match the mapped IDs above, so schema
discovery errors count as misses. Formatting changes count as non-exact even
if semantically equivalent. Precision, true negatives, schema F1, and OCR
evidence accuracy are **undefined** for this partial positive-only mapping.
CORD publishes boxes and word text, but this product gold does not assert OCR
character-offset evidence spans. These derived scores must not be compared
with official CORD parsing scores.

## Reproduce and evaluate

Install the optional reader dependencies in an isolated environment. The
staging code requires `pyarrow` and Pillow; `huggingface_hub` is needed only
for downloading. From the repository root:

```powershell
python -m pip install huggingface_hub pyarrow==22.0.0 Pillow

python -c "from huggingface_hub import hf_hub_download; print(hf_hub_download(repo_id='naver-clova-ix/cord-v2', repo_type='dataset', filename='data/test-00000-of-00001-9c204eb3f4e11791.parquet', revision='7f0115a4b758a71d6473b8d085751692da2fef98', local_dir=r'E:\DocAI-Benchmarks\cord-v2-7f0115a', token=False))"

python -m product_eval.datasets.cord_test `
  --parquet 'E:\DocAI-Benchmarks\cord-v2-7f0115a\data\test-00000-of-00001-9c204eb3f4e11791.parquet' `
  --output-dir 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a'
```

The adapter refuses an existing output directory or a parquet with a
different name, hash, schema, row count, or test version. Use a new directory
when reproducing an existing stage. Compare its `metadata.json` hashes to
the receipt above before a run.

The development run used the image-only input directory and pinned local
Tesseract configuration documented in its evaluation report. To repeat it,
verify every source was processed, including failed or unsupported documents,
then run the separate scorer:

```powershell
python -m idpo.cli process-auto `
  --input 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\input_development' `
  --run-id cord_v2_development_v1

python -m product_eval.verify_execution `
  'PATH_TO_IDPO_DATA_DIR\product_runs\cord_v2_development_v1' `
  --min-unique 60 --report 'PATH_TO_DEVELOPMENT_EXECUTION_REPORT.json'

python -m product_eval.datasets.cord_positive_score `
  --cohort 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\cohort_development.jsonl' `
  --gold 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\gold_development.jsonl' `
  --candidate 'PATH_TO_IDPO_DATA_DIR\product_runs\cord_v2_development_v1\candidates.jsonl' `
  --report 'PATH_TO_DEVELOPMENT_RECALL_REPORT.json'
```

Use `input_reserved`, `cohort_reserved.jsonl`, `gold_reserved.jsonl`, and
`--min-unique 40` for one final reserved run only after development choices
are fixed. Record both run IDs, product commit, model/provider, OCR
configuration, candidate hashes, execution receipts, and review decisions.
If a model is configured, `process-auto` also needs matching `--model` and
`--api-base-url` arguments and its API key environment variable; keep that
configuration the same across both splits. The default `process-auto` path
uses the local baseline.
