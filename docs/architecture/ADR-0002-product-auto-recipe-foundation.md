# ADR-0002: Owner-scoped product recipe approval foundation

Status: implemented as a single-host metadata pilot with explicit recipe selection. Automatic recipe matching and release are not implemented.

## Decision

A completed document review can create a **draft** recipe through
`POST /api/jobs/{jobId}/auto/recipes`. The request names the reviewed `runId`, `docId`,
`expectedReviewRevision`, and a family name. The server derives the recipe owner from the job; an
ownerless legacy job cannot create or read a recipe catalog. The draft records the reviewed field
types, groups, and source review identity and digest. It stores no extracted values or raw document
text.

`GET /api/jobs/{jobId}/auto/recipes` lists that owner's recipes. The
`/api/jobs/{jobId}/auto/recipes/{recipeId}` resource reads the immutable audit trail and accepts
`POST` actions `approve` and `disable` with `expectedRevision`. Approval rechecks the source review,
requires the schema to be unchanged, and requires `confirmedRowGroups` to name every linked group.
For a scalar-only recipe, that list is empty. The approved state is named `approved_shadow` to make
clear that it does not authorize automatic release.

Each revision is one full, immutable event file under the owner's hashed storage directory. It
records the actor, timestamp, action, source review, schema, previous event ID, and revision. A
fully written temporary file is published with an atomic hard link to the next revision filename;
two concurrent writers cannot both publish the same revision. The event itself contains the audit
record, avoiding a separate audit write.

## Current safety boundary

- Drafts require a completed review of a document that did not fail or become unsupported.
  Retained fields must have accepted typed values; `incorrect` and `not_present` decisions cannot
  seed a recipe. `remove` excludes a spurious field. Newly added fields need source evidence;
  legacy ungrounded additions remain in review and cannot seed a recipe.
- A linked group requires at least two reviewed columns with a shared row ordinal. Every column
  must share at least one row with another column. Approval additionally requires a reviewer's
  explicit group confirmation. This confirms only the reviewed example's ordinal relation; it
  does not establish extraction quality on new documents.
- The current review UI can add missed scalar fields. The recipe schema can represent linked
  columns, but adding a missed linked column in review and adjudicating full table geometry remain
  future work.
- A user can explicitly select one approved recipe and its current revision for a model-backed run.
  Selection rechecks the source review and owner, freezes the exact schema in a SHA-256-bound
  snapshot, and records the recipe revision, audit event, and snapshot digest in the run, document,
  and result receipts. The worker validates the snapshot and skips schema induction; it makes at
  most one value call per supported document. A stale, disabled, changed, or cross-owner recipe
  fails before the run starts. Invalid or ungrounded model values abstain with the selected schema
  preserved. Every output remains `needs_review`; an approved schema does not approve any value or
  linked row on a new document.
- A selected family name is an operator assertion, not a tested document classifier. There is no
  automatic family match or automatic release. Held-out extraction and review-cost evaluation is
  required before treating recipe reuse as a quality or cost improvement. Disabling a recipe after
  a run starts does not revoke that run's already frozen snapshot.

## Limits before multi-host use

The event store relies on a shared single-host filesystem. It fsyncs each event file before
publication, but a review update and a recipe approval are not one cross-resource transaction.
Each approval records a source digest; explicit selection rechecks the source before freezing the
run snapshot. Any future automatic matcher must also verify the source still matches or
move reviews and recipes into transactional metadata. Before multi-host deployment, move jobs,
reviews, and recipe revisions into the planned PostgreSQL store with owner-scoped queries and
transactional audit/outbox writes. Do not treat this registry as an extraction quality result.
