# Release verification — 14 October 2026

Classification: `research_evidence`, keep. This records the tested release changes and the remaining sign-off gates.
It does not replace either frozen extraction study or certify general-purpose accuracy.

## Changes verified together

- Incomplete, refused or malformed model output now produces a failed extraction. A complete, valid all-null reply
  remains a reviewable result. These cases are distinguished by the actual decoder outcome.
- Historical artifacts with an exact known model-failure reason are treated as failed after artifact verification.
  Their original bytes remain unchanged. Review, export, preview-to-batch admission and recipe reuse reject them.
  Historical list summaries may retain their original status until the document is opened.
- Failure messages explain the cause and warn that a previous request may have been charged. They do not retry it.
- The optional [full-page JPEG95 profile](JPEG95_VISUAL_ENCODING_20261014.md) reduces encoded payload size while
  preserving the existing routing, geometry and complete-page admission checks. PNG remains the default.
- Integration tests cover [keyed response v2](STRICT_VALUES_V2_CAPABILITY_20261014.md) through both PNG and JPEG
  preparation. This profile remains opt-in; real-document improvement has not been established.

## Software and running-product checks

Tested application commit: `f9cdf9b` (the subsequent documentation commit does not change application files).

| Check | Result |
| --- | --- |
| Eight focused Python suites: automatic extraction, confirmed schemas, strict v1/v2, visual boundary/workflow/JPEG and provider formatting | 160 passed |
| Full frontend `npm run test:server` | 184 passed |
| TypeScript `tsc --noEmit` | Passed |
| Touched Python runtime files: Ruff `E9,F63,F7,F82` | Passed |
| Native launcher PowerShell fixture | Passed |
| Production frontend build through the native build script | Passed |
| Native PostgreSQL, gateway, frontend and persistent worker | Verified running; worker healthy |
| Authenticated existing preview and batch exports | HTTP 200; both exactly match their reviewed references |
| Export review provenance | Completed review; all exported fields retain `human_verified` provenance |
| Frontend and gateway/database health | HTTP 200; healthy |

The authenticated export check made zero model requests. It verifies retained reviewed data after this release;
it does not constitute a fresh extraction or browser interaction test. Browser sign-in and review/export screen
verification remain pending. Existing [nine-format workflow](NATIVE_NINE_FORMAT_SCHEMA_FLOW_20261013.md),
[owner-isolation](NATIVE_OWNER_ISOLATION_HTTP_20261013.md) and
[cold recovery](NATIVE_COLD_RECOVERY_20261014.md) evidence retain their original scope and versions.

Production build ID: `71MF0ePeBmb3WLLq14_9P`. Source fingerprint:
`a738f5cf7d930685a277d6978e196dc2776d1daf286531d6c6d5efb6b7528615`.
Private build-receipt SHA-256: `f6986f58b3bfaa61604bb86621045cf27a72337032d4c73077e812370b48d0e1`.
Private live-export verification SHA-256: `f22e5d8f64df02fc40dcaea30845b93aadd7c38c7549a8dad6c17903c1cf7e46`.

## Evidence and conference gates

| Gate | Current evidence / remaining action |
| --- | --- |
| 2,000-original operational execution | Completed and independently verified: 1,987 originals began model requests; 1,930 strict/full-coverage outputs. All-source success gate failed. [Report](MODEL2000_VERIFIED_OPERATIONAL_20261013.md). |
| Paired extraction quality | Frozen 240-source comparison interrupted, with 43 text and 44 candidate sources sealed. Labels remain unopened. Resume only unstarted sources under the unchanged protocol, then seal, verify and score. |
| ICORE availability | The first request in the separate 25-source strict-v2 development trial returned HTTP 429 on 14 October. It stopped after one attempt; 24 sources remain unstarted. Usage is unknown. No automatic retry or default promotion. |
| Latest release accuracy | The completed 2,000-source campaign predates these fixes. Its measurements cannot be attributed to this release. JPEG packing checks and synthetic v2 checks are engineering evidence only. |
| Browser workflow | Await normal sign-in, then verify the rendered review/export experience. API checks above already pass. |
| Camera-ready paper and slides | Official-template working drafts include verified operational results and corrected simulation. Paired quality results and final layout verification remain. |
| Author package | Confirm department/city wording, corresponding author, required secondary contacts, all-author approval and declaration signatures. External submission remains author-controlled. |

Release work is limited to these gates and reproducible defects found while completing them. Additional agent loops,
service migrations and unmeasured parser replacements are not prerequisites for this conference package.
