# Unmeasured component reuse: one next parser pilot

Status: documentation-only research, 12 October 2026. No assets were
downloaded, no model was run, and no product route changed. Compare on correct
linked rows, inspectable cell evidence and measured total cost, not a vendor's
Markdown or OCR score. The existing [reuse decision](../architecture/FRONTIER_REUSE_DECISION_2026-10-12.md)
already rejects automatic promotion of Docling's standard PDF parser, MinerU 4
Basic and PaddleOCR-VL 1.6 on their frozen 12-PDF results; the
[native mixed-format diagnostic](MIXED_FORMAT_NATIVE_DEV_RESULT_20261012.md)
already recovered 45/45 synthetic table cells with 45/45 native locators.

## Two credible unmeasured boundaries

| Boundary | Current official capability and deployment | Gap against this product |
| --- | --- | --- |
| **Granite-Docling 258M**, selectively parse hard PDF/image pages | IBM's [model card](https://huggingface.co/ibm-granite/granite-docling-258M) declares Apache-2.0 weights, English, 258M parameters and a 515 MB safetensors file. It supports full-page conversion to DocTags and a targeted table-to-OTSL instruction; [Docling's VLM pipeline](https://github.com/docling-project/docling/blob/main/docs/usage/vision_models.md) can convert the response into `DoclingDocument` with structured tables. [Docling code](https://github.com/docling-project/docling/blob/main/LICENSE) is MIT. The [Python SDK path](https://github.com/docling-project/docling/blob/main/docling/.agents/skills/docling/references/python-sdk.md) uses local PyTorch/Transformers on CPU/GPU; the [GPU guide](https://github.com/docling-project/docling/blob/main/docs/usage/gpu.md) describes Linux vLLM, while MLX is for Apple. Use the local Windows Transformers path on this host and measure actual 8 GB GPU fit. | PDF/page image is the input; it is not a DOCX/XLSX/PPTX/HTML/EML native parser. The model supplies **document structure**, not an arbitrary business schema or validated field values. DocTags contain location tokens and Docling's document type can carry table-cell boxes, but the card does **not** guarantee a non-null, correct box for every generated cell. Check raw DocTags, parsed row/column spans and each cell's `bbox` against the page image. No exact per-value quote or business row link can be inferred from a table-region box. The card's FinTabNet TEDS result is a reason to test, not evidence of our ad-buy row accuracy. |
| **Xberg** (active successor to Kreuzberg v4), broad intake alternative | The [official repository](https://github.com/xberg-io/xberg) lists an MIT Rust core, Windows x64 binaries/Python binding, CPU-first operation, PDF, Office, image, HTML and email support. Its [type reference](https://docs.xberg.io/reference/types/) exposes table grids with row/column indices, spans and **optional** cell boxes; its table `bounding_box` uses PDF points with bottom-left origin for PDF/OCR-PDF but top-left pixels for standalone images. Optional layout/OCR engines add their own weights and runtime/rights checks. [Structured extraction](https://docs.xberg.io/guides/llm-integration/) passes document text and a **provided** JSON Schema to a local or hosted LLM; it is neither free by default nor automatic schema induction. | No measured advantage over the 45/45 native-library synthetic control, and the optional `GridCell.bbox` is not proof that each format/route populates it. Source-native sheet/cell, slide/shape, DOM and MIME locators must survive normalization. Cross-page table fragments are [not linked by `table_id`](https://docs.xberg.io/reference/types/). Pin one Xberg release and engine profile before any comparison; a broad feature list does not justify replacing format-specific parsers or the verifier. |

Kreuzberg v4 is now [LTS with best-effort fixes only through 2026](https://github.com/kreuzberg-dev/kreuzberg-lts); the active broad-format line is Xberg. Treat the two as distinct versioned dependencies. For this product, Xberg is a later **real mixed-format** comparator after a rights-cleared corpus exists, not the next extraction pilot.

## Recommended next pilot: Granite-Docling parser only

1. Reuse the **same 12 source-locked ad-buy PDFs and 219 gold linked rows** as
   the [PaddleOCR-VL result](PADDLEOCR_VL16_ADBUY12_RESULT_20261012.md).
   Commit an isolated harness, fixed PDFium raster settings, model and
   `transformers`/Docling revisions, full weight hashes, memory limits and
   scorer hash **before** inference. Do not select crops using gold boxes. Run
   the official full-page DocTags instruction first, with deterministic
   decoding and bounded output tokens. Retain all raw DocTags, parsed
   `DoclingDocument` JSON and failures.
2. Score exactly the existing parser metrics: complete gold-cell sets in one
   parser row (extra cells allowed), strict exact-multiset rows, exact gold-cell
   matches, and per-document/per-scan denominators. Also count non-null and
   image-overlapping **per-cell** boxes, correct page/coordinate transforms,
   truncated generations, unsupported pages, cold/warm latency, host RAM and
   VRAM. Do not count a table box as a cell box or a parser cell as a mapped
   business field.
3. Against the measured PaddleOCR-VL 1.6 control (**14/219 permissive rows,
   0/219 strict rows, 475/808 exact cells, no per-cell boxes**), require at
   least **one strict complete row**, more than 14 permissive rows, and
   verified cell-level boxes on the improved rows before allocating a
   downstream extraction pilot. These are only pilot-advancement conditions;
   they are far below product-quality release criteria. If the Windows local
   path breaches the repo's 2 GiB host-free or 0.5 GiB GPU-free floor, stop
   and report all 12 sources in the denominator; do not silently offload to
   cloud or change models.
4. Only after that parser gate, adapt its cells to the inactive
   `ParsedDocument` contract and challenge the **same** approved-schema
   extractor/reviewer path. Require exact field IDs, linked rows, value
   evidence and review-adjusted cost before product integration. Any
   substantive extraction change still triggers a fresh 2,000-distinct-source
   execution gate plus a diverse holdout.

The immediate integration decision is **no product change**. Granite-Docling
has a small, permissively licensed local model and a clear source-locked test;
its cell evidence and business-row utility remain unmeasured.
