# NuExtract3 grouped-leaf alignment: source-disjoint follow-on protocol

**Status: rule and protocol precommitted; no new sources selected and no model
calls made.** This is a tuned **secondary development candidate** prompted by
the prior blind-schema diagnostic. It cannot revise that locked result:
NuExtract3 matched 22/53 reference fields but **0/26 linked field pairs** under
the original predeclared alias ontology. Its 13/32 scalar and 24/43 complete-row
results came from a *different, reference-schema value arm*. The original
[protocol](NUEXTRACT3_LOCAL_DEV_PROTOCOL_20261012.md),
[result](NUEXTRACT3_LOCAL_DEV_RESULT_20261012.md), and
[ontology](../../product_eval/fixtures/graph_schema_aliases_v1.json) remain
unchanged.

## Decision being tested

The previous model produced explicit repeated objects on both ad-buy and both
receipt documents, but its nested leaf names often differed from the narrow
reference IDs. A scorer that recognizes common leaf names **within the same
declared repeated-object group** might measure linked schema structure more
faithfully. This is a scoring hypothesis, not proof of correct extracted
values, field meaning, row identity, or source evidence.

The normative [grouped-leaf rule](nuextract3_group_leaf_alias_v1.json) is
family-independent and contains no VRDU/CORD gold ID table. Its SHA256 is
`343e6c2403d97c27d4cdf4207e005eb6d800397ff19d426474d6970d3b51d95b`
over canonical UTF-8 JSON: parse with duplicate keys rejected, then serialize
with sorted keys, no extra whitespace, `ensure_ascii=False`, and `allow_nan=False`.
The harness must verify this digest and the commit containing the rule before
source selection. The canonical hash avoids Windows checkout line-ending
differences. A changed rule creates a **new candidate version** and cannot be
used to reinterpret prior outputs.

### Deterministic canonicalization and matching

1. Project only root-reachable template leaves and keep the **nearest explicit
   array-of-objects parent path** as each predicted leaf's group ID. A nested
   object alone, a scalar array, or table-looking OCR text is insufficient.
   For a reference `array[object]` field, use the annotated row group; if the
   reference format has exactly one implicit row group, use one synthetic
   reference group. If multiple groups cannot be identified, mark linked-pair
   scoring unavailable for that source rather than guessing.
2. Normalize each eligible leaf name with the rule's NFKC, camel-boundary,
   casefold, and separator steps. Look it up in the fixed slots. Unlisted names
   use only normalized **literal equality**. `price`, `item_price`, and similar
   unqualified leaves map to `price_unspecified`; they never equal
   `unit_price` or `line_amount`. Thus the earlier `unit_price` versus CORD
   `item_price` example remains unproved semantic equivalence.
3. Apply the same rule to prediction and reference names. Exact ID, original
   frozen ontology, and this new rule are **three separate score modes**.
   Require unique one-to-one slot matches. If two leaves on either side map to
   one slot, count a collision and leave it unmatched; never select a leaf
   using a value, document family, confidence, or reference row. A linked pair
   hits only if both reference fields uniquely match predicted leaves under
   one identical non-null predicted group path. Do not match leaves across two
   model groups merely because both are called `items`.
4. Report the raw names and group paths, normalized names, chosen slots,
   unmatched/ambiguous counts, shape and type agreement, matched linked fields,
   and pair hits. Keep **all** annotated linked pairs in the denominator. The
   slot match is a lexical/structural diagnostic; ambiguous semantics require
   blinded human adjudication from source content before any quality claim.

Example: `Document.receipt.line_items.quantity` and
`Document.receipt.line_items.unit_price` share a predicted group and map to
different slots. `Document.receipt.other_items.quantity` does not share that
group. A reference `item_quantity` maps to `quantity`; a reference `item_price`
maps to `price_unspecified`, so it does **not** receive credit for the model's
`unit_price` without separate source-backed adjudication.

## Chronological locks and source exclusion

1. Commit this rule/protocol **first**. Only after that commit, select a new
   development cohort using source bytes/metadata and existing completed OCR,
   without reading labels, model responses, or scorer results. The candidate
   cohort is 12 public documents: four VRDU registration forms, four VRDU
   ad-buy forms, and four CORD v2 **development** receipts. For each VRDU
   family, sort the pinned 2,000-source cohort by `(source_sha256, doc_id)` and
   take ranks **13–16** (one-based). This avoids the six lowest-hash pilot
   sources per family. For CORD, sort the 60 development rows by the same key;
   require an existing completed OCR sidecar with at least 200 characters,
   exclude every source in the prior Graph lock, then take the first four.
   No replacement based on gold content or model output is permitted.
2. Verify all 12 raw SHA256 hashes against cohort records and compare them
   against **every source** in the previous
   [Graph/NuExtract3 lock](../../product_eval/fixtures/docling_graph_v1_dev_sources.json),
   including its six scored documents and six examples. Verify CORD sources
   are in the 60-development manifest and absent from the 40-reserved manifest
   by both doc ID and raw source hash. The frozen manifest hashes are VRDU
   cohort `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`,
   CORD development `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a`,
   CORD reserved `06d0bcfb05734557c54b85a9d7c0536008d9393a14012a1c7d01ab6e3058647e`,
   and the previous twelve-source lock
   `61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047`.
   CORD's split also groups near-duplicate images; raw-hash disjointness
   alone does not establish vendor or layout independence.
3. In a **second, later commit**, freeze each selected doc ID, family, raw
   source SHA256, OCR sidecar SHA256, exact OCR prompt-text SHA256, corpus
   manifest hashes, rule canonical SHA256, model/projector/server hashes,
   prompt/settings hash, selection algorithm, and source-lock SHA256. Reject
   missing or changed files, duplicate hashes, any reserved CORD item, and any
   prior scored/example item. Keep raw sources, OCR, prompts, replies, and gold
   outside Git. Hash gold manifests for later integrity checks, but do not
   parse gold during selection or inference. **No fresh source hashes are
   claimed in this first commit:** selecting them before the rule commit would
   defeat the precommit boundary.

## Harness and arms, after a separate run decision

Reuse the pinned NuExtract3 Q4 model/projector and local llama.cpp configuration
from the original protocol, including 120-dpi all-page images capped at 1,600
pixels, page-labeled completed OCR up to 6,000 characters, temperature 0.2,
seed 42, one slot, 12,288 context tokens, and 3,072 maximum output tokens.
Preflight model/template compatibility and resources. Freeze the exact prompt
body and runner commit before calls; no prompt may include gold names, values,
row content, alias slots, family labels, or reference schema. Document text is
untrusted data. Run at most 12 schema calls plus 12 conditional value calls,
zero retries, one source at a time, with a 300-second per-call cap and a
240,000-token total accounting cap. Failures and skipped calls stay in the
12-source denominator. No model run is authorized by this document.

The **no-reference-template schema arm** requests the same compact typed JSON
template and repeated line-item objects as the original blind call. Seal all
12 raw schema replies before loading gold. For the separate **self-template
value arm**, send only each document's own valid model-generated template
and that document's images/OCR; invalid or truncated templates produce a
failed value result. Seal all value replies before loading gold. This is an
end-to-end automatic candidate, not the old reference-schema oracle. Do not
pool its schema and value metrics, and never substitute reference field IDs
to rescue a failed self-template. Any optional reference-template arm needs
its own explicit label, budget, and report.

After replies are sealed, load the frozen gold for **scoring only**. Report
per-family and per-source exact-ID, original ontology, and grouped-leaf schema
matches; linked field and pair recall with collision counts; then separately
report exact positive scalar values, mapped linked cells, and one-to-one exact
complete rows from the self-template arm. A complete row must contain every
annotated field; missing schema fields fail that row. Preserve strict raw
string and secondary NFKC/space-normalized views separately. Verify source
quotes and page/row evidence before acceptance: model JSON alone supplies no
verified boxes or spans, so **zero outputs are auto-accepted**. CORD labels
are positive-only, and VRDU annotations cover a narrow ontology; unsupported
precision or hallucination claims are prohibited.

Promotion requires a source-disjoint, larger and more diverse evaluation of
correct linked rows, evidence, reviewer effort, latency, and total cost. A
product change still needs the separately required **at least 2,000 distinct
source** regression gate and an independent permitted holdout. This small
development experiment cannot establish arbitrary-document performance or
change the accepted paper's reported findings.
