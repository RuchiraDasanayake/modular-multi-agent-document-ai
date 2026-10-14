# Browser review and source-preview verification

Date: 14 October 2026. Classification: review workspace (`core`, `simplify`),
local raster preview (`core`, `keep`), operator instructions (`supporting`, `keep`).

## Changes

- TXT/JSON results show extracted source text immediately. Extracted text can
  be copied; it is labelled accurately for digital text as well as OCR.
- PDF and supported images use an authenticated local PNG preview, with page
  navigation and zoom. The source and proposed fields remain beside each other
  on desktop and stack on narrow screens.
- Reviewed document JSON and run JSONL can be copied through the same server
  export gates as downloads. Clipboard failures have visible instructions.
- A repeated batch selection warns that another run can incur another model
  charge. A normal in-flight start no longer displays the lost-response warning.
- Review inputs are locked while their save is pending, so new edits cannot be
  silently replaced by the saved snapshot. Source navigation remains available.
- Run-list reads are invalidated around admission. Older focus/poll responses
  cannot hide a newly queued run or reconcile an obsolete request receipt.
- Added-field source references say "source" or "extracted text" for both digital
  text and OCR. Proposal status/counts are distinguished from the saved human review.

The renderer reuses installed PDFium/Pillow. It accepts only owner/admin-accessible
uploaded bytes and has no provider credentials, arbitrary path or URL input.
Bounds are 20 MiB source, 50 PDF pages, 1,600-pixel preview edge, 12-million-pixel
source image, 15 seconds, and two concurrent renderers per server process.
Failed termination retains its capacity slot until the child closes. Original
downloads and extraction artifacts are unchanged. A raster preview does not
create verified field pixel coordinates.

## Actual browser checks

The native production build was used with the authenticated administrator account.
Review notes explicitly identify automated synthetic demonstration checks; no
independent human-effort measurement is inferred from these saves.

| Check | Observed outcome |
| --- | --- |
| Existing TXT sample review | Source text visible; `UI-2001` and `42.5` matched; review saved; JSON and JSONL copied. |
| Apply schema to remaining TXT | One run admitted from the UI; `UI-2002` and `73.25` matched; export remained disabled until review; saved review enabled export. |
| New two-page PDF setup | New job created in UI. Authenticated API uploaded the 1,204-byte self-authored PDF because the browser file chooser could not be automated. |
| AI schema suggestion | Natural-language intent saved in UI; Luna 6 proposed `invoice_number` and `final_amount_due` with meanings/examples. 619 input and 176 output tokens were reported. |
| Confirmation and preview | Suggested fields adopted, saved and confirmed as revision 3 in UI. Preview returned `DEMO-2026-014` and `125.75`. |
| Source preview | Both PDF pages visibly rendered. Next/previous page controls and end-page bounds worked; desktop source/field columns and the narrow layout were inspected. |
| Narrow-screen zoom | At a 314-pixel viewport, the zoomed 1,224-pixel page scrolls inside a 234-pixel preview pane; the document remains 314 pixels wide. Fit width restores the page. |
| PDF review and copy | Both fields checked against rendered page 1, review saved, and copied JSON contained the expected values and review provenance. |
| Add a field through review | Added `payment_terms = "30 days"` from the exact page-2 quote, saved revision 2, reloaded, and verified the persisted field and `human_added` provenance in copied JSON. Review-status refresh kept the run and its export controls available. |
| Research overview boundaries | Rebuilt and checked the page in the browser: experimental routing and service health are explicitly scoped to research; an unavailable AHMN service shows `Research outcomes unavailable`, rather than implying an empty history. The extraction link leads to the document workspace. |

Read-only authenticated verification checked each export, its recorded review
revisions, the explicit test notes, and absence of reported human effort. The first
PDF export below predates the separate added-field check and is retained as history.

| Export | SHA-256 |
| --- | --- |
| TXT preview JSONL | `4856736dcd3fa07c9a634bc6e2042749c89227e05fb9a0a5c41dc92985cfe91b` |
| TXT batch JSONL | `3534b31ff073026823a612117285119ce1cb2b7989bc311334ee5303413f52f7` |
| PDF reviewed JSON, revision 1 | `2c32e01345dbe177a43d9194e3b31c2d0cfbf37cc78247236cc3ed3ebbcf5b3f` |
| PDF reviewed JSON, revision 2 with added field | `125909f9b053ab6f1458e58a59a4c35640c888c2eb47a6cf34b933c49e8e2e2b` |

These three small synthetic documents establish integration behavior, not
general-purpose accuracy, scalability or human productivity. They are separate
from the frozen operational and paired-quality campaigns.

## Automated checks and remaining browser boundary

- 16 Python renderer tests and 10 authenticated endpoint tests passed, including
  actual local PNG/PDF rendering, ownership, bad pages/files, credential exclusion,
  timeout termination and capacity retention after failed termination.
- 19 focused review, confirmed-preview, batch-export and source-guidance tests passed.
- Five delayed-response regressions cover admission/refresh ordering, shared reads,
  stale errors, busy state, and navigation invalidation. They passed together with
  nine existing readiness, visual-review and request-idempotency checks.
- TypeScript and targeted ESLint passed with one existing internal-navigation
  warning in `idpo-api.ts`; no lint errors. Production builds completed.
- The embedded browser blocked direct document navigation and did not expose a
  file chooser or a download event. Authenticated upload/export APIs and UI copying
  were verified, but ordinary browser file selection and saved-file delivery still
  require a Chrome/Edge check. Download-request messages do not assert file delivery.
  Both browsers were unavailable to the browser tool, and the user could not run
  the manual check on 14 October. This remains unverified, not a passed check.

Use the [demo runbook](../DEMO_RUNBOOK.md). Final research and conference sign-off
remain subject to the paired study, truthful manuscript updates and author details,
consent and signatures. Successful UI checks do not close those separate gates.
