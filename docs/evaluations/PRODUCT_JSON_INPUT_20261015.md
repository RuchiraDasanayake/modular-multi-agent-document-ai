# Product JSON input guard — 15 October 2026

Scope: the product JSON reader is **core**, with primary action **simplify**
through defect cleanup. Shared research `IntakeAgent` behavior is unchanged.
This change applies to product extraction and bounded JSON schema samples.

## Actual findings

A read-only audit of 20 authored malformed JSON cases did **not** reproduce the
suspected batch abort from non-string page text. Those cases failed within the
existing OCR exception boundary, the following text original completed, and
`run.json` was terminal. The correction is input validation and accurate
classification, not a claim that this existing catch was absent.

The audit did reproduce these gaps:

- Invalid or duplicate page IDs could become `needs_review` artifacts with invalid source-page metadata.
- Non-string source document IDs were accepted.
- A 203,968-byte JSON original allocated 5,001 `Page` objects before the 50-page limit rejected it.
- A 9,952-byte array allocated 129 logical documents, with no JSON entry-count bound.
- One original could fan out into many value-model calls while queue admission counted uploaded originals.

## Implemented boundary

`idpo/product_auto/json_input.py` reads at most 20 MiB and accepts one document
object or a nonempty array. It validates the entire container before constructing
any `Document` or `Page`: at most 5,000 entries, at most 50 pages per entry,
nonempty string document IDs, string page text, and string-or-null raw text.
Missing page IDs retain the existing one-based default. Explicit page IDs must
be unique positive safe integers and are preserved without renumbering.

Duplicate JSON properties, nonstandard constants, nonfinite numbers, malformed
shapes and invalid Unicode are rejected. Supplied image paths and metadata
remain ignored and stripped from executable product objects. Canonical entry
receipts still hash the complete original entry, including ignored metadata.
Valid entry order, source indices, canonical hashes and derived document IDs
retain their existing definitions.

Extraction preflights all selected originals and retains only bounded count/hash/
outcome receipts. It does not cache parsed containers. Valid JSON entries count
as logical documents; an invalid original counts as one explicit failure unit.
A run exceeding 5,000 logical units rejects before creating its run directory or
calling a model. Each admitted JSON source is read and hash-checked again before
construction, so a later source change cannot increase its admitted fan-out.

A malformed container yields one `parse_failed` original. Too many entries yield
one unsupported `json_document_limit_exceeded` original; too many pages yield
one unsupported `too_many_pages` original. The complete container abstains if
any entry is invalid or exceeds a limit; earlier entries are not partially
processed. Other admitted originals continue.

JSON schema samples use the same complete validation and hash check, then build
only the first two logical documents for the existing bounded excerpts.

The native dispatch-v4 admission path separately reserves a conservative budget
from a standard JSON array's raw length, with at least one unit per original.
It may reserve more units, or reject earlier, when a malformed array will become
one product failure. This overreservation is intentional. Older dispatch queue
accounting remains a separate compatibility boundary.

## Verification

The initial behavioral suite failed **12 tests** with one positive control before
the guard. The expanded focused suite passed **112 tests**, including 32 JSON
guard regressions and the existing product, brief and confirmed-schema checks:

```powershell
python -m pytest idpo/tests/test_product_json_input.py `
  idpo/tests/test_product_auto.py `
  idpo/tests/test_product_auto_brief_draft.py `
  idpo/tests/test_product_auto_brief_preview.py `
  idpo/tests/test_confirmed_schema_routing.py -q
```

Checks cover malformed page types, unsafe/duplicate page IDs, standard JSON
constants, duplicate properties, lone surrogates, complete-container validation
before allocation, the 5,000-entry boundary, zero model calls on global excess,
source changes, two JSON logical documents plus a text original, preserved
canonical receipts/IDs, stripped server paths, and bounded sample construction.
Ruff checks pass for all modified product parser files and their focused tests.
The combined core-reply and JSON workflow suite passed **245 tests** after both
sets of fixes were applied together.

No paid provider, image OCR engine, sealed prediction, benchmark reference or
conference artifact was used or changed. These are structural safety and
accounting checks; they establish no new extraction accuracy or cost result.

