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
| Paired extraction quality | [Completed on 13–14 October UTC](QUALITY240_RESULTS_20261014.md): all 480 slots terminal, sealed and independently verified before reference access. Scalar macro recall 64.77% text / 65.09% selective; whole-row macro 34.13% / 41.74%; both macro difference intervals include zero. Receipt rows improve, ad-buy rows decline. Valid complete outcomes: 222/240 text, 217/240 candidate; 14 uncertain sources per arm. |
| ICORE accounting | The quality campaign is permanently closed. Provider failures and unknown usage remain in its denominators; known tokens total 878,447 text / 1,597,180 candidate, with usage unknown on 13/16 attempts. No USD cost or current provider-availability guarantee is inferred. The separate strict-v2 development trial remains an incomplete diagnostic and was not promoted. |
| Distinct-source volume | [Verified union](VERIFIED_SOURCE_UNION_RESULT_20261014.md): 2,240 selected, 2,225 model-attempted, 2,147 valid complete and 2,146 non-null complete originals across the operational study and source-disjoint candidate arm; baseline excluded. Structural coverage does not establish semantic correctness or replace the failed original operational gate. |
| Latest release accuracy | Both frozen extraction studies use their registered implementations. Their measurements cannot be attributed to later UI/provider fixes. JPEG packing checks and synthetic v2 checks are engineering evidence only. |
| Browser workflow | Sign-in, creation, upload, schema confirmation and existing review rendering verified. Authenticated exports pass; browser file-save delivery remains unconfirmed. |
| Camera-ready paper and slides | Official-template working drafts and verified paired reporting inputs are prepared. Final manuscript/reviewer-response and slide generation, rendering and visual inspection remain. |
| Author package | Editable Word completion/declaration forms delivered privately. Department/city wording, corresponding author, secondary contacts, author approval, consent, signatures and dates remain author input. External submission remains author-controlled. |

Release work is limited to these gates and reproducible defects found while completing them. Additional agent loops,
service migrations and unmeasured parser replacements are not prerequisites for this conference package.

## Confirmed saves and schema editing

The review UI previously issued a second document read after a successful save.
If that read failed, the screen reported a failed save and retained the previous
revision even though the server had committed the review. The save response now
includes the verified document and audit history, which the screen applies
directly. Existing response fields remain available. The regression checks the
returned revision, audit event, corrected values and exclusion of private paths.

Schema setup now uses a native disabled fieldset during draft saving, AI field
suggestion, extraction admission and active extraction. This prevents edits made
while a request is pending from being silently replaced by its earlier response.

Validation after these changes: 194 frontend tests passed, five skipped; TypeScript
and targeted ESLint passed with one existing navigation warning. The native
production build passed. A read-only authenticated check confirmed the retained
synthetic PDF export still has revision 2 and SHA-256
`125909f9b053ab6f1458e58a59a4c35640c888c2eb47a6cf34b933c49e8e2e2b`.
That check made zero model calls. Windows browser control stopped because it could
not reliably identify the current URL, so it supplies no new browser-delivery
evidence. The paired quality study subsequently completed with its original frozen code; see the result report above.

The latest dated main revision is `f2a8ef93b92757845c67fe86aeec5c3a4e14754c`.
Its retained frontend build is `vI8XZs2w6kUsZ3w3gFwjp`, completed 14 October at
13:36:56 UTC, with source fingerprint
`ed84fc98ac78f5df49769912c09547f08c962158fb813debe80faae8f62bb8d3`.
These 194 passed/five skipped frontend checks and the matching production build
are implementation evidence. Later research-runtime/recovery clarifications do
not change the frozen study or validate the missing historical bundles.
Post-evaluation native verification passed the current-byte fingerprint check,
four verified service identities, three owned listening ports and worker health. A fresh authenticated
GET of the retained reviewed PDF export matched
`125909f9b053ab6f1458e58a59a4c35640c888c2eb47a6cf34b933c49e8e2e2b`
with zero model calls. Private verification receipt SHA-256:
`5ac9779928ea70a6ec89bc5b5de2cab2c3baba33bf5a1c9bdc5bbf4ab79cd968`.
Documentation/evidence edits were still being prepared during that check;
final clean-main verification follows their publication merge.
Chrome/Edge file selection and saved-download delivery remain unverified after
Windows URL control stopped and the user could not perform the manual check.
