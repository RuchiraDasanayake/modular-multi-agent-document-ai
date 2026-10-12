# Diverse extraction corpus: candidate and holdout decision

Status: research and allocation proposal, 12 October 2026. No new corpus was
downloaded, rights-cleared for provider transfer, labeled locally, or run
through the product. The existing [dataset plan](../DATASET_PLAN.md) remains
the execution rule, including the 2,000 **distinct raw-source** extraction
gate after each substantive extraction change.

## Decision

Use the creator's [ExtractBench](https://github.com/run-llama/ExtractBench)
as the best available **conditional external PDF extraction holdout** and
[DocLayNet](https://github.com/DS4SD/DocLayNet) as a separate **layout-only**
component benchmark. Build the missing Office/HTML/email product cohort from
documents the team owns or has explicit evaluation and provider-processing
rights to use. None of these sets replaces the 2,000-source execution gate or
proves arbitrary-format, automatic-schema extraction by itself.

| Source | Verified scope and labels | Rights and admission decision |
| --- | --- | --- |
| [ExtractBench creator repository](https://github.com/run-llama/ExtractBench#dataset) and [dataset card](https://huggingface.co/datasets/llamaindex/ExtractBench) | 370 PDFs, 4,869 pages, eight business domains, 67 document types; 252 short, 98 medium, 20 long. JSON Schema, expected values, repeated-record identity rules and per-field evidence; publisher's metrics cover values and verified page/box grounding. It includes 325 real documents, 45 synthetic long lists and 38 degraded recaptures of clean documents. | The [card declares Apache 2.0](https://huggingface.co/datasets/llamaindex/ExtractBench) and says the files derive from public records. Public availability and a dataset-level declaration do not independently establish every third-party source's redistribution or cloud-processing rights. Record source terms and screen personal data before copying documents to ICORE or another provider. **Conditional** local research candidate pending a per-origin rights ledger. |
| [DocLayNet creator repository](https://github.com/DS4SD/DocLayNet/blob/main/README.md) and [license](https://github.com/DS4SD/DocLayNet/blob/main/LICENSE) | 80,863 annotated pages; fixed train 69,375, validation 6,489, test 4,999. Eleven layout-box classes from financial reports, scientific articles, laws, government tenders, manuals and patents. Extra files provide matching single-page PDFs and digital text cells with coordinates. | CDLA-Permissive-1.0 is attached to the released data, with attribution/notice duties. Admit for layout-region box tests after revision and source inventory are frozen. It has **no gold business field, linked-row extraction or reading order** and its single-page PDFs are not whole original reports. |
| [PubTables-1M creator repository](https://github.com/microsoft/table-transformer#pubtables-1m) | 947,642 annotated tables with row, column and cell boxes/text from PubMed articles; 401,733 PDF-level annotation files. Useful for cell geometry, not invoice line items or automatic schema discovery. | [Creator processing notes](https://github.com/microsoft/table-transformer/blob/main/scripts/process_pubmed.py) explicitly warn that source PubMed article licenses vary. Admit only a source-license-filtered subset after mapping article IDs to PMC license terms; do not treat the code license as a document grant. |
| [INV-CDIP creator repository](https://github.com/salesforce/inv-cdip) | 350 labeled invoices, seven known fields with value/key boxes; about 200,000 unlabeled invoices. No linked line-item gold. | Dataset is CC BY-NC 4.0 and underlying tobacco-industry documents have separate copyright/fair-use terms. Optional noncommercial academic diagnostic only, subject to source rights; exclude from the default commercial product corpus. |
| [Kleister NDA](https://github.com/applicaai/kleister-nda) and [Kleister Charity](https://github.com/applicaai/kleister-charity) | NDA: 540 documents; Charity: 2,788 long annual reports. Their task supplies requested key names, with some test gold withheld. The [paper](https://arxiv.org/abs/2105.05796) reports scanned and digital documents. | The creator repositories do not state a reusable document license; the [Charity license question](https://github.com/applicaai/kleister-charity/issues/2) asks whether commercial use is allowed without an answer in the issue. Keep out of the rights-cleared product cohort until the publisher clarifies source and derivative rights. |

The existing plan already records [CORD v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2), [FUNSD](https://github.com/crcresearch/FUNSD), [XFUND](https://github.com/doc-analysis/XFUND) and [DocILE](https://github.com/rossumai/docile); their restrictions and allocated CORD 60/40 split are unchanged.

## Proposed source-disjoint allocation

1. **Development:** keep the already frozen 60 CORD receipts for receipt
   tuning. Acquire and adjudicate a target of **25 development originals per
   format** for DOCX, XLSX, PPTX, HTML and EML (125 originals total), from
   team-owned files or sources whose terms explicitly permit this evaluation.
   Deliberately include letters/reports in DOCX, multi-sheet tables in XLSX,
   slide tables in PPTX, nested/irregular web tables in HTML, and MIME
   alternatives plus attachments in EML. Seek at least five non-English
   originals per format with qualified annotators; if unavailable, report the
   actual language coverage rather than filling the quota with translations
   of the same source.
   A PDF export, screenshot, OCR text, email attachment and reformatted copy
   of one original all share one origin ID. Do not count them as new sources.
2. **Internal product holdout:** acquire **10 additional originals per native
   format** (50 total) from disjoint issuers/templates and organizations;
   seek at least two non-English originals per format, again only when they
   can be independently adjudicated. Freeze origin IDs, raw SHA-256,
   annotation files and use-right receipts
   before model selection. If a format cannot supply disjoint source groups,
   report its denominator as zero and defer claims for that format instead of
   substituting synthetic copies. The existing 40 CORD receipts remain reserved
   independently and are never used for prompt examples or route tuning.
3. **External extraction holdout:** reserve all 370 ExtractBench cases for a
   one-shot run after design choices freeze, conditional on the rights and
   overlap audit above. Pin the exact dataset Git revision and scorer commit:
   the [publisher has revised evidence and values](https://huggingface.co/datasets/llamaindex/ExtractBench/discussions/2/files), so `main` is not a stable benchmark version. Audit raw hashes, canonical source URL/filing ID, document title, template and degraded-recapture parent against VRDU, CORD and the owned cohort. Keep paired clean/recaptured files in the same source group. If a source was seen in tuning, exclude it from the internal blind summary and disclose the overlap; retain the publisher's full benchmark score separately if required for comparability. Its public gold also makes this a **protocol holdout**, not a secret benchmark.
4. **Layout holdout:** use DocLayNet's official train/validation data only for
   component selection and reserve the fixed 4,999-page test split for a
   one-shot layout score. Check `doc_name`/collection grouping before any
   custom re-split; never count its pages as business extraction documents.

For ExtractBench, run two separately scored arms: (a) the publisher's supplied
schema for value/row/evidence comparability and (b) the product's schema
generation with the publisher schema and gold values hidden from prompts and
recipes. In arm (b), adjudicate field meaning, type, absent fields and repeated
grouping **before** inspecting value predictions; then score values and
evidence. Do not call the publisher schema-guided score automatic-schema
quality. Include input-cap failures in the denominator: the current product
limit of 50 pages excludes the benchmark's 20 long cases from successful
processing, and this limitation must appear in any full-cohort result.

For each native original, adjudicate typed scalar values, repeated rows/cells,
null/absent fields, and file-native source locators (DOCX paragraph/table cell,
XLSX sheet/cell, PPTX slide/shape/table cell, HTML element/XPath, EML MIME
part/header/attachment). Add page/box coordinates only when a rendered surface
supports them; do not invent PDF boxes for native Office or email content.

## Remaining gap and admission checklist

No verified public corpus in this audit supplies **all** of native DOCX,
XLSX, PPTX, HTML and EML, open commercial-use document rights, arbitrary
AI-generated schemas, linked business rows and grounded evidence. The owned
cohort is therefore essential but **not yet available**. The named public
corpora are PDF/image-heavy and mostly English; the existing XFUND
multilingual forms are noncommercial and known-schema research evidence only.

Before admitting any source, record creator, exact revision, document license
and provider-transfer permission, raw/origin hashes, family, language, file
format, scanned/digital condition, gold semantics, source locators, split and
near-duplicate group. Run the 2,000-source gate separately after each
substantive implementation, then report every newly admitted family as a
source-disjoint slice with its own quality, review, failure and cost denominator.
