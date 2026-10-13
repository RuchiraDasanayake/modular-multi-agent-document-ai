# NuExtract3 grouped-leaf follow-on: source lock

**Locked after rule commit `819d62e`; no inference or gold parsing.** The
[twelve-source manifest](nuextract3_group_leaf_dev12_sources.json) contains
four VRDU registration PDFs, four VRDU ad-buy PDFs, and four CORD v2
**development** receipt images. Its canonical JSON SHA256 is
`846d3bcc4cf1d02a2dcb10d1e5233b6881c2ec23d57d0a100936430972748a80`.
The independent [rule](nuextract3_group_leaf_alias_v1.json) canonical SHA256
is `343e6c2403d97c27d4cdf4207e005eb6d800397ff19d426474d6970d3b51d95b`;
the [run profile](nuextract3_group_leaf_run_profile_v1.json) canonical SHA256
is `c72c0c4e86499796a188c660ce0de03d04be25abe90d0ca3e469812c2eddcd62`.
Canonical JSON here means UTF-8, sorted keys, compact separators, no ASCII
escaping, and no NaN. The source manifest records every raw source, completed
OCR sidecar, full page-labeled OCR text SHA256, and the separate SHA256 of the
first 6,000 OCR characters eligible for the prompt. One selected form has
6,842 OCR characters and its prompt prefix is capped at 6,000.

Selection followed the [precommitted protocol](NUEXTRACT3_SEMANTIC_ALIGNMENT_FOLLOWON_PROTOCOL_20261012.md):
VRDU source-hash ranks 13–16 within each family, and the first four CORD
development receipts by source hash after the prior Graph lock's four CORD
items were excluded and a completed OCR sidecar had at least 200 text
characters. The source/sidecar bytes were rehashed. All 12 source hashes are
unique; **zero** source IDs or hashes overlap the prior
[Graph/NuExtract3 lock](../../product_eval/fixtures/docling_graph_v1_dev_sources.json)
(six examples and six scored), and **zero** CORD IDs or hashes overlap the
40-source reserved manifest. Cohort and gold-manifest byte hashes matched the
pinned values, but no gold row was parsed for selection.

VRDU OCR comes from completed v8 product runs, whereas the older six-source
NuExtract3 pilot used v5 sidecars. A future difference from the old pilot
cannot be attributed solely to the alias rule. The meaningful paired check
on this new set is the original exact/alias scorer versus the new grouped-leaf
scorer on the **same sealed replies**. The original **0/26** linked-pair
result remains unchanged. The model-generated schema and its self-template
values must be scored and reported separately.

This is a source/profile lock, not a runnable or scored result. Before any
model call, the future harness still needs a reviewed immutable code commit,
per-call request hashing, model/server byte rechecks, resource/headroom
preflight, and an explicit run sequence after competing inference completes.
No source content, prompt, reply, or gold annotation was committed.
