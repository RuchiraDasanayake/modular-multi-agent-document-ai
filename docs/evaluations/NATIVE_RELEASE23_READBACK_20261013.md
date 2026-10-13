# Native release readback — 13 October 2026

Classification: **supporting / keep**. This is live application regression evidence on synthetic fixtures, not an
extraction-accuracy or human-review study.

## Deployed revision and checks

Release `d50fc471ab4043e2c3cbefb4d9bf663f815e352e` was merged into `main` through PR 23. The integrated frontend
server suite passed **177 tests** and TypeScript passed. The release includes paid-request identity preservation,
review-status refresh, safe failed-document explanations, server rejection of failed-result review/export,
Office allocation checks, image-frame completeness checks, and passive recovery tooling.

The existing owned native Windows stack was stopped with **zero nonterminal queue jobs**. Its frontend was rebuilt
with the checked production-build script, then PostgreSQL, gateway, worker and frontend returned healthy. No Docker
was used. The independently running, frozen 2,000-source benchmark was not stopped or changed.

After deployment, an authenticated HTTP script checked the ten already reviewed synthetic cases recorded for the
planned recovery drill. These contain ten distinct source hashes and three distinct reviewed batch-export hashes;
several cases belong to the same batch. The source/review cases were not modified.

| Check | Observed result |
| --- | --- |
| Application health | HTTP 200 |
| Anonymous original and export requests | All 20 returned HTTP 401 |
| Authenticated original and export requests | All 20 returned HTTP 200 and matched the baseline byte hashes |
| Model-backed admission without a request key | HTTP 400 with the expected missing-key error |
| Model-backed admission with an invalid or overlength key | Both returned HTTP 400 with the expected invalid-key error |
| Broker jobs and durable dispatches | Unchanged: seven of each |
| Selected job run identities and states | Unchanged: two runs |
| Model calls submitted by these checks | Zero |

The negative admission requests used an existing uploaded file identity. They never sent a valid key. The separate
successful-admission check below used a new synthetic job; it did not modify those ten baseline cases.

## Concurrent paid admission and replay

A second, one-shot script created a new, explicitly named synthetic job with one 100-byte TXT invoice. It supplied
and confirmed two fields manually, so no schema-suggestion call was needed. The script pinned the production build
receipt and eight relevant source-file hashes, then durably reserved one request key before sending two concurrent
identical preview requests. It refused reuse of its own state/output files and did not create a replacement key.

Both initial requests returned **HTTP 202 with the same run identity**. Exactly one new broker job, durable dispatch
and product output appeared. The run succeeded with one document still requiring review. Its run, manifest and
sidecar receipts all recorded **one model call and one SDK attempt**: 461 input tokens and 174 output tokens, with no
recorded provider error. These are reported tokens, not a monetary charge or semantic quality score.

After completion, an exact-key replay returned the original completed run with HTTP 202. Changing the preview
options while retaining that key returned HTTP 409. Queue identities/states and the per-run model receipt remained
unchanged after both replays; the seven pre-existing broker and dispatch records were unchanged.

This is a live single-source regression for concurrent admission and replay. It does not prove exactly-once
execution at the provider across arbitrary process, disk or network failures. Unknown admissions still fail closed;
cross-job isolation, damaged claims, source/schema drift and failed-attempt reuse remain separately tested cases.

## Retained receipts

- Private script: `I:/DocAI-Runtime/release23-http-smoke/release23_http_smoke.py`; SHA-256
  `b0c0d0e3f8127fdcb2ce32b6048af0d8f49098515a731fbeb798605a237d11a7`.
- Private result: `I:/DocAI-Runtime/release23-http-smoke/result.json`; SHA-256
  `dd760336a746695617fee95dd8e397e70f4ab3479788dcc7d47de6fb76df7be4`.
- Preserved baseline: SHA-256 `a73d5120cf4a453ce60ab3981f335a6cd16eb36ed88eb5f44010ca80c4d9eccf`.
- Source case list: SHA-256 `df78a0ab487078d7f8561b8be31c34a55ec0d07222ab70f76acd562fff4901f6`.
- Frontend build receipt at this deployment: SHA-256
  `4b6c4aaf684404c0df557596bf6fee642547defa7c423f624e330d8a5caa0f43`.
- Offline capability receipt at this startup: SHA-256
  `97ffbde83b3ec9fc9898d777600841a8a8d50e23072400b36d5013b179a76caf`.
- Private paid-admission script: `I:/DocAI-Runtime/paid-idempotency-smoke-v1/paid_idempotency_smoke.py`; SHA-256
  `9684ae18cf70cc60b7eb89f969218cadcb739b46d47a4d6ca34021490af0f138`.
- Paid-admission receipt: `I:/DocAI-Runtime/paid-idempotency-smoke-v1/receipt.json`; SHA-256
  `ddb184c9d0e793c9771fa37c2c436f5c16d63124f40afe0b2c9bd78c2f81c413`.
- Synthetic TXT source: SHA-256 `eb3830b8630dc90a65461203fc59ec4a46296b9a6bac248e91d307f8b5ce4533`.
- Completed run / manifest / result SHA-256:
  `61fe5b5b89d640e8a6aaf072b2328c8a6e9d619ce01e2f8dc1130becdf20f200`,
  `83ccc59481915f91f08db8293374165b887f4c145610a0c71b94daab5094f63b`,
  `32eb44f0d891f7ccaa19e043313b802cf86d0fa6aa77146a780bc26587f674da`.

The script pins the deployed source revision and baseline hashes, refuses to overwrite its result, uses bounded
requests with no proxy/redirect/retry, and keeps credentials and response bodies out of its output. Root independently
checked the script/result hashes and the distinct source/export counts. Startup receipts are mutable operational
files; the hashes above identify this particular startup, not every later deployment.

This establishes readback, negative admission, and same-key paid replay for the selected fixtures. It does not establish browser
usability, general-purpose correctness, priced cost, or successful restoration from backup. The cold recovery drill
must wait until the benchmark releases the shared parser runtime.
