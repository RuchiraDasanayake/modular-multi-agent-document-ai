# Real public native-format development corpus — 2026-10-12

**Status:** ten local source files frozen for development; no extraction, gold annotation, model call, or accuracy score. This is `research_evidence` with the primary action **keep**. The acceptance check for this acquisition is exact source/rights/hash reproducibility, not extraction quality.

The files are outside Git in a local directory selected through `NATIVE_DEV_CORPUS_DIR`. The companion [machine-readable manifest](NATIVE_REAL_PUBLIC_DEV_MANIFEST_20261012.json) records every publication URL, direct asset URL or API request, byte count, SHA-256 hash, and rights note. No file from the reserved ExtractBench PDF holdout or a user document was opened. These ten are a development set and must never be reported as an independent holdout or as the paper's measured results.

## Selection and frozen bytes

| Format | Real source | Local filename | Bytes |
| --- | --- | --- | ---: |
| DOCX | UK Evaluation Task Force 2025 indicators report | `gov_etf_indicators_2025.docx` | 114,282 |
| DOCX | UK Evaluation Task Force technical annex | `gov_etf_technical_annex_2025.docx` | 126,084 |
| XLSX | Defra June 2025 workforce/payroll data | `gov_defra_workforce_june_2025.xlsx` | 60,123 |
| XLSX | Department for Education adoption agency data, 2014 Q2 | `gov_adoption_agency_data_q2_2014.xlsx` | 158,700 |
| PPTX | Ofqual 2026 exam-grading lesson slides | `gov_ofqual_grading_lesson_2026.pptx` | 760,730 |
| PPTX | Ministry of Defence cyber-protection board slides | `gov_defence_cyber_board_2018.pptx` | 213,121 |
| HTML | Published Evaluation Task Force report page | `gov_etf_indicators_2025.html` | 77,706 |
| HTML | Published Ofqual exam-grading lesson page | `gov_ofqual_grading_lesson_2026.html` | 86,097 |
| EML | ASF Log4j 2.25.0 announcement | `asf_log4j_2250_2025.eml` | 5,950 |
| EML | ASF POI 5.4.1 announcement | `asf_poi_541_2025.eml` | 4,672 |

The ten evaluation files total **1,607,465 bytes**. The two additional raw mbox-source receipts total 10,823 bytes; they are retained separately for provenance. The six Office files begin with ZIP package magic `PK\x03\x04`; the two HTML downloads begin with `<!DOCTYPE` after leading blank lines; the EML derivatives begin with `Return-Path:`. These signature checks only establish plausible format, not semantic parser success or safety of untrusted content.

The [Evaluation Task Force publication](https://www.gov.uk/government/publications/evaluation-task-force-output-and-outcome-indicators-march-2025) identifies the report and annex as Word documents and presents the report's indicator table on the HTML page. [Defra's publication](https://www.gov.uk/government/publications/defra-workforce-management-information-june-2025) identifies the XLSX as published staff-number and payroll data; the [adoption publication](https://www.gov.uk/government/publications/adoption-leadership-board-quarterly-data-reports) identifies the agency-level XLSX. [Ofqual's publication](https://www.gov.uk/government/publications/understanding-grading-classroom-and-assembly-resources) identifies the lesson slides and linked [HTML lesson](https://www.gov.uk/government/publications/understanding-grading-classroom-and-assembly-resources/lesson-plan-in-html-format-understanding-how-your-exams-are-marked-and-graded). The [Ministry of Defence publication](https://www.gov.uk/government/publications/defence-cyber-protection-partnership-presentation-slides) identifies its board slides.

## Rights boundary

Each selected GOV.UK publication displays **Open Government Licence v3.0, except where otherwise stated**, and [GOV.UK's terms](https://www.gov.uk/help/terms-conditions) explain that most Crown-copyright content may be reproduced under that licence subject to its conditions. The Ofqual HTML document also expressly warns that identified third-party copyright needs separate permission. The manifest includes the originating agency for attribution. We have not audited embedded images, trademarks, or third-party material inside each Office package. Consequently, the frozen bytes remain local; redistribute full files or transfer them to a cloud provider only after a file-level rights and data review.

The two email messages are actual public ASF archive posts. The [ASF public-forum archive policy](https://www.apache.org/foundation/public-archives.html) calls posts public without conditions, and its [research page](https://apache.org/research/) permits research on publicly archived lists subject to responsible use. [ASF Pony Mail's API documentation](https://github.com/apache/ponymail-foal/blob/master/docs/API.md#sourcejson) documents the single-message raw source endpoint. `POST /api/email.json` reported `private=false` and zero attachments for both chosen IDs. **An Apache-2.0 licence for the authors' email content was not verified.** Keep the `.eml` files in local research evaluation; do not redistribute them as corpus assets or send them to ICORE or another cloud model without further review. The [Log4j message](https://lists.apache.org/thread/9w0zpqgt803kz6onzdzyy1x1vfyt01vb) and [POI message](https://lists.apache.org/thread/n0w82jv5v4twm4vbk937hgk3wmbngjgs) are the primary archive references.

## Reproduction and integrity

1. Create a fresh directory outside the repository. For each GOV.UK entry in the JSON manifest, download `source_url` directly to `filename` without text conversion or normalization. Compare byte count and SHA-256. A changed page or asset is a new source revision, not a silent replacement of this frozen corpus.
2. For each ASF entry, `POST` the listed `source_json_body` to `https://lists.apache.org/api/source.json` with `Content-Type: application/json` and save the response bytes as `raw_filename`. Compare its raw byte count and SHA-256. The endpoint returns an mbox `From ` envelope line before the RFC 2822 message. Find its first LF and write **all bytes after that LF, unchanged**, to `filename`; compare the derivative byte count and SHA-256. The raw receipts and the EML derivatives have separate hashes in the manifest.
3. Check that every local path resolves within the chosen corpus directory, each hash matches, and there are ten distinct derivative/original evaluation files with exactly two per format. Do not fall back to a live changed source if any hash fails.

This acquisition did not execute the native adapter or inspect a ground-truth file. Later evaluation should first test parse success, bounded resource use, exact text/cell locator resolution, and unsupported-feature reporting. Human-labelled schemas and values are needed before reporting extraction precision, linked-row quality, review work, or cost. The two Office datasets and two government reports are related within their respective publishers; the sample is small, mostly UK government, and not representative of arbitrary documents. The HTML files include navigation/site chrome, and the two simple emails have no attachments. A broader, independently sourced set is still necessary.
