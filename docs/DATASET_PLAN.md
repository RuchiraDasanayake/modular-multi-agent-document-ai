# Product evaluation datasets and split discipline

Status: active product plan, 12 October 2026. The [system contract](SYSTEM_CONTRACT.md)
describes the implemented runtime; [productization gates](PRODUCTIZATION_PLAN.md)
define promotion. The accepted-paper evidence and the later internal October
study remain separate from the product results below.

## What the current data can establish

| Cohort | Locked role | Labels and limit |
| --- | --- | --- |
| [VRDU](https://github.com/google-research-datasets/vrdu) | 2,000 distinct public PDFs, 500 ad-buy and 1,500 registration, for repeatable execution and paired quality gates. Source and gold hashes are in the [v8 report](evaluations/VRDU_2000_NO_MODEL_V8_PROVENANCE.md). | Field and linked-row gold; only two families. The no-model v8 gate had 4.2423% strict schema F1 and zero linked rows, so its successful execution is not a general extraction claim. |
| [CORD v2](https://github.com/clovaai/cord) | Creator test Parquet frozen to 60 development receipts and 40 reserved receipts. Source/split hashes and CC BY 4.0 attribution are in the [CORD slice](evaluations/CORD_SECONDARY_SLICE.md). | Receipt totals, menu rows, text boxes and geometry. Tune candidate components on the 60 development sources only. The 40 reserved sources are for one final locked evaluation after choices freeze; do not use them for prompts, examples, routing thresholds or error inspection during selection. |
| Ten-case internal research pack | Preserve canonical-runtime regression only. | Small and partly synthetic; never use it as product accuracy evidence. |

The historical October CORD-100 result used a different CORD validation split,
known receipt fields, pipeline and scorer. It cannot be pooled with the product
CORD test split or described as automatic schema discovery. Public documents
used in pilots remain public; private team documents require a separate data
rights and labeling decision before provider calls.

## Next coverage, without moving the holdout

1. Freeze a **mixed-format, adjudicated development set** for PDF, image,
   DOCX, XLSX, PPTX, HTML and EML before treating the native-format path as validated. Use real,
   rights-cleared files with useful scalar and repeated fields, source regions
   or explicit no-geometry markers, failures and ambiguous cases. Select by
   source hash before inspecting candidate results. The product now parses the five native formats in review-only
   mode with explicit resource bounds and source locators; synthetic tests are not real-document quality evidence.
2. Add independent structured datasets only after verifying exact source
   revisions and use rights. [DocILE](https://github.com/rossumai/docile)
   supplies field-localization and line-item grouping evaluation, but its
   official download requires an access token; the MIT code license must not
   be assumed to cover document redistribution. Its predeclared labels make
   it a known-schema cross-check, not a direct test of arbitrary AI schemas.
   The creator's [CORD v2 card](https://huggingface.co/datasets/naver-clova-ix/cord-v2)
   lists 800 train, 100 validation and 100 test receipts under CC BY 4.0; this
   host currently holds only the 100-test Parquet, so a broader local gate
   needs a separately frozen download and fresh source-hash overlap check.
   [XFUND](https://github.com/doc-analysis/XFUND) adds seven-language form
   relations but is CC BY-NC-SA 4.0, and the original
   [FUNSD](https://github.com/crcresearch/FUNSD) has 199 forms for
   non-commercial research/education. Neither is a default commercial product
   corpus, and neither supplies Office/email documents. Dataset code licenses
   must not be mistaken for source-document rights.
3. Maintain source-disjoint induction examples, development scores and a final
   holdout. Any generated schema/recipe is versioned and reviewed. Do not pass
   gold field names, values or reviewer corrections for a scored document into
   that document's model prompt. Count model errors and unsupported inputs in
   the original denominator.
4. After **every substantive extraction implementation**, run at least 2,000
   distinct raw-source extractions with frozen parser/model versions and verify
   the source hashes, all receipts, failure denominator and budget. Add a
   disjoint diverse holdout; 2,000 VRDU PDFs alone cannot prove arbitrary
   document-type quality. Avoid rerunning the reserved CORD 40 while tuning.

## Metrics required for a promotion decision

Report per family and overall: schema field meaning/type and repeated grouping;
exact typed scalar precision/recall; exact linked-cell and complete-row
precision/recall; page/quote/box evidence correctness; critical false
acceptances; abstentions and failures; reviewer corrections and active minutes;
wall/CPU/GPU, peak memory, provider tokens and priced cost per correctly
released document. A recognition-only OCR score, valid JSON, or a successful
2,000-document process exit does not satisfy these metrics. Retain both raw
candidate and corrected human result so review never rewrites machine history.

Every report must name the creator source, license, revision, cohort and gold
hashes, raw output location/hash, code commit, runtime/model hashes, selection
rule, leakage controls and scoring limitations. This is the same standard used
by the existing [v8 execution gate](evaluations/VRDU_2000_NO_MODEL_V8_PROVENANCE.md)
and [CORD OCR result](evaluations/CORD_DEVELOPMENT_TEXT_BOX_OCR_RESULT_20261012.md).
