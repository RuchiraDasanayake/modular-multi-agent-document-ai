# NuExtract3 local development diagnostic

**Decision: do not integrate this automatic schema route.** The pinned local
NuExtract3 Q4 multimodal run completed on 12 October 2026. It improved
reference-field recall over the earlier Docling Graph development diagnostic,
but recovered **0/26 linked field pairs** during blind schema discovery. Its
separate reference-schema arm recovered 24/43 exact complete rows when given
the gold field IDs and shapes. That is a useful conditional extraction signal,
not evidence that an automatic end-to-end route works.

## Integrity and scope

The [predeclared protocol](NUEXTRACT3_LOCAL_DEV_PROTOCOL_20261012.md) used
the same six scored public documents as the [Docling Graph diagnostic](DOCLING_GRAPH_SCHEMA_DEV_RESULT_20261012.md):
two VRDU registration forms, two VRDU ad-buy forms, and two CORD v2
**development** receipts. The source lock SHA256 was
`61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047`;
the predeclared alias ontology SHA256 was
`24950fd476469d5a433ec3ef423d005eba8ecb703e730b44a8f7f538e306bd03`.
The 40 reserved CORD receipts and private sources were excluded. Blind schema
calls finished before the runner parsed gold. No ICORE or other cloud API was
used.

The official [NuExtract3 GGUF model revision](https://huggingface.co/numind/NuExtract3-GGUF/tree/28a1aae6288c5d50bdf999ca2e572240966d669b)
was `28a1aae6288c5d50bdf999ca2e572240966d669b`. The local Q4 weights and
vision projector passed the pinned SHA256 checks. A prior XET download had the
expected byte count but the wrong SHA256 and was excluded. The verified files
ran under llama.cpp b11425 with one vision slot, 12,288 context tokens,
`--reasoning off`, and 1,024 minimum and maximum tokens per image. The
no-inference `/apply-template` preflight showed distinct generic, schema
generation, and JSON-template prompts, including the synthetic template field.
Server load and all 12 model calls completed without HTTP, context, timeout,
or truncation errors.

The full raw run is outside Git at
`E:\DocAI-Benchmarks\nuextract3-dev-v1\run.json`, SHA256
`2fb4c5bf66a0e96cc84dd1df4038ce360074d348c188bd376eebcb1cd60cfd92`.
The directory also holds rendered images, replies, call metadata, and resource
samples. No raw document content or model reply is committed.

## Blind schema discovery

The principal match mode uses only the frozen alias ontology. Scores refer to
the narrow available reference fields, so extra VRDU fields are out of scope
of this ontology and are **not** established hallucinations. CORD labels are
positive-only, making reference precision undefined.

| Family (two documents each) | NuExtract3 matched / reference fields | Earlier Graph per-document matched / reference fields | NuExtract3 linked pairs |
| --- | ---: | ---: | ---: |
| Registration | 6 / 12 | 4 / 12 | 0 / 0 |
| Ad-buy | 9 / 28 | 1 / 28 | 0 / 20 |
| Receipt | 7 / 13 | 2 / 13 | 0 / 6 |
| **Total** | **22 / 53** | **7 / 53** | **0 / 26** |

Without aliases, NuExtract3 matched 13/53 fields. Of 22 alias-matched fields,
20 had the expected scalar/list/linked shape. Its 150 extra or duplicate VRDU
fields relative to the narrow reference ontology make blind schemas noisy.
The Graph comparison is directional: Graph received completed OCR text,
whereas NuExtract3 received images plus that OCR, and their model and prompts
differed. Both failed the linked-field gate.

**Post-hoc structural check, outside the primary score:** both ad-buy
templates contained a grouped `line_items` repeated object, and both receipt
templates contained a grouped `items` or nested `receipt.line_items` object.
The projection preserved those repeated-object paths. The frozen ontology
mapped only `channel` in one ad-buy group and `item_name` in each receipt
group to gold linked IDs. For example, the receipt template's generic
`quantity` and `unit_price` are not predeclared aliases of the reference
`item_quantity` and `item_price`. The **0/26** pair score therefore reflects
insufficient predeclared field-ID alignment, not failure to detect a nested
repeated object. These inspected names were not used to add aliases or
recompute the locked score; semantic equivalence would need adjudication.

## Reference-schema value upper bound

After blind discovery ended, the model received each document's reference
field **IDs and shapes only**. It received no reference values, quotes, or
rows. This generous oracle schema is a diagnostic upper bound; the product
cannot assume these field IDs for an arbitrary new document.

| Family | Exact positive scalars | Exact linked cells at annotation ordinal | Exact complete rows, order independent |
| --- | ---: | ---: | ---: |
| Registration | 4 / 10 | 0 / 0 | 0 / 0 |
| Ad-buy | 5 / 15 | 117 / 171 | 21 / 36 |
| Receipt | 4 / 7 | 16 / 21 | 3 / 7 |
| **Total** | **13 / 32** | **133 / 192** | **24 / 43** |

The strict complete-row score compares all annotated fields in each row and
uses one-to-one multiset matching without order. Ordinal-sensitive matching
was 15/43 rows. NFKC/casefold/space normalization left the order-independent
result at 24/43; no date, amount, or alias repair was applied. Both positive
scalar-list fields were wrong. An independent second calculation from the raw
model replies and locked gold reproduced **13/32 scalars** and **24/43 rows**.
The 21/30 ad-buy rows from one source dominate the overall row result; the
other ad-buy source contributed 0/6. This variance blocks a broad quality
claim.

## Runtime and decision

The 12 local calls used 44,762 reported tokens, 79.0 seconds of summed call
time, and 80.7 seconds of run wall time. The longest call took 27.3 seconds.
Sampled minimum **host-wide** available RAM was 3.56 GB and maximum
**host-wide** GPU use was 5,591/8,192 MiB; these are not isolated process
costs. Provider spend was zero. Electricity, equipment amortization, and
review labor were not priced. The server emitted multimodal token-position and
unused-tensor warnings, with no observed request failure; their accuracy
impact is unknown.

These six development sources do not measure generalization. Downsampled page
images and completed Tesseract OCR may miss fine text. The run produced no
verified page boxes or exact quote spans, so **zero model values are eligible
for automatic acceptance**. It did not measure reviewer time, error severity,
or production cost. A future candidate could pair a reliable independently
generated or human-approved schema with NuExtract3 values and evidence checks,
but must be evaluated on source-disjoint data. Any product extraction change
still requires a fresh gate of at least 2,000 distinct sources; this diagnostic
does not satisfy that gate or update the accepted conference paper.
