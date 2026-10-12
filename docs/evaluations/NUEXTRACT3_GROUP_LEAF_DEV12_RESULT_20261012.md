# NuExtract3 grouped-leaf follow-on: frozen 12-source development result

**Decision: do not promote.** The tuned, family-independent grouped-leaf rule
recovered two linked field pairs on receipts but none on ad-buy forms. Strict
self-template extraction recovered no complete annotated rows. The value arm
stopped at the precommitted host-memory guard, so this is an incomplete
development diagnostic, not a full value-arm result or a product quality claim.

## Chronology and integrity

The [rule and protocol](NUEXTRACT3_SEMANTIC_ALIGNMENT_FOLLOWON_PROTOCOL_20261012.md)
were committed as `819d62e` before source selection; the
[12-source lock](nuextract3_group_leaf_dev12_sources.json) was committed as
`bae94a1`. The runner and scorer were committed as `87c28a6`, then the
[code lock](nuextract3_group_leaf_code_lock_v1.json) as `e9ac449`. The latter
has raw SHA256 `48fce1c67eb0e76bfb9582b9751fd47d2bdd2ac9544ab4d1adadd44e169aaed4`;
its Git-tree, current-file, source-lock, rule, and profile checks passed before
inference and after scoring. The source-only inventory check found all twelve
raw sources and OCR sidecars byte-identical and did not parse gold.

The raw run is outside Git at
`E:\DocAI-Benchmarks\nuextract3-grouped-leaf-dev12-v1\run.json`, SHA256
`b86ceff97f6cac6ac85b574eba15ba24f54e74d174d82e5c5c326980e535afc7`.
Its `preflight.json` SHA256 is
`a1e549f7c4b1fac06b4343615f2b5cc682c288f560ec7edb4903fb753ad81136`;
the twelve rendered image sets and exact schema request-body hashes were saved
before the first model call. The `calls.jsonl` SHA256 is
`3f1b490c1cc75b67a1bf4ad9ef4affbcf69c2462534bb0afa4308153cb097846`.
A separate receipt check verified all 19 request and reply file hashes,
all twelve schema request hashes against the preflight receipt, unique call
labels, schema-before-value order, 57,913 accounted tokens, 36 schema-score
rows, and twelve value-score rows. No gold was parsed until both model arms
had ended. No gold ID, value, row, family label, alias slot, or reference
template entered a request.

The pinned local NuExtract3 Q4 model, vision projector, and llama.cpp build
11425 passed hash, loopback listener ownership, vision flag, context, slot,
health, and template-mode preflights. The server was stopped after the run.
The 19 calls took 144.3 seconds end to end. The resource sampler observed a
maximum 5,444 MiB GPU memory use; the final eligible value call was blocked
when available host RAM fell below the frozen 2 GiB guard. No retry or
replacement occurred.
All twelve locked sources remain in every score denominator.
The last sampler record at `2026-10-12T16:59:02.321943Z` was
**2,152,189,952 available RAM bytes** and 2,756 MiB free GPU memory. The
guard's subsequent read was below its 2,147,483,648-byte RAM threshold, but
the exact value of that read was not persisted; the blocked source's outcome
records the guard error. This is a telemetry gap, not a model-call failure.

## Outcomes

The schema arm attempted 12/12 calls: eight valid templates, two templates
rejected by the bounded template grammar, and two replies rejected for
duplicate JSON keys. Of the eight eligible self-template value calls, seven
were attempted: six completed and one returned malformed JSON. The eighth was
blocked by the RAM guard. The other four were correctly skipped because their
schemas were invalid. All raw replies and failures remain in the run bundle.
Both schema duplicate-key failures came from the strict JSON parser, which
rejects repeated keys in nested model content and in the outer API reply
instead of silently retaining the last value.

| Locked source ID | Schema reply | Self-template value model call |
| --- | --- | --- |
| `7ba35933944eee89ee43b3bbba803dfb` | Valid | Completed |
| `7303ec881d6845a40d9fc020e8cfa15c` | Valid | Completed |
| `fe2fcccf130fd38bdeb28b8597861ee9` | Valid | Completed |
| `d7a30914d32c62df019b55f2a3c2d834` | Invalid template | Skipped |
| `0dca9c23dfeca2163c12090aed497513` | Duplicate key | Skipped |
| `645db4e6afd7e00a1c1119e98538d3bf` | Valid | Completed |
| `929eece3330db1c63ad9df29c72e916b` | Valid | Malformed JSON reply |
| `f14d0a9762d099d3ceb7f0bfbf146281` | Duplicate key | Skipped |
| `9f2a6408e8b64f9e159d5f59c73ad88d` | Valid | Completed |
| `80d127023b7175e317489afd7b25eca5` | Valid | Completed |
| `baa00097fb7bd54a5416ca363359fcc6` | Invalid template | Skipped |
| `1c88826dce03cbb09c428b1750f595a2` | Valid | Blocked by RAM guard; no call |

| Schema mode, all 12 sources | Matched annotated fields | Linked pairs |
| --- | ---: | ---: |
| Exact reference ID | 13/101 | 0/52 |
| Original predeclared ontology | 22/101 | 0/52 |
| Tuned grouped-leaf rule | 16/101 | 2/52 |

The grouped rule scored 0/40 linked pairs on ad-buy forms and 2/12 on CORD
development receipts; registration forms had no annotated linked pairs.
Thirteen alias-slot collisions were left unmatched. The pair gain is a
lexical/structural alignment on a tuned secondary development set. It does
not establish row correctness or semantic equivalence for ambiguous prices.
In particular, unqualified `item_price` still does not match `unit_price`.

The separate self-template value arm scored **2/57** exact positive scalar
values, **0/5** exact scalar-list values, **3/190** ordinal exact linked
cells, and **0/30** strict exact complete rows. Twenty-four additional gold
rows were sparse and received no complete-row credit. The secondary normalized
views did not improve these counts. These denominators include documents with
failed or skipped calls. The model supplied no verified quote spans or cell
boxes; machine-auto-accepted values remain zero.

The original six-source NuExtract3 result remains **0/26 linked pairs** under
its original ontology. This new 0/52 original-ontology and 2/52 tuned-rule
comparison is on different, source-disjoint documents and cannot revise that
result. CORD labels judge positives only, VRDU reference fields are narrow,
and the CORD development sources can share layouts. This small aborted pilot
cannot support a precision, arbitrary-document, cost, or 2,000-document
regression claim. A future candidate would need source-backed cell/row
alignment and a larger independent holdout before product integration.
