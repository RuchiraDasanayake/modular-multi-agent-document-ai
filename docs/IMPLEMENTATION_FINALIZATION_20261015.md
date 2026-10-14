# Implementation finalization — 15 October 2026

Classification: `supporting`; primary action: `keep`.

This pass closes reproduced defects in the native extraction, schema setup and reviewed-export workflow.
The deployment target remains native Windows with PostgreSQL, the gateway, the frontend, a separate worker
and configured filesystem storage. The completed extraction studies retain their original implementations
and results; new regression checks are engineering evidence.

## Task list

| ID | Reproduced defect | Owning surface / classification / action | Acceptance check | State |
| --- | --- | --- | --- | --- |
| F1 | A failed schema read appears to be no saved schema and enables discovery extraction | Frontend setup / core / simplify | Unknown setup blocks writes and paid admission; explicit retry restores the saved schema; a successful empty response preserves discovery | Implemented; focused and combined checks pass |
| F2 | Example textarea removes the newline after Enter | Frontend setup / core / simplify | Raw multiline edits survive; save normalizes at most three nonblank examples; excess examples are rejected without truncation | Implemented; focused and combined checks pass |
| F3 | Deeply nested or invalid Unicode model JSON can abort the remaining batch | Product reply decoder / core / simplify | Reject malformed replies before artifacts; only that document fails; subsequent sources finish and run completion is recorded | Implemented; combined checks and independent review pass |
| F4 | Invalid typed visual scalars can produce an artifact the review API refuses | Product visual decoder / core / simplify | Reject invalid types before source coverage is claimed; valid coerced values stay review-only | Implemented; combined checks and 17-case frontend parity audit pass |
| F5 | Confirmed Unicode IDs are rewritten and quote matching differs between Python and the frontend | Product value parser / core / simplify | Preserve exact confirmed IDs and distinct IDs; source evidence obeys the same conservative lowercase comparison | Implemented; combined checks and 17-case frontend parity audit pass |
| F6 | Multiple logical documents from one supported JSON original cannot be exported as a reviewed batch | Reviewed export / core / simplify | Export unique logical document IDs in selected-original order; every original is covered and every logical document reviewed; retain ownership, source/hash and resource guards | Complete; combined checks and authenticated native integration pass |
| F7 | A small JSON container can create many model-call units while admission counts one original; malformed page identities can create unusable artifacts | JSON intake and queue admission / core / simplify | Bound product JSON before object construction and model calls; preflight at most 5,000 logical documents/run; new dispatches seal that planned budget, legacy dispatches retain their original semantics | Complete; combined checks, independent review, native queue count and zero-call admission rejection pass |
| F8 | The UI assumes one result per original and blocks a fully reviewed JSON preview/export | Frontend review readiness / core / simplify | Multiple logical rows can complete; missing original coverage, repeated result IDs and any unreviewed/failed result remain blocked; progress distinguishes results from files | Implemented; failing-first component/helper tests and combined checks pass |
| V1 | Combined release validation | Product runtime / core / keep | Relevant Python and frontend suites, TypeScript, targeted lint, production build and authenticated synthetic native integration pass | Complete; 414 Python and 235 frontend tests pass; production build and three-call ICORE integration pass |
| V2 | Publish and deploy | Release evidence / supporting / keep | Reviewed commits reach main; matching native build, verified service identities and reviewed export readback pass | Native deployment and readback verified; main publication recorded by this change's merge |

## Reproduction and scope

The regressions use authored synthetic inputs and fake provider replies. The final authenticated integration uses
three real Luna 6 calls over separate authored invoices. These checks do not infer that these defects caused
the completed cohort's extraction errors. The UI regressions execute the actual component callbacks using
deterministic hooks and API promises; they do not certify browser layout or React scheduling.
Provider prompts, selected models and routing profiles are outside these defect fixes.
The [release verification](evaluations/RELEASE_VERIFICATION_20261015.md) records the combined checks, native
build and complete reviewed-export evidence.

Before a newly found issue enters implementation, record a concrete reproduction, affected contract and
bounded acceptance check. F7 was accepted after an authored 350-byte JSON source produced five logical
documents and five fake value-model calls while its queue budget counted one original. A separate malformed
text-type batch-abort hypothesis did not reproduce: all twenty authored cases retained terminal outcomes
and continued to the next source. That non-finding is not reported as a repaired crash.

## Research and reuse decisions

Use the existing bounded standard-library JSON decoder and shared typed-value checks across reply profiles.
Python documents resource risks when decoding untrusted JSON; RFC 8259 permits parser resource limits and
describes interoperability problems with unpaired UTF-16 surrogates. The new synthetic regressions exercise
those concrete failure modes. See [Python JSON](https://docs.python.org/3.10/library/json.html) and
[RFC 8259, sections 8.2 and 9](https://www.rfc-editor.org/rfc/rfc8259.html#section-8.2).

Preserve raw controlled textarea input during editing and normalize at save time, following the
[React textarea contract](https://react.dev/reference/react-dom/components/textarea#my-text-area-caret-jumps-to-the-beginning-on-every-keystroke).
No extra form library, parser dependency or agent service is required for these repairs.

## Remaining human and deployment boundaries

The [conference technical handoff](CONFERENCE_HANDOFF_20261014.md) is already prepared.
Author details, approval, consent, signatures and external submission remain with the authors.
Windows computer input was stopped with the physical Escape key during this continuation.
Browser file selection/saved-download delivery and native Microsoft Word/PowerPoint execution remain unverified.
The native single-host deployment, fixed-schema studies and these regressions do not certify unrestricted
accuracy, lower USD cost, multi-host operation or high availability.
