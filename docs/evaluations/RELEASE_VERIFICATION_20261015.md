# Native product verification — 15 October 2026

Classification: `research_evidence`; primary action: `keep`.

This is an engineering release check on authored data. The completed 2,000-source operational study and
240-source paired quality study retain their original code, outcomes and limitations. These later repairs
are not evidence of a new accuracy or USD-cost improvement.

## Implemented and reviewed

The [implementation task list](../IMPLEMENTATION_FINALIZATION_20261015.md) records eight reproduced defects:
schema-read failure enabling extraction, lost example line breaks, hostile JSON replies interrupting a batch,
invalid visual scalars, changed Unicode field identity, incomplete JSON-container export, incorrect logical
document budgeting/unsafe JSON shape intake, and UI review gates assuming one result per file.

Changes are recorded in commits `e7a8492`, `5e9575a` and `8cc149f`. Independent review covered reply/frontend
contract parity and the cross-language JSON count/hash boundary. No provider model, prompt, routing default,
shared research intake or frozen prediction/reference artifact changed.

## Combined verification

| Check | Observed result |
| --- | --- |
| Product Python suites plus confirmed-schema routing | 414 passed; 2 opt-in live RapidOCR tests skipped |
| Full frontend/server suite on deployed Node 22.20.0 | 235 passed; zero skipped |
| Actual local image/PDF preview renderer tests | Included and passed using the product Python environment |
| TypeScript, targeted ESLint and touched Python Ruff checks | Passed |
| Production build and native restart through supported scripts | Passed |
| PostgreSQL, gateway, frontend process/port identities and worker heartbeat | Verified |
| Authenticated retained reviewed demo export | HTTP 200; original bytes preserved |
| Conference technical handoff files | All six hashes unchanged; requested paper PDF matches |

The two Python skips require explicit `TEST_RAPIDOCR_PYTHON` and `TEST_RAPIDOCR_FONT`. The existing OCR rejection
test was stale: multi-frame input is rejected before OCR as `multi_frame_image_unsupported`. Its corrected
regression proves zero OCR/model calls and a terminal source outcome. This changes a test, not the runtime.

The full upload suite passed on native Node 22.20.0. An exploratory Node 24.19.0 run failed synthetic FormData
cancellation tests inside Undici and intermittently failed a later valid request; the valid request alone passed
on both. Node 24 is not certified by this release. No speculative upload-runtime workaround was added.
Component callback tests use deterministic hooks; they do not certify real-browser layout or React scheduling.

Production build: `DYihx4Y0dm9f6uP7EHhyg`.
Source fingerprint: `20b2f7bfed83ee455328c18edab2e79e633fdb3ecabd0a7bb6e37c0685263e62`.

## Authenticated ICORE integration

The rebuilt production frontend, PostgreSQL dispatch and separate worker processed one authored JSON original
containing two invoices, followed by one authored TXT original. All three used confirmed string/decimal fields,
including the exact Unicode field ID `straße` and source value `Königstraße`.

- Exactly **three Luna 6 value-model calls** were recorded, with zero provider retries.
- All **nine authored field targets** matched before review. This tiny synthetic check is not a quality benchmark.
- Before review, JSONL export returned 409. After the first JSON document was reviewed, export and remaining-batch
  admission still returned 409. Both became available only after the second document was reviewed.
- The reviewed JSON preview exported two records; the remaining TXT batch exported one. All fields retained
  `human_verified` provenance. Reviews were explicitly labelled automated synthetic checks, not a human study.
- PostgreSQL recorded succeeded dispatches with logical-document budgets **2** and **1**.
- A separate 5,001-entry JSON original returned **413 before execution**, with no run record or model calls.
- The queue was idle afterwards, with 13 succeeded retained dispatches.

Reviewed preview JSONL SHA-256: `60c0f5eed27c0104e32d823a5a068a60f2836f13bef5bf316aaa0c58a6652181`.
Reviewed remaining-batch JSONL SHA-256: `5d2f09e15276d1c31b2499db3a2d21719eb1aed870a01c6a1c0ec2e446997a6e`.
Retained prior demo export SHA-256: `125909f9b053ab6f1458e58a59a4c35640c888c2eb47a6cf34b933c49e8e2e2b`.

Private engineering receipt SHA-256: `a3f1eadfe698423ec411621c6b7521df04802d15a3906254db4250389facfc04`.
It records exact application/test hashes, build identity, log hashes, fresh retained export, idle queue and
conference-file comparisons. Private synthetic integration state SHA-256:
`cbf4f03da1f27505e9724b098746689d0a09fd8ab9163c3bfaf544c35378dffc`.
Credentials and private source/run paths are not published here.

## Remaining sign-off boundaries

The [conference package](../CONFERENCE_HANDOFF_20261014.md) already contains the measured results, reviewer
response, oral deck and editable author documents. It remains an author-review handoff. Missing author details,
consent, signatures, approval and external submission must be completed by the authors; no signature or consent
was invented. The author documents were preserved.

Computer input was stopped with the physical Escape key. Ordinary Chrome/Edge file selection, saving a browser
download and native Microsoft Office execution remain unverified. The HTTP exports above verify payload delivery,
not a browser Save dialog. The supported deployment remains one native host with bounded admission and shared
filesystem storage. Arbitrary-document accuracy, priced cost per correct document, measured human review effort,
multiple frontend writers and high availability remain unestablished.
