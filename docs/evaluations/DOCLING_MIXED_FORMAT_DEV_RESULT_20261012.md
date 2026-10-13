# Docling mixed-format converter feasibility — 12 October 2026

**Decision:** Advance `docling-slim` as a candidate normalization layer for DOCX, XLSX, HTML, and PPTX. Do not use direct EML conversion as a structured-table path. This is a five-file synthetic converter diagnostic, not a product extraction result or a reason to claim arbitrary-format support.

## Current intake boundary

The product UI's [file picker](../../frontend/src/components/idpo/job-detail-page.tsx), [upload validation](../../frontend/src/server/jobs.ts), and [runner configuration](../../frontend/runner.config.json) currently admit PDF, common raster images, TXT, and JSON. The [product-auto workflow](../../idpo/product_auto/workflow.py) has the same extension set; the [canonical inbox](../../idpo/pipeline/inbox.py) also filters to it. DOCX, XLSX, HTML, EML, and PPTX are therefore **not currently supported extraction inputs**. The converter results below do not change that boundary or imply that these formats can safely be enabled by adding extensions alone.

## Frozen protocol

- Five locally generated, rights-cleared files: DOCX, XLSX, HTML, multipart EML, and PPTX. Each source contains the same synthetic 3-row × 3-column order table; the EML has a short plain-text part and an HTML alternative containing the table. Source SHA-256 hashes are in [the fixture manifest](../../product_eval/fixtures/mixed_format_docling_v1/manifest.json); the five source files are committed beside it.
- Python 3.11.0 on Windows 10; `docling-slim[format-office,format-web,format-email]==2.138.0`, `docling-core==2.101.1`, and `psutil==7.2.2` in an isolated environment. The [full resolved package freeze](locks/docling_slim_mixed_2.138.0_py311_windows.txt) and [diagnostic script](../../product_eval/mixed_format_docling_diagnostic.py) permit a repeat run. The slim install omitted local model dependencies; `torch` was absent. Docling [lists these input formats](https://docling-project.github.io/docling/usage/supported_formats/) and [documents selective slim extras](https://github.com/docling-project/docling/blob/main/packages/docling-slim/README.md).
- Each file ran in a fresh process with only its matching `InputFormat` enabled. Hugging Face offline flags were set. Process wall time includes Python startup and imports; conversion time is the `DocumentConverter.convert` call. A 10 ms RSS sampler recorded process memory and can miss a shorter peak. No GPU or billable API was used. [Raw results](DOCLING_MIXED_FORMAT_DEV_RESULT_20261012.json) contain the recorded structure and timings.

| Source | Conversion | Table rows / cells | Exact known cells | Grid indices | Page, sheet, and region evidence | Process wall | Convert call | Sampled peak RSS |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| DOCX | success | 3 / 9 | 9 / 9 | 9 / 9 | No pages or boxes | 2.015 s | 0.046 s | 135.73 MiB |
| XLSX | success | 3 / 9 | 9 / 9 | 9 / 9 | Sheet group `Order Lines`, page 1, one table-region box in sheet grid coordinates | 2.013 s | 0.017 s | 130.39 MiB |
| HTML | success | 3 / 9 | 9 / 9 | 9 / 9 | No pages or boxes | 1.929 s | 0.021 s | 130.74 MiB |
| EML | success | 0 / 0 | 0 / 9 | 0 / 0 | No pages, sheet, or boxes | 1.951 s | 0.011 s | 130.21 MiB |
| PPTX | success | 3 / 9 | 9 / 9 | 9 / 9 | Slide page 1, one table-region box in slide coordinates | 1.896 s | 0.023 s | 131.79 MiB |

All five conversions reported success, but only four preserved a structured table: **12/15 known table rows and 36/45 exact known cell strings** across this fixture set. All 36 recovered table cells have row/column start and end indices and spans. **Zero of the 36 cells have a cell-level bounding box.** XLSX and PPTX each have only a table-region box, which must not be treated as evidence for an individual cell. Median cold process wall time was 1.951 s (range 1.896–2.015 s); sampled peak RSS ranged from 130.21 to 135.73 MiB. These numbers are for tiny files and one conversion at a time.

The EML fixture's HTML alternative contains the table, but the converted output used the nonempty plain-text part and lost its rows. Docling's [email backend](https://github.com/docling-project/docling/blob/main/docling/backend/email_backend.py) selects nonempty plain text before HTML; its HTML fallback also exports Markdown into paragraphs rather than retaining a `TableItem`. A future candidate is to parse MIME safely, pass a selected HTML part through Docling's HTML backend, and preserve email headers and attachment boundaries separately. That path was not tested here.

## Integration boundary

For four formats, a next-stage adapter can reuse Docling's table grid and text while adding source-specific evidence: sheet name and cell address for XLSX, slide plus cell identity for PPTX, and stable OOXML/DOM locations for DOCX/HTML. A faithful source viewer could use these structural cell identities without pixel boxes; the table-region boxes here are not cell evidence. DOCX and HTML provided no page geometry in this trial. The current [product evidence validator](../../frontend/src/server/product-auto.ts) and [review UI](../../frontend/src/components/idpo/product-auto-document-page.tsx) require OCR page, text offsets, and an exact quote. Thus converter integration also needs a source-native evidence contract and reviewer path before these formats can satisfy acceptance or human review. Docling's [HTML options](https://github.com/docling-project/docling/blob/main/docling/datamodel/backend_options.py) default to no page rendering and no image fetching; keep remote/local resource fetching disabled for untrusted HTML unless a sandboxed renderer is justified and tested.

This trial did not cover real documents, merged cells, formulas, multi-sheet workbooks, nested tables, attachments, remote HTML resources, malformed input, concurrency, Linux containers, or downstream schema/value extraction. It does not demonstrate lower end-to-end cost or accuracy. A product adapter would require its own evidence tests, mixed-format holdout, and the user's required 2,000 distinct-document extraction gate after implementation.
