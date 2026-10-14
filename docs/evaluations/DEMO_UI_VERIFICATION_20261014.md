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
| PDF review and copy | Both fields checked against rendered page 1, review saved, and copied JSON contained the expected values and review provenance. |

Read-only authenticated verification also checked each export, its one recorded
review revision, the explicit test notes, and absence of reported human effort.

| Export | SHA-256 |
| --- | --- |
| TXT preview JSONL | `4856736dcd3fa07c9a634bc6e2042749c89227e05fb9a0a5c41dc92985cfe91b` |
| TXT batch JSONL | `3534b31ff073026823a612117285119ce1cb2b7989bc311334ee5303413f52f7` |
| PDF reviewed JSON | `2c32e01345dbe177a43d9194e3b31c2d0cfbf37cc78247236cc3ed3ebbcf5b3f` |

These three small synthetic documents establish integration behavior, not
general-purpose accuracy, scalability or human productivity. They are separate
from the frozen operational and paired-quality campaigns.

## Automated checks and remaining browser boundary

- 16 Python renderer tests and 10 authenticated endpoint tests passed, including
  actual local PNG/PDF rendering, ownership, bad pages/files, credential exclusion,
  timeout termination and capacity retention after failed termination.
- 19 focused review, confirmed-preview, batch-export and source-guidance tests passed.
- TypeScript and targeted ESLint passed with one existing internal-navigation
  warning in `idpo-api.ts`; no lint errors. Production builds completed.
- The embedded browser blocked direct document navigation and did not expose a
  file chooser or a download event. Authenticated upload/export APIs and UI copying
  were verified, but ordinary browser file selection and saved-file delivery still
  require a Chrome/Edge check. Download-request messages do not assert file delivery.

Use the [demo runbook](../DEMO_RUNBOOK.md). Final research and conference sign-off
remain subject to the paired study, truthful manuscript updates and author details,
consent and signatures. Successful UI checks do not close those separate gates.
