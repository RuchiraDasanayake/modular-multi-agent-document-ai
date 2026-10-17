# Native browser demonstration — 17 October 2026

Classification: `research_evidence`; action: `keep`.

This engineering check used the deployed production build from main revision
`732ad1e` and two previously authored synthetic fixtures. It does not add documents
to the frozen research studies or measure independent human review effort.

## Observed flow

The in-app browser completed sign-in, new-job creation, PDF file selection and
upload, manual string/decimal field definitions with meanings, schema confirmation,
sample extraction, source-page display, review save and a saved JSON download.
After uploading a second TXT file, the same confirmed schema completed the
remaining-file batch, source-text review and a saved JSONL download.

| Source | Requested invoice number | Requested amount due | Outcome before review |
| --- | --- | --- | --- |
| Authored two-page PDF | `DEMO-2026-014` | `125.75` | Both values matched |
| Authored TXT | `UI-2002` | `73.25` | Both values matched |

Both runs used Luna 6. The TXT invoice quotation did not pass the automatic
text-match status; the displayed source was checked explicitly during the test.
Review notes identify the decisions as automated synthetic UI checks, not a human
study. Export was unavailable before review and available after review.

The actual browser download events returned saved files in the local Downloads
directory, whose JSON payloads were read back. This closes file selection and
saved-download verification for this in-app browser, not Chrome or Edge.

| Saved payload | SHA-256 |
| --- | --- |
| Reviewed PDF result, JSON | `9e7e43c412e98da0c3f59cd92efd8d08ba381957d8e4faf2f1b5a6e8e7bf4e89` |
| Reviewed remaining-file run, JSONL | `adbe2d351bdfd138223d970041e001ec632256d505991fe3901edeb77d7856e7` |

## Startup and checks

All services were stopped when inspected. The first full preflight failed the
scanned-PDF sample check; an isolated repeat and subsequent full preflight passed.
The initial failure was not isolated to a root cause and is not reported as a code
fix. Stale tracked process records were cleared through the supported shutdown
script, then the normal launcher started the production stack successfully.
No startup guard was bypassed. All advertised synthetic parser checks passed.

Authenticated retained preview and batch exports matched their existing reference
payloads. Frontend and gateway health returned HTTP 200 with PostgreSQL and token
revocation healthy. The runtime preflight regression suite passed all 27 tests.

## Remaining boundaries

The application remains a bounded extraction-and-review workflow. Four correct
values from two simple fixtures do not establish arbitrary-document accuracy,
priced cost per correct document, high availability or a new research improvement.
The initial intermittent OCR preflight failure remains unexplained. Use the
supported launcher before the presentation and retain reviewed examples if the
provider is unavailable. Chrome/Edge and native PowerPoint execution remain
separate checks. Author approval, signatures and external submission are not
established by this product verification.
