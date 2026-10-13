# PaddleOCR-VL 1.6 full-pipeline table pilot on public VRDU ad-buy PDFs

**Decision: no product parser promotion.** The pinned, local full pipeline
completed all 12 frozen PDFs and improved the paired parser-only complete-row
score to **14/219** from MinerU Basic's 6/219, Docling's 3/219 and
pdfplumber `text`'s 4/219. This still misses 205 of 219 gold rows. **Zero
parser rows exactly equal the gold cell multiset**, and the output has no
cell-level source coordinates or word/token links. It is a useful research
result, not a verified field extractor or a basis for the 2,000-document
product gate.

## Frozen run and reproducibility

The [protocol](PADDLEOCR_VL16_ADBUY12_PROTOCOL_20261012.md),
[model lock](../../product_eval/fixtures/paddleocr_vl_16_models.json),
[runtime lock](../../product_eval/fixtures/paddleocr_vl_16_runtime.json),
[guarded runner](../../product_eval/paddleocr_vl_pilot.py), worker and scorer
were committed as `ae670aa` **before** the first inference. The exact 12
source PDFs were selected without gold by
[`vrdu_ad_buy_table12.jsonl`](../../product_eval/fixtures/vrdu_ad_buy_table12.jsonl),
SHA256 `b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d`.
All source SHA256s passed verification before the run and again during
independent rescoring. The cohort SHA256 is
`98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`;
gold SHA256 is
`8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
The 12 PDFs comprise 28 pages, including two PDFs with zero native text.

The [official PaddleOCR-VL pipeline](https://github.com/PaddlePaddle/PaddleOCR/blob/v3.7.0/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)
ran `PP-DocLayoutV3` on PaddlePaddle CPU 3.3.0, then the official
PaddleOCR-VL 1.6 0.9B GGUF and projector through one local CUDA llama.cpp
server slot. The isolated Python 3.11 environment used PaddleOCR 3.7.0 and
PaddleX 3.7.2; `pip check` and `PaddleOCRVL` import passed. The 102-package
runtime closure, three core wheel hashes and five official model artifact
hashes are in the locks. The GGUF revision is
`511b09642bb324401f15f97cc23bc67e8f0a291d` and the layout revision is
`241f8bdfc77a7c7bee915a5057aaee58c235a8d3`.
The server build was `b11425-e117148a4`; its props confirmed the pinned
model, vision support, 8192-token context and one slot before prediction.

Raw outputs are outside Git at
`E:\DocAI-Benchmarks\paddleocr-vl16-adbuy12-v1`. The run-lock JSON SHA256
is `a25f1aa6c5458c7e495dfc1c731b5c83c44fb2e63b7fc0762b14de9b86653a62`;
the complete `run.json` SHA256 is
`5291d6361759f59237484fc1bbc359237ebc7fb0b41a3d96e6302144cf243e3a`.
Every premerge and merged page JSON is SHA256-bound to its conversion receipt.
Independent reloading of the frozen source selection, gold, all receipts
and saved pages reproduced both scores **exactly**. The model server was
stopped after the run.

## Paired parser-only scores

The shared scorer applies NFKC, case folding and whitespace collapse only.
The headline complete-row score requires all gold cells with exact text in
one **distinct** parser row and allows extra parser cells. It does not
attribute cells to business field IDs. The stricter entire-row score
disallows extra cells. These are parser table metrics; they are not
comparable to NuExtract's oracle-schema value extraction rows.

| Measure, all 12 PDFs | PaddleOCR-VL 1.6 full pipeline | MinerU Basic | Docling TableFormer | pdfplumber `text` |
| --- | ---: | ---: | ---: | ---: |
| Documents converted | 12/12 | 12/12 | 12/12 | 12/12 |
| Valid tables / nonempty rows / nonempty cells | 72 / 766 / 4,680 | 61 / 620 / 2,692 | 50 / 428 / 3,030 | 24 / 1,165 / 8,548 |
| Gold string occurs within any parser cell | 723/808 | 769/808 | 675/808 | 529/808 |
| Gold cell exactly equals a parser cell, one-to-one by text | **475/808** | 211/808 | 279/808 | 237/808 |
| Complete gold cell set in one parser row, one-to-one | **14/219** | 6/219 | 3/219 | 4/219 |
| Entire parser row exactly equals gold cell multiset | **0/219** | 0/219 | 0/219 | 0/219 |
| Sum of per-document conversion time | 359.67 s | 227.73 s | 537.95 s | 10.12 s |

The Paddle result is stronger on exact cell text and complete exact-cell
sets, but MinerU retains more gold cell strings somewhere in table cells.
Paddle emitted 766 nonempty parser rows and 4,680 nonempty parser cells
against 219 gold rows and 808 gold cells. The 14/219 score is **6.4%**;
475/808 exact cells is **58.8%**. The apparent 723/808 surface recall
does not establish row, field or source correctness. The primary merged
HTML score and separately predeclared premerge score were identical. No
cross-page merged continuation appeared in this cohort.

The two image-only PDFs contributed **6/32** complete exact-cell rows
and **38/84** exact cells; the ten native-text PDFs contributed **8/187**
rows and **437/724** cells. One scan supplied all six recovered scan rows.
This uneven distribution is another reason not to extrapolate from 12 PDFs.

| Source ID prefix | Input | Pages | Complete exact-cell rows | Exact cells | Conversion time |
| --- | --- | ---: | ---: | ---: | ---: |
| `c9603389` | native text | 3 | 2/32 | 99/154 | 41.2 s |
| `e2e3a1f8` | image-only | 1 | 0/10 | 16/40 | 17.9 s |
| `1bf0c61d` | native text | 1 | 1/6 | 18/27 | 15.8 s |
| `b83458ce` | native text | 6 | 2/30 | 80/144 | 68.5 s |
| `19410b18` | native text | 1 | 1/11 | 10/20 | 17.9 s |
| `480ff756` | image-only | 3 | 6/22 | 22/44 | 32.7 s |
| `2bbf89c7` | native text | 2 | 0/8 | 23/32 | 24.3 s |
| `46a4deba` | native text | 3 | 0/55 | 109/165 | 39.0 s |
| `82b30ab8` | native text | 4 | 0/33 | 65/132 | 43.3 s |
| `bb6694b6` | native text | 2 | 2/4 | 9/12 | 26.3 s |
| `37acb119` | native text | 1 | 0/6 | 18/30 | 15.8 s |
| `f61eb3be` | native text | 1 | 0/2 | 6/8 | 16.9 s |

The prior [Docling/pdfplumber comparison](VRDU_ADBUY12_TABLE_PARSER_COMPARISON_20261012.md)
and [MinerU result](MINERU_4_BASIC_ADBUY12_RESULT_20261012.md) used the same
source lock and scorer. They ran at different times and with different
hardware and OCR capabilities. The pdfplumber profile has no OCR and found
no tables on the two scans. The timing row is a whole-system cost comparison,
not a model-kernel speed benchmark.

## Saved source evidence and cell-localization limit

The first real three-page smoke confirmed saved JSON has zero-based
`page_index`, `model_settings.use_layout_detection=true`, a
`parsing_res_list`, and table `block_content` containing HTML under
`format_block_content=false`. Across all 28 merged pages, 72 recognized
table blocks contained valid HTML and 72 syntactically valid `block_bbox`
rectangles; none were malformed. Each table block has block/order/group
IDs and a **table-region** box. `layout_det_res` contains 386 labeled
region detections with score and four-coordinate rectangle, 82 labeled
`table`. These are region detections, not table-cell boxes.

A read-only audit of all 28 merged and 28 premerge page JSON files found
no `table_res_list`, OCR word/token list, per-cell coordinates or cell-to-
source links. The 72 HTML tables contain 772 `<tr>` and 6,797 `<td>` tags
including empty cells. Their only HTML attributes are `colspan` (284)
and `rowspan` (18); there are no coordinate or token-reference attributes.
The saved JSON can defensibly attach a recognized table to its page region.
It **cannot** attach each extracted cell to a source box without additional
evidence. A future adapter would need separately measured OCR/token boxes,
alignment to HTML cells and validation. Dividing a table box into an
inferred grid would create coordinates unsupported by this output.

## Runtime, limits and decision

The guarded run attempted and completed 12/12 PDFs, with zero invalid page
outputs and zero resource stops. Whole-run elapsed time was **366.65 s**;
median PDF conversion time **25.30 s**, maximum **68.48 s**. Maximum
sampled server-plus-worker process-tree RSS was **3.91 GiB**; minimum
host available memory **4.17 GiB**; minimum free GPU VRAM **4,509 MiB**.
The first three-page smoke finished in 41.17 s, produced six valid table
blocks, and passed the stricter smoke thresholds. No cloud API was used, so
there was no API charge; GPU hardware, electricity and operational cost
were not priced. This local result does not prove a CPU-only deployment fit.

Do not replace the product parser or run the 2,000-source gate on this
candidate now. It recovers too few complete linked rows, offers no
cell-level grounding, and has only been evaluated on one small public
document family. Further research could compare specialist table
structure/cell-box models or a separate OCR alignment stage on a disjoint
development set, with quality and runtime measured before integration.
