# Parser and OCR options, 12 October 2026

**Decision:** retain the pinned native-PDF/Tesseract path as the measured control.
The paired **PP-OCRv6 small** challenge found better scan-text coverage on 30 selected
public pages, at higher CPU time and memory; it has not demonstrated better
end-to-end extraction. Use structured table/layout engines only for pages that need
them. Model/vendor benchmark scores do not establish field or linked-row accuracy
on our documents.

## Why the control remains useful

The [v5 VRDU gate](../evaluations/VRDU_2000_NO_MODEL_V5.md) processed 2,000
distinct PDFs from two families. Pinned Tesseract produced text on all 831 OCR pages,
including 35 PDFs previously called unsupported because the executable was missing.
Yet strict schema F1 was 4.245%, accepted-value F1 was 0%, and proposed linked
cells/rows were 0/0 against 30,133/7,234 gold. OCR quality is not the only, or even
the demonstrated dominant, failure. The [local 12-PDF oracle-schema text-model
diagnostic](../evaluations/LOCAL_QWEN_ORACLE_SCHEMA_VRDU_TWELVE_PILOT.json) got
11/98 exact scalar values and no exact linked rows even when supplied gold field
names/types. Replacing OCR cannot alone solve schema induction, row linking, or
release policy.

The [v6 bounded-OCR gate](../evaluations/VRDU_2000_NO_MODEL_V6.md) also processed
2,000 unique PDFs with the same 4.245% schema F1, zero accepted-value F1, and zero
linked cells; no natural page hit its configured timeout. The [30-page PP-OCRv6 small
pilot](../evaluations/RAPIDOCR_PPOCRV6_THIRTY_SCAN_PILOT.md) exposed 121/146
page-local gold scalar strings versus 107/146 in the selected v5 Tesseract text,
but its warm CPU p50 was 5.50 s per page versus 1.59 s for a direct Tesseract
single pass. This selected-set string-presence proxy is not CER, field F1, or a
production latency comparison. It warrants a selective fallback challenge with
an independent adjudicated set, not automatic replacement.

The isolated Docling 2.137.0 ten-PDF pilot (`E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\parser-pilot\recommendation.md`)
converted all ten and produced bounded provenance boxes, but native-PDF CPU median
was 30.17 s against 0.119 s for the frozen native intake on seven timed PDFs. One
scanned table collapsed into one noisy cell. Its scalar phrase-presence comparison
is a parser diagnostic, not extraction F1; the earlier baseline had missing OCR, so
that scan comparison is not against corrected v5. This is evidence for selective
routing and for testing table cells directly, not a default Docling migration.

## Ranked experiments for this Windows CPU + RTX 3060 Ti 8 GB host

| Priority | Candidate and exact role | Evidence and constraint | Licensing status |
| --- | --- | --- | --- |
| 1 | **PaddleOCR 3.7.0, PP-OCRv6 small/medium** as an OCR adapter on scanned or suspect pages; keep native PDF text. | [Official release](https://github.com/PaddlePaddle/PaddleOCR/releases/tag/v3.7.0) introduced tiny/small/medium; the [general OCR pipeline](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md) emits text and geometry and supports CPU/GPU. The vendor's aggregate detection/recognition gains over v5 are a reason to test, not our expected gain. Check actual CPU and GPU wheels/driver on this host. | [Code Apache-2.0](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE); official [medium detection](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_det_safetensors) and [recognition](https://huggingface.co/PaddlePaddle/PP-OCRv6_medium_rec_safetensors) cards each say Apache-2.0. Pin and audit the exact downloaded pair, runtime, transitive notices. |
| 2 | **PP-StructureV3**, configured down to fit, on preselected table crops/pages; compare directly with Docling TableFormer. | Its [output contract](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md) has `cell_box_list`, table HTML, OCR text/scores/boxes and JSON/overlay exports. The [published default profile](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-StructureV3/PP-StructureV3.en.md) peaks at 13.97 GB on T4 and 18.54 GB on A10, so **default GPU configuration exceeds 8 GB**. Disable irrelevant modules and choose smaller models or CPU; verify actual peak and row quality. | PaddleOCR code Apache-2.0; each selected layout/table/OCR model weight needs a recorded license, hash, and notice before shipping. |
| 3 | **Docling 2.137.0** as a selective layout/table parser and broad-format adapter, never a silent replacement for the cheap native path. | The [current release](https://github.com/docling-project/docling/releases/tag/v2.137.0) is already the pinned pilot version. Its [document model](https://docling-project.github.io/docling/reference/docling_document/) exposes table cell text, row/column offsets, spans, bounding boxes, and page provenance; [inputs](https://docling-project.github.io/docling/usage/supported_formats/) include PDF, Office, images and others. The local scanned-table failure and 30.17 s CPU median demand a new row-level comparison. | [Code MIT](https://github.com/docling-project/docling/blob/main/LICENSE); [Docling model bundle](https://huggingface.co/docling-project/docling-models) declares CDLA-Permissive-2.0 and Apache-2.0, [Heron](https://huggingface.co/docling-project/docling-layout-heron) Apache-2.0. Verify exact weight and optional OCR dependencies. |
| 4 | **MinerU 4.0.9 `basic`**, then `standard` only if hardware allows, as a separate full-parser comparator. | [4.0 release](https://github.com/opendatalab/MinerU/releases/tag/mineru-4.0.0-released) provides CPU-capable small-model `basic`, native `flash`, VLM-assisted `standard`, and Windows base-package ONNX/llama.cpp Vulkan. [4.0.9](https://github.com/opendatalab/MinerU/releases/tag/mineru-4.0.9-released) is current; [versioned intermediate JSON](https://github.com/opendatalab/MinerU/blob/master/docs/en/reference/output_files.md) can be adapted to our provenance contract. Confirm exact 8 GB peak, per-cell coordinates, and model-bundle rights. | **Custom MinerU Open Source License**, not unmodified Apache: [service attribution, revenue/MAU thresholds, termination](https://github.com/opendatalab/MinerU/blob/master/LICENSE.md). Its [1.2B VLM card](https://huggingface.co/opendatalab/MinerU2.5-Pro-2605-1.2B) says Apache-2.0; the 4.0 ONNX bundle card does not state a license, so inspect individual artifacts before distribution. |
| 5 | **PaddleOCR-VL 1.6** or **Qwen3-VL-4B-Instruct GGUF** as bounded visual fallbacks on cases where OCR/table candidates fail. | [PaddleOCR-VL 1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6) is a 0.9B class document parser with page-level JSON/Markdown via its official pipeline; its transformers example is only element-level. The pinned [Qwen3-VL-4B Q4](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF) weights and projector ran locally on this 8 GB card, but the [two-document v2 diagnostic](../evaluations/LOCAL_QWEN3_VL_TWO_DOC_V2_PROMPT_PILOT.json) matched only 1/19 gold scalars, falsely accepted one, and proposed no linked cells. The second reply truncated at its 3,000-token cap. No production-quality visual fallback has been shown. | Both official model cards state Apache-2.0. Pin full runtime/weight hashes and test visual grounding; generated text alone cannot be treated as pixel evidence. |

**Do not ship Surya 2 as a default dependency under the present product goal.** Its
[code is Apache-2.0 but model weights carry a separate license](https://github.com/datalab-to/surya)
that restricts use by entities over revenue/funding thresholds **and products competing
with the licensor** ([exact terms](https://github.com/datalab-to/surya/blob/master/MODEL_LICENSE)).
Its [0.22.1 release](https://github.com/datalab-to/surya/releases/tag/v0.22.1)
and row/column/cell geometry make it a technically relevant comparator, but this is
not a clean permissive dependency for a document-AI product. Legal review would be
required before product use. This is a license reading, not legal advice.

## Predeclared comparison and stop rules

1. **Pin and normalize first.** Record source SHA, engine/revision/weights SHA,
   renderer, DPI, rotation, language setting, CPU/GPU mode, and source-page mapping.
   Convert each candidate into `ParsedDocument` page text, spans/boxes, table cells,
   row/column IDs and provenance without discarding raw output. The same rasterized
   pages and fixed extractor/prompt budgets feed paired OCR comparisons. Exclude
   private sources from external calls. An OCR confidence or string match is not
   proof of semantic field correctness.
2. **12-document engineering smoke.** Freeze a source-hash manifest before running:
   both VRDU families, native-text and scanned pages, at least four table-bearing
   and two rotated/noisy cases; previously seen pilot files may be used here. Run
   Tesseract control and PP-OCRv6 small/medium on every relevant scan page, and
   Docling/PP-StructureV3/MinerU basic on relevant layout/table pages. A candidate
   proceeds only if 12/12 return explicit success/failure, no crash/OOM or silent
   page loss occurs, and page/box overlays map back to the original image. Reject
   a GPU configuration if its measured peak leaves less than 0.5 GiB free on
   the shared 8 GiB card; retry a named small/CPU
   configuration rather than silently changing models. Report cold/warm latency,
   peak host RAM/VRAM, model downloads, retries, text coverage and table cells.
3. **50-document adjudicated comparison.** Freeze an untouched manifest and gold
   before candidates run: 25 VRDU PDFs with native/scan and both families, and 25
   legally usable mixed documents across invoice/receipt/form/letter/report,
   image/PDF/DOCX where available. Keep format and family counts explicit and
   report any unavailable stratum rather than substituting after outcomes. Human
   adjudicators mark scan transcription, table grids/headers/spans, row links,
   critical scalar values and pixel evidence. Score scan CER/WER, text coverage,
   cell text and geometry, row-link F1, exact typed field F1, critical false
   acceptance, evidence overlap, perfect-document rate, abstention, reviewer
   minutes, p50/p95 latency, CPU/GPU time and actual API spend. Report paired
   bootstrap intervals by family/scan/layout and individual failures. Advance
   OCRv6 only if scan CER falls by at least 10% relative **and** the same
   downstream route has no new erroneous critical-value proposals or false
   acceptances; advance a table parser only if row-link F1 gains at least 10
   percentage points with no worse critical-value proposals, false acceptances,
   or evidence correctness. If the same
   extractor cannot consume cells, report parser-only results and do not claim
   end-to-end benefit.
4. **2,000 unique-document implementation gate.** After integrating any winner,
   run the fixed [VRDU 2,000-source cohort](../evaluations/VRDU_2000_NO_MODEL_V5.md)
   through a clean, pinned commit and same gold/scorer, with 2,000 distinct source
   hashes and zero missing outputs. Preserve the baseline route for a paired
   comparison. Report all scan/table strata, exact schema/value/cell/row metrics,
   evidence validation, status/review/unsupported/failure counts, timeout rate,
   latency/memory, engine calls and compute/API/reviewer cost. Any regression in
   critical false acceptance, source evidence, or completeness blocks promotion.
   The two-family VRDU gate is a volume/regression check; the mixed 50-doc set is
   needed for generalization and is too small for a universal-accuracy claim.

The first engineering change justified by this research is an **isolated OCR adapter
experiment**, not a new agent loop or microservice. Keep page and table provenance
in a versioned internal contract so that the OCR winner can change without changing
review decisions or source evidence semantics.
