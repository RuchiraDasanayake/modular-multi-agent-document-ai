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

The negative admission requests used an existing uploaded file identity. They never sent a valid key, so this check
does not demonstrate a successful paid admission/replay over HTTP. Concurrency, changed payloads, cross-job identity
and replay behavior are covered by the server regression tests; a live successful-admission check is separate.

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

The script pins the deployed source revision and baseline hashes, refuses to overwrite its result, uses bounded
requests with no proxy/redirect/retry, and keeps credentials and response bodies out of its output. Root independently
checked the script/result hashes and the distinct source/export counts. Startup receipts are mutable operational
files; the hashes above identify this particular startup, not every later deployment.

This establishes readback and negative-admission behavior for the selected fixtures. It does not establish browser
usability, general-purpose correctness, priced cost, or successful restoration from backup. The cold recovery drill
must wait until the benchmark releases the shared parser runtime.
