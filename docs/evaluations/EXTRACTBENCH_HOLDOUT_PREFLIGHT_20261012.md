# ExtractBench holdout preflight: no development admission

Status: metadata-only check on 12 October 2026. **No PDF, JSONL label, or
schema was downloaded or opened; no extraction was run.** The proposed
370-case external holdout in [the corpus plan](DIVERSE_CORPUS_CANDIDATES_20261012.md)
remains untouched. No source was admitted to a development set.

## Frozen metadata and overlap

I queried the publisher's [Hugging Face dataset API](https://huggingface.co/api/datasets/llamaindex/ExtractBench?blobs=true)
for PDF path, byte size and repository content ID only. The full dataset
resolved to revision `51bf3a03eb7feeaef8952be1fc2fc7f924ee72dc` with
370 PDFs. The publisher's separate `test-data` branch resolved to
`1107fe033a94e93cbc47bb44ded14f02e9c61c62` with six PDFs. The
[official downloader](https://github.com/run-llama/ExtractBench/blob/eb0797020fa22123c42ee4d366963cca321da3ca/src/extract_bench/data/download.py)
routes `--test` to that branch. All six test paths also appear in the full
revision, with the **same size and content ID**:

| Publisher test PDF path under `docs/` | Bytes | Content ID in both revisions |
| --- | ---: | --- |
| `long/real_sm0801_eco_full.pdf` | 215,847 | LFS SHA-256 `e21e6eeb75d5aa1ce519c636de319e20445980e7a1ef28b7aa897d004af89030` |
| `medium/real_pueblo_oct_2025.pdf` | 980,011 | LFS SHA-256 `aa3548beb298d8de582016b1f4fd9e2b066c983fc7759462901506ef19bca3e8` |
| `medium/veralto_earnings_deck_q4fy25.pdf` | 1,722,236 | LFS SHA-256 `0b434fe01dc376c8972ede272df0551c30965f58b880dcecdc37bb254de970ce` |
| `short/W14-Atascosa SWD Well No. 4 - W-14 (Updated 01.22.2025).pdf` | 84,826 | Git blob SHA-1 `f610682dfa1e5eeb8d899ce1436db12c3c873aef` |
| `short/bianco-2024.pdf` | 593,057 | LFS SHA-256 `571fe05a74b6c4820906ac9c00e9a8ce141420b7de54d4129f60c61c887c5012` |
| `short/real_wyo_Goshen_2024.pdf` | 304,618 | LFS SHA-256 `391d65fe5cda94842ac341cf515f947f7a1f554a00f0cc473d14fde6523282a7` |

The Git blob ID is a repository object hash, **not** a raw-file SHA-256.
These metadata IDs suffice to prove the six branch files overlap the main
revision without viewing their contents. The check compared all six paths,
sizes and content IDs against the 370-entry metadata listing; all matched.
It did not audit same-origin or visually duplicated PDFs under different
filenames. The publisher also reports 38 degraded recaptures paired with clean
documents, so raw-hash deduplication alone would be insufficient for a future
source-disjoint split.

**Decision:** Do not use `extract-bench download --test` for development while
claiming an untouched 370-case holdout. Do not select any of the 370 for
prompt, parser, routing, schema, threshold or reviewer-flow tuning. A later
intentional split change would need a new manifest and a reduced blind
denominator; this preflight does not make that change.

## Rights and transfer boundary

The pinned [dataset card](https://huggingface.co/datasets/llamaindex/ExtractBench/blob/51bf3a03eb7feeaef8952be1fc2fc7f924ee72dc/README.md)
declares Apache-2.0 for the released dataset and says its real PDFs come
from public records, including regulatory filings, court and agency
exhibits, tax forms and published business documents. The pinned
[benchmark repository license](https://github.com/run-llama/ExtractBench/blob/eb0797020fa22123c42ee4d366963cca321da3ca/LICENSE)
is Apache-2.0. Neither statement is a per-origin copyright, privacy or
cloud-processing ledger for every embedded third-party document. Publicly
accessible filing material can retain third-party rights and personal data.
Treat local benchmark research as conditional on the dataset publisher's
terms; require source-level rights and sensitive-data review before provider
transfer, commercial redistribution or use as product training data.

## Independent development cohort to acquire next

Build a **separate 12-original, local-only PDF pilot** from documents the team
created or has explicit local evaluation rights to use, with at least eight
different document families and issuers. Include born-digital text, scans,
repeated tables, blanks, and multi-page documents. An issuer-authored blank
government form may be useful for parser checks, but filled samples and
third-party exhibits need their own rights check. Do not count exports,
recaptures, pages, or synthetic variants of one original as new sources.
Exclude all ExtractBench PDFs, reserved CORD receipts, reserved DocLayNet test
pages, and existing VRDU holdout sources by origin as well as raw hash.

Before any acquisition or label access, freeze for each original: canonical
origin ID and source URL or owner permission receipt; raw SHA-256 and size;
family, issuer, language, page count and scan state; near-duplicate group;
local-only/cloud permissions; and development allocation. Keep files outside
Git, cap this pilot at 12 PDFs and 500 MB, and independently verify hashes
after transfer. If rights or origin cannot be established, record the case as
unadmitted rather than filling the quota with questionable material.

Adjudicate an automatic-schema arm **without a supplied schema**: field
meaning, type, null/absent semantics, and repeated-record grouping first,
then values and evidence. Score schema field/type precision and recall plus
group structure, followed by typed value F1, strict linked-row F1, evidence
page/box correctness, abstention/review and cost per accepted document.
Separately run a **supplied-schema** arm using the publisher-style value,
record-alignment and grounding metrics. ExtractBench itself is explicitly
[schema-guided](https://github.com/run-llama/ExtractBench/blob/eb0797020fa22123c42ee4d366963cca321da3ca/README.md),
so its value score must never be reported as automatic schema quality.
Failures and input-cap rejections stay in denominators.

The publisher's 370 PDFs are a useful later, one-shot PDF benchmark but are
smaller than the user's required **2,000 distinct raw-source extractions after
each substantive product extraction implementation**. They also cannot prove
native DOCX, XLSX, PPTX, HTML or EML extraction. This metadata-only preflight
counts as **zero** of the 2,000 and establishes no extraction quality result.
