# Product improvement and verification — 17 October 2026

Classification: `core` supporting documentation; action: `keep`.

## Scope and acceptance checks

The current confirmed-schema workflow remains the product boundary. Preserve the
frozen research studies and their measured outcomes. New engineering checks are
reported separately; authored fixtures do not establish general-document accuracy.

1. Native tables: recover explicitly headed single-row tables with exact source
   cell evidence, while retaining abstention for ambiguous layouts.
2. Batch isolation: one unexpected document-processing failure must not discard
   later originals. Preserve failed/uncertain outcomes and never automatically
   replay a possibly paid attempt.
3. Schema and review UX: display the confirmed meanings beside preview actions
   and provide direct links to the samples requiring review.
4. Required-field contract: evaluate the existing keyed v2 profile before using
   it in new deployed runs. Structural completeness is not semantic accuracy.
5. Workflow: exercise actual browser upload, schema confirmation, preview, source
   inspection, review, remaining-file extraction and saved export. Include linked
   duplicate rows and absent fields, with expected results written before calls.
6. Evidence and release: run relevant tests and production build, document measured
   outcomes and unresolved limits, then update presentation/paper only where the
   new evidence supports the exact claim. Keep the signed-form submission pending.

## Decisions

- Reuse existing parsers, schema profiles, queue and owner-scoped review instead
  of introducing additional services or agents into extraction.
- Retain explicit source and review gates. A repair cannot convert an uncertain
  machine proposal into an automatically approved value.
- Do not claim reduced API cost without priced usage, or reduced human effort
  from an agent-operated review check.
- Any new quality campaign must retain all attempted sources, failures and costs.
  A development comparison cannot replace the frozen paired study or be described
  as an untouched holdout.

Status: implementation and validation in progress; no new accuracy result yet.

## Reproduced fixes and checks so far

- Three authored, explicitly headed single-row HTML/EML/XLSX cases failed before
  the native-table fix. All 38 native-table tests pass afterward. This affects
  discovery, not confirmed-schema native header mapping.
- An injected exception after two recorded model replies previously aborted the
  batch and prevented its completion marker. The regression now preserves those
  receipts, marks the failed document's attempt count unknown, processes the next
  source once, and retains process/disk failures as fatal. The broader 295-test
  product selection passed; the combined focused rerun passed 86 tests.
- Confirmed-schema summary, direct sample review links, accessible labels and a
  repeated-column shortcut passed eight component checks. Failure/review/export
  guards passed 32 focused frontend tests. TypeScript and changed-file lint passed.
- Startup reproduced the earlier scanned-PDF sample failure. Its original cause
  cannot be recovered because the old probe discarded the reason. New diagnostics
  preserve only closed-set failure codes, never arbitrary source/exception text.
  The OCR page budget is 30 seconds within a shared 60-second sampling deadline.
  The latter is checked between parsing operations and before the model call;
  the existing 120-second helper timeout remains the hard process bound. These
  changes are bounded tolerance and diagnostics, not proof of the original cause.
  114 related Python tests and the PowerShell preflight regression passed; a real
  native capability probe reported ready on 17 October at 11:32:49 UTC.

The in-progress three-call UI protocol uses two newly authored documents: a
single-row HTML order and a text order with duplicated rows and an absent tax ID.
Expected values and file hashes were written before model execution. These are
engineering fixtures and simulated review, not independent human evaluation.
