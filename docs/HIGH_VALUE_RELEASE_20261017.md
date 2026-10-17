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

Status: engineering implementation and the authored UI workflow check are
complete. Independent quality evaluation remains pending; no new general-document
accuracy or monetary-cost result is established.

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

## Authored UI workflow result

The saved protocol at `I:\DocAI-Runtime\high-value-20261017\ui-protocol.json`
fixed source hashes and expected values before any model call. Two newly authored
sources covered a single-row HTML order and a text order with duplicate linked
rows and an absent tax identifier. The in-app browser exercised upload, confirmed
schema, preview, source inspection, review, remaining-file extraction and export:

- One `strict_confirmed_values_v1` preview and one
  `strict_confirmed_values_v2` preview of the HTML source each matched the
  prewritten values. A v2 batch run of the text source also matched its
  prewritten values, including all three linked rows in order. Each run used
  one model call, for three calls total; the saved receipts show no retries.
- The previews still required review because no values were grounded for
  automatic confirmation. The text run required review for ambiguous evidence.
  The agent inspected the authored source and used **Correct** for the linked
  rows, without inventing an evidence location. Review changed no extracted
  values and explicitly removed the absent tax identifiers.
- Two downloaded reviewed JSON files and one reviewed JSONL file were saved,
  parsed and checked against expected values. Their hashes and run receipts
  are in `I:\DocAI-Runtime\high-value-20261017\ui-verification.json`.

The UI check used the in-app browser; Chrome and Edge remain unverified. The
review was agent-simulated, not an independent human study. The three authored
calls and 147 passing focused evaluation tests are engineering evidence only;
they do not establish heterogeneous-document accuracy, human-effort savings,
throughput or priced cost per correct document.

## Deployed release readback

The output-limit guidance change passed its targeted server/component tests,
TypeScript and lint checks, then a production build and native startup on
17 October. The deployed browser retained the confirmed schema and completed
review after restart. A newly downloaded reviewed JSONL file matched the
pre-restart export byte for byte (SHA256
`5c72d94ebb7d8ee63d23059d51911043fa919e7c87e0a80760cfec9729f1f26a`).
This readback required no model calls. The specific length-limit message was
tested with verified-artifact fixtures, not a newly induced provider truncation.

The release is merged into `main` through PR 45. Its private build and readback
receipt is `I:\DocAI-Runtime\high-value-20261017\deployment-readback.json`.
The independent operational campaign continued during the frontend build;
its elapsed time must not be presented as isolated processing throughput.

## User-requested evaluation pause

The newer frozen 2,000-source campaign stopped at a safe boundary on 17 October
after the user requested a processing pause. No requests remain running. There
are 697 accounted-for sources (694 sealed and three uncertain), 1,303 unstarted,
and 678 valid complete outputs. These are provisional processing counts, not
accuracy results or a completed operational study. Reference labels remain
unopened. The campaign has no final seal and was not scored.

The durable stop reason is `user_requested_pause`. The frozen CLI does not
currently accept this reason with `--acknowledge-stop`; continuation requires an
audited operator-pause procedure. Do not reset uncertain outcomes, replay paid
requests, substitute a provider-error reason or silently clear the stop.

The [GPU screening](evaluations/GPU_OCR_SCREENING_20261017.md) is complete and
CPU OCR remains the production default. Neither this screening nor the paused
campaign changes the completed-study claims in the paper and slides. See the
[final conference handoff](CONFERENCE_HANDOFF_20261017.md).
