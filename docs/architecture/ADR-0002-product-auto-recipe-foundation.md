# ADR-0002: Owner-scoped product recipe approval foundation

Status: implemented as a single-host metadata pilot. Recipe matching and automatic release are not implemented.

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
- No extraction run reads this catalog. Recipe matching, calibration, and release policy require
  separate implementation and held-out evaluation. A document's existing `needs_review` state is
  unchanged.

## Limits before multi-host use

The event store relies on a shared single-host filesystem. It fsyncs each event file before
publication, but a review update and a recipe approval are not one cross-resource transaction.
Each approval records a source digest; any future matcher must verify the source still matches or
move reviews and recipes into transactional metadata. Before multi-host deployment, move jobs,
reviews, and recipe revisions into the planned PostgreSQL store with owner-scoped queries and
transactional audit/outbox writes. Do not treat this registry as an extraction quality result.
