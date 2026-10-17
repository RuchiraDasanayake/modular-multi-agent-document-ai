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
