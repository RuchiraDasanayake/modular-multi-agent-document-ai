# Public VRDU ad-buy linked-table diagnostic: Docling and pdfplumber

## Decision

Neither parser is ready to supply accepted linked-table rows to the product. On 12 source-locked public ad-buy PDFs with 219 gold linked rows and 808 gold linked cells, Docling recovered **3/219 complete rows with exact cell text**, while pdfplumber `lines` recovered **0/219** and pdfplumber `text` **4/219**. Each measure requires all gold cells in a single parser row, with no parser row reused across gold rows. These are *unlabeled* row matches: the experiment did not map parser columns to business field IDs. Even 4/219 is too weak for autonomous extraction.

The cheaper pdfplumber `text` profile is worth retaining as a research candidate for native-PDF table detection, provided its output remains untrusted until row, field, and evidence verification. It is **not** a production table adapter on this evidence. A bounded PP-StructureV3 comparison on the same frozen cohort is the next specialist test; no larger or private-document run is justified by these results.

## Frozen design and provenance

- Population: 12 lowest source-SHA-256 ad-buy-form PDFs from the frozen public VRDU cohort, selected independently of gold. Selection was committed as [`product_eval/fixtures/vrdu_ad_buy_table12.jsonl`](../../product_eval/fixtures/vrdu_ad_buy_table12.jsonl) in `90f26fc` before parser inference. Selection SHA-256: `b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d`.
- Frozen cohort SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`. Frozen gold SHA-256: `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`. Every PDF's bytes were rehashed against selection before processing. The 12 PDFs have 28 pages in total.
- Gold includes 219 linked rows and 808 nonempty linked cells. Two PDFs have zero native PDF text (32 rows, 84 cells); the other ten have 187 rows and 724 cells. These two scans remain in every denominator.
- Docling research runner: [`product_eval/docling_table_diagnostic.py`](../../product_eval/docling_table_diagnostic.py), SHA-256 `ca0c4d2eb99680a00da2442989f083d4329703296ec3d790c336c70ab92e25e7`, committed through `2387e9d`. Raw run: `E:\DocAI-Benchmarks\vrdu-tableformer-ad12-v1-20261011T2237Z`; complete marker `run.json`; score SHA-256 `5801c226edcad2ae3c1a59e0e5966b994ca9da8d7ae898b2be30f01bd539ee6c`.
- pdfplumber research runner: [`product_eval/pdfplumber_table_diagnostic.py`](../../product_eval/pdfplumber_table_diagnostic.py), SHA-256 `e72f1b21754c4d57daa6e971a66bf9273998d245976de3e5906f5f00aa72278c`. Both `lines/lines` and `text/text` settings were fixed in code before the run. Raw run: `E:\DocAI-Benchmarks\vrdu-pdfplumber-ad12-v1-20261011T2249Z`; complete marker `run.json`; score SHA-256 `d57089d9ecf59d4c3eb9e7bd5b49d9d0fea7f2b9ef55373bbd8d2be4afda2b95`.
- Raw parsed tables and conversion receipts remain outside Git. Each raw JSON file is SHA-256 bound to its receipt; saved scores were recomputed after the runs. All 12 Docling receipts and all 24 pdfplumber profile receipts match the frozen document IDs and source SHA-256 values.

## Configurations

| Parser | Fixed profile | Environment | Local licensing evidence |
|---|---|---|---|
| Docling 2.137.0 | TableFormer `ACCURATE`, cell matching on; RapidOCR 3.10.0 torch/en; `full_page` OCR for documents with <100 native text characters; CPU, four threads; max 20 pages, 2 MB, 240-second document timeout | `docling-core` 2.101.1, `docling-parse` 7.22.2, PyTorch 2.14.1, pypdfium2 5.14.0; 20 cached Docling artifacts and three RapidOCR weights rehashed before run | [Docling code MIT](https://github.com/docling-project/docling/blob/main/LICENSE); cached `docling-models` README declares CDLA-Permissive-2.0 and cached layout Heron README declares Apache-2.0; the [RapidOCR project README](https://github.com/RapidAI/RapidOCR#license) declares Apache-2.0 for code and upstream-derived model files. Individual downstream asset terms still need checking before distribution. |
| pdfplumber 0.11.10 | Native PDF only, no OCR; profile A: vertical/horizontal `lines`; profile B: vertical/horizontal `text`; other library table settings left at defaults | Isolated Python 3.11 environment; `pdfminer.six` 20260107 | [pdfplumber MIT](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt). The [official table API](https://github.com/jsvine/pdfplumber#extracting-tables) exposes row/cell text and boxes and states machine-generated PDFs are its best case. |

Docling's cached model-artifact manifest SHA-256 is `3a2c3e36a5db87d85d3952aed37f809d8c7d495dd8cfba64e65b8d622cee8241`. The TableFormer accurate weight SHA-256 is `2a7d6c924b3cd12fb99a09280ca9c33a89c5d60b93253617d2e088c1a40374d9`; the layout Heron weight is `00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c`. [Docling's pipeline options](https://docling-project.github.io/docling/reference/pipeline_options/) define the chosen TableFormer and cell-matching settings. The research runs used no cloud APIs or GPU.

## Results over all 12 PDFs

| Measure | Docling | pdfplumber `lines` | pdfplumber `text` |
|---|---:|---:|---:|
| Documents with parsed tables | 12/12 | 8/12 | 10/12 |
| Parser tables / nonempty rows / nonempty cells | 50 / 428 / 3,030 | 60 / 264 / 975 | 24 / 1,165 / 8,548 |
| Gold cell string found inside any parser cell, reuse allowed | 675/808 | 479/808 | 529/808 |
| Gold cell exactly equals parser cell text, one-to-one by text | 279/808 | 86/808 | 237/808 |
| Gold within-row cell pairs co-located by substring, reuse allowed | 801/1,219 | 218/1,219 | 439/1,219 |
| Complete gold rows co-located by substring, rows one-to-one | 71/219 | 0/219 | 10/219 |
| Complete gold rows with exact cells, rows one-to-one | **3/219** | **0/219** | **4/219** |
| Entire parser row has exactly the gold cell multiset | 0/219 | 0/219 | 0/219 |
| Sum of per-document processing durations | 537.951 s | 5.616 s | 10.124 s |

All 12 Docling conversions returned `success`, including both scans. pdfplumber produced no table on both scans; its `lines` profile also found no table on two native-text PDFs. Each pdfplumber profile processed all 12 PDFs with no exception, and no-table outcomes remain scored as zero. The pdfplumber command running both profiles finished in about 18.5 seconds of wall time. Docling's per-document time includes PDF text probing, cold model initialization, OCR where selected, conversion, and raw JSON serialization; the profiles do different work, so timing is a system cost comparison rather than a TableFormer kernel benchmark. Peak RAM and energy were not measured. Local software had no API charge; hardware cost was not estimated.

### Native text versus image-only PDFs

| Split and measure | Docling | pdfplumber `lines` | pdfplumber `text` |
|---|---:|---:|---:|
| Native-text PDFs with tables | 10/10 | 8/10 | 10/10 |
| Native-text gold cell substring presence | 643/724 | 479/724 | 529/724 |
| Native-text exact cell strings | 263/724 | 86/724 | 237/724 |
| Native-text complete substring rows | 71/187 | 0/187 | 10/187 |
| Native-text complete exact-cell rows | 3/187 | 0/187 | 4/187 |
| Image-only PDFs with tables | 2/2 | 0/2 | 0/2 |
| Image-only gold cell substring presence | 32/84 | 0/84 | 0/84 |
| Image-only exact cell strings | 16/84 | 0/84 | 0/84 |
| Image-only complete exact-cell rows | 0/32 | 0/32 | 0/32 |

## Interpretation and limits

Cell presence is only a recall-style ceiling: a string may appear in an unrelated cell or repeat across rows. Exact cell counts also do not establish correct rows. The complete-row metric enforces one parser row for each gold row and distinct parser cells for each gold value; the stricter entire-row metric also disallows extra parser cells. All comparison text was normalized with NFKC, case folding, and whitespace collapse only. Spanning Docling cells were assigned to their starting row. No fuzzy numeric, currency, or business-field alias matching was used.

The pdfplumber `text` profile emitted 1,165 nonempty rows and 8,548 cells for only 219 gold rows, so its apparent text recall includes substantial over-segmentation. Docling's 50 tables retained more cell surfaces, yet most gold rows were not linked exactly. In one scanned PDF, Docling logged that 132 of 169 PDF cells were dropped while matching a 2×2 inferred grid; its conversion still returned `success`, illustrating why conversion status alone is inadequate. The two scans together yielded no complete linked row under Docling OCR.

VRDU gold does not include page locations for linked cells, and parser output does not assign business field IDs. This test therefore measures unlabeled table-cell text and row grouping; it is **not** field accuracy, evidence grounding, end-to-end extraction F1, or an estimate for arbitrary document types. The sample is only 12 public ad-buy PDFs selected without looking at gold. No parser settings were tuned from the observed scores.

## Reproduction checks

The tests for the research runners passed (`python -m pytest product_eval/tests/test_docling_table_diagnostic.py product_eval/tests/test_pdfplumber_table_diagnostic.py -q`, 13 tests), and Ruff reported no diagnostics. Each runner supports `--check`, `--run`, and independent `--score`; `--run` refuses an existing output directory, and `--score` revalidates the frozen source selection plus raw-output receipt hashes. The complete markers identify the exact source, runner, version, profile, duration, and score hashes. Reproducing a full run requires the public VRDU corpus and pinned local model cache at the E: paths above; the JSON receipts are retained there, outside the repository.
