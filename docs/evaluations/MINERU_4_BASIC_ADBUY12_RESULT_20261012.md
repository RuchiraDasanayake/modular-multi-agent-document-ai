# MinerU 4.0.9 Basic local table diagnostic on public VRDU ad-buy PDFs

**Decision: retain as a bounded parser candidate; do not integrate into product extraction yet.**
On the same 12 source-locked PDFs and the same unlabeled table scorer used for
[Docling and pdfplumber](VRDU_ADBUY12_TABLE_PARSER_COMPARISON_20261012.md),
MinerU Basic recovered **6/219 complete gold rows with exact cell text**.
That is three more than Docling's 3/219, but still 97.3% of gold rows missed.
It recovered fewer exact cell strings than Docling. The candidate ran locally
with no configured cloud inference, passed the resource guard, and did not
change the product extractor. The accepted paper and 2,000-document product
gate are unaffected.

## Frozen setup and observed backend

- The [selection](../../product_eval/fixtures/vrdu_ad_buy_table12.jsonl) is
  the 12 lowest source-hash-ranked public ad-buy PDFs, committed before any
  parser run, SHA256 `b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d`.
  The cohort/gold locks remain `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`
  and `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
  All 12 raw PDF hashes were rechecked. They contain 28 pages and **219 gold
  linked rows / 808 linked cells**, including two PDFs with zero native text
  and 32 rows / 84 cells.
- The [MinerU 4.0.9 release](https://github.com/opendatalab/MinerU/releases/tag/mineru-4.0.9-released)
  resolves to source commit `fa91b100f5350731064bd267008ca44302589417`.
  The isolated PyPI `mineru-4.0.9-py3-none-any.whl` SHA256 is
  `4d9c0e28e2d4b132a9ca245a64dd970a721380b0f6d3dd0615e50ff12328a260`.
  The official [`MinerU-4_models_onnx` revision](https://huggingface.co/opendatalab/MinerU-4_models_onnx/tree/358310b4f64b95f9fefc372ad899356e4111f376)
  is `358310b4f64b95f9fefc372ad899356e4111f376`, with 16 files totaling
  858,220,651 bytes. Every downloaded byte is bound by the
  [model manifest](../../product_eval/fixtures/mineru_4_0_9_onnx_models.json),
  SHA256 `2cb238eafa541d2de051caa3bbcfa8e6c2c6d048b614863f11c7458fb0bd5933`.
  The isolated `pip check` and `mineru-kit models verify --tier basic
  --small-backend onnx` passed.
- The [diagnostic runner](../../product_eval/mineru_table_diagnostic.py)
  SHA256 at execution was `7e146d4e78cf7e8c0904c804078da729eea201d16122bbfb831fa8c8034091ef`.
  It invoked stateless `mineru-kit parse` per PDF with `--tier basic`,
  `--format middle_json`, `--ocr-mode auto`, and image analysis disabled.
  `MINERU_MODEL_SOURCE=local`, `MINERU_MODEL_SMALL_BACKEND=onnx`,
  `MINERU_TABLE_DEVICE=cpu`, and `HF_HUB_OFFLINE=1` were set. No `--remote`
  service or VLM was configured. [MinerU's pinned tier guide](https://github.com/opendatalab/MinerU/blob/mineru-4.0.9-released/docs/en/usage/tiers.md)
  identifies Basic as local small-model OCR/formula/table parsing without a VLM.
- Every saved MiddleJson identified `tier=basic`; eight PDFs reported final
  `parse_mode=txt` and four `parse_mode=ocr`. All 12 conversion logs recorded
  the table models with `requested=cpu` and `CPUExecutionProvider`; none
  recorded model download or parser error. The two zero-native-text PDFs
  used OCR. The four OCR-mode PDFs include two with some native text.

The raw run is
`E:\DocAI-Benchmarks\mineru-4.0.9-basic\adbuy12-run-v1\run.json`,
SHA256 `7d82fb3356d59fdab036469bea92456cc0af3ba7509684fa289a67672e785b7b`.
Each raw MiddleJson has a SHA256-bound conversion receipt and local CLI log
outside Git. The environment freeze and config remain beside the run,
SHA256s `b0bec42a1be49063c886ae5536819776eed81433ccc0fa372a1035fd7031aa71`
and `75857e6d722749f6bc4374c1b3b865930681e56ad69d7d56573168e8baa02d2a`.
Independently reloading the frozen selection, all 12 raw outputs, receipts,
and gold with `score_saved` reproduced the saved score exactly.

## Paired scores over all 12 PDFs

All parsers retain every gold row in the denominator. The comparison reads
table cells without business field IDs. NFKC/casefold/whitespace normalization
is the only text normalization. A complete row requires all gold cell strings
to appear in **one** parser row, with no parser row reused across gold rows.
The exact-row measure additionally requires separate exact cell strings,
though a parser row may contain extra cells. Spanning HTML cells belong to
their starting row and are not duplicated into later rows.

| Measure | MinerU Basic | Docling TableFormer | pdfplumber `text` |
| --- | ---: | ---: | ---: |
| Successful document parses | 12/12 | 12/12 | 12/12 |
| Tables / nonempty rows / nonempty cells | 61 / 620 / 2,692 | 50 / 428 / 3,030 | 24 / 1,165 / 8,548 |
| Gold string occurs within any parser cell | 769/808 | 675/808 | 529/808 |
| Gold cell exactly equals a parser cell, one-to-one by text | 211/808 | **279/808** | 237/808 |
| Gold within-row pairs co-located by substring | 689/1,219 | **801/1,219** | 439/1,219 |
| Complete rows co-located by substring, one-to-one | 21/219 | **71/219** | 10/219 |
| Complete rows with exact cells, one-to-one | **6/219** | 3/219 | 4/219 |
| Parser row exactly equals gold cell multiset | 0/219 | 0/219 | 0/219 |
| Sum of per-document processing time | 227.73 s | 537.95 s | 10.12 s |

MinerU's three additional exact rows over Docling came from two PDFs: two
additional rows in the first hash-ranked PDF and one in an image-only PDF.
Neither parser recovered exact linked rows from most PDFs. This tiny paired
difference is not evidence that MinerU will generalize better. MinerU's high
substring presence coexists with poor row grouping and exact text: it cannot
be treated as accepted linked extraction.

| Source split | MinerU exact cells | MinerU complete substring rows | MinerU complete exact rows | Docling complete exact rows |
| --- | ---: | ---: | ---: | ---: |
| 10 native-text PDFs, 187 rows / 724 cells | 181/724 | 18/187 | 5/187 | 3/187 |
| 2 image-only PDFs, 32 rows / 84 cells | 30/84 | 3/32 | 1/32 | 0/32 |

`pdfplumber` has no OCR and found no tables in the two image-only PDFs. Its
10.12-second timing therefore reflects a cheaper, narrower task. MinerU and
Docling used different OCR/layout/model stacks and prior runs occurred at
different times on the same host; observed run time is a system comparison,
not an isolated kernel benchmark.

## Resource gate and limits

The first 3-page smoke passed in **26.86 s**, with a sampled parser process-tree
peak RSS of **1,309,429,760 bytes** and minimum host-available memory of
**8,437,428,224 bytes**. This met the predeclared continuation limits of
less than 6 GiB RSS and more than 3 GiB available. The runner then completed
the remaining 11 sequentially. Every child was capped at 360 seconds,
8 GiB process-tree RSS, and 2 GiB minimum host-available memory. All 12
passed. Whole-run wall time was **229.31 s**; median document time 15.63 s,
maximum 35.05 s; maximum sampled child process-tree RSS **1,878,482,944 bytes**
(1.75 GiB), minimum sampled host-available memory **7,644,409,856 bytes**
(7.12 GiB). The process-tree RSS sum conservatively counts shared pages in
multiple processes if any; these are observed host figures, not deployment
capacity guarantees. There was no provider API charge; electricity,
hardware amortization, and reviewer labor were not priced.

MinerU's [source license](https://github.com/opendatalab/MinerU/blob/mineru-4.0.9-released/LICENSE.md)
is Apache-2.0-based **with additional terms**: attribution for a third-party
online service and a separate commercial license above stated scale/revenue
thresholds. These terms must be considered before any product integration;
the code is not plain Apache-2.0. Individual model asset terms should be
checked before distribution.

This is a public, 12-document, single-family development diagnostic. It
does not identify ad-buy column roles, establish per-cell source boxes,
extract typed business values, resolve evidence, measure HITL time, or test
arbitrary formats. A table route would need much stronger linked-row
accuracy and adjudicated value/evidence results before promotion. Any
substantive product change would require a fresh >=2,000-distinct-document
execution gate plus a diverse reserved holdout; this parser-only study does
not satisfy that gate.
