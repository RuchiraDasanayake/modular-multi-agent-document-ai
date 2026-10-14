# Reconstructing the quality240 inputs

The reconstruction manifest contains public corpus source identities, fixed
schemas, the registered schedule and execution profiles. These source-only
identities are intentionally retained for input reconstruction. Metric, incident
and union aggregates omit individual source identities and values. No source
documents, labels, predictions, credentials or original host paths are packaged.
The authors retain the original raw protocol and execution bundles privately.
Input reconstruction alone makes no extraction-quality claim.

The separately reported completed results are in the [paired quality report](../QUALITY240_RESULTS_20261014.md)
and [distinct-original union report](../VERIFIED_SOURCE_UNION_RESULT_20261014.md).
Machine-readable [primary results](aggregate-results.json),
[secondary diagnostics](secondary-diagnostics.json), [incident accounting](incident-accounting.json),
[source-union totals](source-union.json), [numeric-audit summary](numeric-audit-summary.json)
and [publication manifest](publication-manifest.json) preserve their scopes and hashes.

`reconstruction-manifest.json` SHA-256:
`d1ad99128791518b20573258fa8b0fba16c38cf80d8bfabc1b0c08afe09c5535`.
The original registered protocol SHA-256 is
`3cf41aac59be90d610a4479d1d9876bbf77894e9d55162983a8713b510594075`;
the original inventory SHA-256 is
`214def43738fd2bafb3102d80b4f26287e5b405140206abc767c361521e135ab`.
This portable JSON is explicitly **not** either original registered file.

## Acquire the creator sources

1. Obtain [VRDU at the recorded creator revision](https://github.com/google-research-datasets/vrdu/tree/04a4df7ac5cc694e51c48115c03fe428f0e240cc),
   commit `04a4df7ac5cc694e51c48115c03fe428f0e240cc`.
   Follow the creator's acquisition instructions. Match the manifest's
   `registration-form` and `ad-buy-form` filenames within their respective
   families. Keep creator terms and attribution with the local data; a code
   repository license alone does not establish every source document's reuse
   or redistribution rights.
2. Obtain NAVER CLOVA's [CORD v2 test Parquet at its recorded revision](https://huggingface.co/datasets/naver-clova-ix/cord-v2/blob/7f0115a4b758a71d6473b8d085751692da2fef98/data/test-00000-of-00001-9c204eb3f4e11791.parquet),
   revision `7f0115a4b758a71d6473b8d085751692da2fef98`, file
   `data/test-00000-of-00001-9c204eb3f4e11791.parquet`.
   Its expected size is **234,202,795 bytes** and SHA-256 is
   `51c65f1788faff392abe2a0b55b023eb23e9be551c509138eaa3a832514224e7`.
   See the [creator project](https://github.com/clovaai/cord) and
   [CC BY 4.0 attribution terms](https://github.com/clovaai/cord/blob/master/LICENSE-CC-BY).
   Attribute Park et al., *CORD: A Consolidated Receipt Dataset for Post-OCR
   Parsing* (2019), and NAVER CLOVA.
3. For CORD source reconstruction, read **only the `image` column** using
   PyArrow. `cord_test_NNNN.png` identifies zero-based Parquet row `NNNN`.
   Extract that row's original `image.bytes` without decoding/re-encoding the
   PNG. Select the exact 40 receipt rows listed in this manifest. The current
   `product_eval.datasets.cord_test` staging command also reads annotations;
   do not use it as a label-blind image-only acquisition step for a new study.
4. Before OCR, inference or reference access, verify each selected file's raw
   SHA-256 **and** byte size against its manifest row. A matching filename or
   visually equivalent image is insufficient. Do not repair, recompress or
   replace a mismatching source. Stop and investigate unavailable or different
   bytes. Keep all acquired source files outside the public code repository.

## Verify the reconstruction

Retain the source list and its order: **240 distinct raw hashes and document
IDs**, comprising **100 registration PDFs, 100 ad-buy PDFs and 40 receipt
PNGs**. The schedule has **480 slots**, exactly one `text` and one `candidate`
slot per source, with adjacent counterbalanced pairs. Reuse the explicit
schedule; do not reselect or reshuffle a cohort from available files.

The three packaged schema files must retain these exact raw hashes:

| Schema | SHA-256 |
| --- | --- |
| `schemas/registration-form.json` | `36c53ff90a098d05e1c2b8d2a7d35ebb3c29e6915f354658a03671d8d9a9dcfd` |
| `schemas/ad-buy-form.json` | `3fd04649edb13e920915d5e326522587a57af4abfd8499f8ae0d8f501dc73675` |
| `schemas/receipt.json` | `0ebeb253954b8726d9e46a3b24fbedfb30cb5b5f9957cde98580deee948f80b7` |

A source-only review compared this package with the original frozen protocol:
all source identities, sizes, filenames, schema hashes, 269 registered Python
source hashes, profiles and all 480 schedule entries agree. The packaged schema
bytes were rehashed. The manifest scan found no drive, UNC or home paths,
credential properties/prefixes, bearer values or private keys. This metadata
review did not reacquire/reopen original documents or inspect labels or
predictions; a new host must perform its own original-file verification.

## Execute and score a separately registered reproduction

Use the public repository
[modular-multi-agent-document-ai](https://github.com/RuchiraDasanayake/modular-multi-agent-document-ai)
at coordinator commit `1d1d55a501b007f6d815f4880517c3ec980b1607` for the
registered execution source. Verify its `idpo/` and `product_eval/` Python files
against `registered_python_source_sha256`; automatic line-ending conversion
can change raw hashes. Pin dependencies, OCR assets, interpreter and resource
limits in a new runtime receipt. Use fresh intake/OCR separately for both arms,
one worker, the supplied profiles, and the 960-per-arm/1,920-global request caps.

A new host uses different absolute paths and runtime receipts, so its inventory
and raw protocol hashes will differ. Record a **new** registration before any
model request, retaining the exact source-hash cohort, schemas and schedule.
The historical `quality_comparison.prepare` deliberately requires the original
inventory hash: remapping paths is not a drop-in invocation of that original
registration. Preserve its guard. Do not substitute this portable manifest for
the original protocol or describe a new run as the authors' sealed campaign.

The manifest preserves the initially registered provider profile. Any later
endpoint/authentication amendment is separate execution evidence. Configure a
currently authorized provider credential outside all manifests and source code,
record endpoint/model changes, and preregister them for the new run. A model
alias does not prove immutable backend weights or deterministic replay.

After both arms are permanently closed, use the public post-seal tools
`scripts/quality240_offline_analysis.py`, `product_eval/quality_scoring.py`,
`product_eval/quality_scoring_verification.py` and
`scripts/quality240_timing_usage.py` from published analysis revision
[`f2a8ef93b92757845c67fe86aeec5c3a4e14754c`](https://github.com/RuchiraDasanayake/modular-multi-agent-document-ai/tree/f2a8ef93b92757845c67fe86aeec5c3a4e14754c). Stage the registered execution source separately from these
later analysis modules; follow
`docs/evaluations/QUALITY240_OFFLINE_ANALYSIS_20261014.md`. The historical
verifier intentionally pins the original registration and will not certify a
new host's protocol hash as that original campaign. A new reproduction needs
its own explicitly bound registration and verification; preserve the original
scoring definitions and integrity checks.

Seal and independently verify every assigned prediction/failure outcome before
opening creator references. Retain all 240 sources per arm, including failures
and uncertain or unattempted slots. Never replay an uncertain paid attempt.
Use the declared creator-derived scalar and one-to-one whole-row metrics and
paired source-level family-stratified bootstrap; do not silently replace
matching rules or repair references toward predictions. Keep unknown usage and
missing timing explicit. Input reconstruction does not guarantee identical
provider outputs, latency, pricing or quality, and these three selected
families do not establish arbitrary-document or template generalization.

This package has completed publication review for the included metadata and
aggregates. Source documents and raw request/response bundles are not
redistributed here. The original-to-public hashes and documented transformations
are recorded in [publication-manifest.json](publication-manifest.json). The Git
revision containing this package identifies the publication; it does not change
the frozen execution or analysis revisions.
