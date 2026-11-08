# Local product consolidation

Owner decision: 8 November 2026. The deliverable is a native Windows workspace
that runs locally from a configured data drive without Docker or cloud keys.

## Product contract

The primary flow is add documents, describe the fields, confirm meanings on a
sample, preview, review source evidence, then export structured records. A file
must produce a result or an explicit unsupported/failed state. Valid JSON is not
proof of correct values. Keep scalar alternatives, duplicate rows, source links,
revision checks, durable admission and reviewed-only exports.

Keep the existing gateway, PostgreSQL queue and extraction worker. They already
provide ownership and durable attempts. Avoid replacing them until a reproduced
problem justifies a change. Quarantine legacy research dashboards from the
operator flow; preserve frozen evidence and reconstruction tools.

## Execution order

1. Preserve the existing checkout and configure the active checkout on the data
   drive. Store binaries, models, dependencies, caches, logs and source artifacts
   there. Do not recursively move unrelated files or delete old evidence.
2. Research official model sources, licenses, actual release dates, Windows
   support, weight size and GPU memory. Trial compact general extraction and
   specialist OCR models; model download does not establish quality.
3. Start a loopback-only model service with cloud features disabled. Verify its
   owned process, executable, model digest and context settings. Start the native
   product only against that endpoint. Keep all required runtimes explicit.
4. Record generation settings, exact model identity and per-call provenance;
   compare repeated outputs instead of promising bitwise GPU determinism.
5. Reduce confirmed-schema setup duplication and secondary debug content in the
   UI. Preserve visible errors, review gates and source evidence.
6. Compare a fixed local baseline against candidate parsing/routing on a frozen
   development cohort, then freeze prompts, schemas, model digests and scoring
   before an untouched holdout. Report scalar and whole-row quality separately,
   failures, source evidence, latency, peak memory and review burden. Local API
   spend is zero; hardware, energy and human effort are not free.
7. Run the retained 2,000-original operational gate after a substantive extraction
   milestone, including every failed source. Keep development, operational and
   held-out quality evidence distinct. Do not tune on the submitted paper cohort.

## Milestone checks

- One launch command starts owned local services and reports missing resources.
- No configured remote model endpoint or cloud fallback in the local installation.
- Requested-field preview, review, restart persistence and downloaded export pass
  through the actual UI with local inference.
- Model receipts identify weights and configuration; repeated trial outputs and
  failures are reported with matching source and schema hashes.
- Targeted tests, frontend type checks and a production build pass.
- Stronger research claims require a paired held-out comparison and an ablation
  for each retained adaptive component. A negative result is preserved.

## Surface decisions

| Surface | Classification | Primary action | Acceptance |
| --- | --- | --- | --- |
| Product extraction/provider | core | keep | Local endpoint and auditable bounded requests |
| Native launcher | core | keep | Owned local model readiness and one launch path |
| Confirmed-schema UI | core | simplify | Current stage and one primary action are clear |
| Run/source receipts | research_evidence | keep | Stable source, schema, model and settings identity |
| Legacy service dashboards | legacy | quarantine | Optional research access outside product flow |
| Conference files | research_evidence | keep | Frozen submitted content preserved |

## Current limits

This plan does not certify arbitrary file understanding, general accuracy, a
learning benefit, hardware portability or production scale. Verify each before
promoting it. Authentication remains enabled on the local app. Larger batch
navigation and local-user authorization need a separate scoped pass.
