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
it does not constitute a fresh extraction or browser interaction test. Subsequent browser checks are recorded below.
Existing [nine-format workflow](NATIVE_NINE_FORMAT_SCHEMA_FLOW_20261013.md),
[owner-isolation](NATIVE_OWNER_ISOLATION_HTTP_20261013.md) and
[cold recovery](NATIVE_COLD_RECOVERY_20261014.md) evidence retain their original scope and versions.

Production build ID: `71MF0ePeBmb3WLLq14_9P`. Source fingerprint:
`a738f5cf7d930685a277d6978e196dc2776d1daf286531d6c6d5efb6b7528615`.
Private build-receipt SHA-256: `f6986f58b3bfaa61604bb86621045cf27a72337032d4c73077e812370b48d0e1`.
Private live-export verification SHA-256: `f22e5d8f64df02fc40dcaea30845b93aadd7c38c7549a8dad6c17903c1cf7e46`.

## Browser-discovered workspace correction

Classification: product UI, `core`, simplify; research navigation, `supporting`, keep.
Browser verification reproduced two misleading entry points: sign-in opened an unavailable research dashboard,
and the job list displayed research-only processing counters for completed product extractions.

Sign-in, sign-up and job links now open the extraction workspace. Uploads are available beside schema setup using
the existing bounded upload helper and its request-key-preserving retry behavior. The jobs list shows file counts;
actual extraction and review states remain inside each job. Separate research tools are collapsed, and advanced
job settings retain access to job renaming and the research pipeline. No extraction algorithm or stored result changed.

Observed in the rebuilt production browser:

- Sign-in opened document jobs; a new job opened the extraction workspace directly.
- Two authored text files uploaded together; both appeared in the sample/selection lists without a page reload.
- A string field and a decimal field with explicit meanings were saved as draft revision 1 and confirmed as revision 2.
- Preview became available; applying the remaining file stayed disabled without a reviewed preview.
- The new job had exactly two stored sources and zero extraction runs. These browser checks made no model calls.
- An existing completed human review displayed its source quotes, decisions, corrected values and review history.
- The batch-download button was exercised without a page error, but the browser automation did not observe a
  download event or a saved file. Browser file delivery is not certified by this check. Authenticated preview and batch
  export checks independently returned the exact reviewed reference data again after the rebuild.

Validation: 36 focused upload/request-key/schema-gate/export tests passed using scratch space on the data drive;
TypeScript, targeted ESLint and the production build passed. The first default-scratch test run had three failures
while the system drive was full; it is not used as passing evidence. The npm cache was moved to the data drive with
its original path preserved by a junction. No application source or document was removed for that move.

Browser-tested production build: `O6IILvVa2cvFdCVMLK23W`; source fingerprint
`7262aa4db0d37e87aaaa29a2cdee67214d39b2cc0848c73acda0f13f52641292`;
build-receipt SHA-256 `bc2ab06c762a065177f12f0969f548bfbea01aa3fa504caae5f53a4422376c53`.
The new export-check receipt has the same content hash as the earlier check above.

The post-merge source fingerprint check required a new build after checkout. The final production build from
application commit `d06f984286aa7b3e6cad5937cf193fdf53dbe384` is `GZmahZ4Wgx04zLAT6YkaF`, completed
14 October at 07:46:29 UTC. Its source fingerprint is
`0ad6c301788e6a59636d867718533c61b932ff7db109d624dcd82a725ebaf328`, and build-receipt SHA-256 is
`c366bbba5dc12165477caa069c497c08e7c075be3ea80003035a1fded3f6946c`.

## Evidence and conference gates

| Gate | Current evidence / remaining action |
| --- | --- |
| 2,000-original operational execution | Completed and independently verified: 1,987 originals began model requests; 1,930 strict/full-coverage outputs. All-source success gate failed. [Report](MODEL2000_VERIFIED_OPERATIONAL_20261013.md). |
| Paired extraction quality | Frozen 240-source comparison stopped again on rate limiting after a bounded resume. Text: 44 sealed, 3 uncertain, 193 unstarted; candidate: 46 sealed, 2 uncertain, 192 unstarted. Valid/full-coverage outputs: 44 text, 45 candidate. Labels remain unopened. Resume only unstarted slots once availability is restored, then seal, verify and score. |
| ICORE availability | The separate 25-source strict-v2 development trial stopped after its first request returned HTTP 429; 24 sources remain unstarted. A later quality-study resume completed additional work before another 429. Latest stop receipt: `8be599b1d363318843eac102cce1445a30c0c2e0675e9c536092cf6cf90a286d`. No automatic retry or default promotion. |
| Latest release accuracy | The completed 2,000-source campaign predates these fixes. Its measurements cannot be attributed to this release. JPEG packing checks and synthetic v2 checks are engineering evidence only. |
| Browser workflow | Sign-in, creation, upload, schema confirmation and existing review rendering verified. Authenticated exports pass; browser file-save delivery remains unconfirmed. |
| Camera-ready paper and slides | Official-template working drafts include verified operational results and corrected simulation. Paired quality results and final layout verification remain. |
| Author package | Confirm department/city wording, corresponding author, required secondary contacts, all-author approval and declaration signatures. External submission remains author-controlled. |

Release work is limited to these gates and reproducible defects found while completing them. Additional agent loops,
service migrations and unmeasured parser replacements are not prerequisites for this conference package.
