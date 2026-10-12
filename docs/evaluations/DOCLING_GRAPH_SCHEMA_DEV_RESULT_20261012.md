# Docling Graph local schema-induction development result

**Decision: do not integrate this configuration as the automatic schema route.**
The source-locked Docling Graph v1.9.1 pilot completed on 12 October 2026.
It generated some valid SPECs and Python templates, but its reusable schemas
missed most reference fields and all linked field pairs. This is a six-scored-
document development diagnostic of *schema induction only*. It did not extract
or verify values, measure reviewer effort, or establish production accuracy.
The accepted conference paper and the product's 2,000-document no-model gate
have different methods and denominators; neither result is updated by this pilot.

## Locked run and integrity

The [frozen protocol](DOCLING_GRAPH_SCHEMA_DEV_PILOT_20261012.md) used the
12-document source lock `61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047`
and predeclared alias ontology `24950fd476469d5a433ec3ef423d005eba8ecb703e730b44a8f7f538e306bd03`.
There were two example and two scored source-disjoint documents in each of
three families: VRDU registration forms, VRDU ad-buy forms, and CORD v2
**development** receipts. The 40 reserved CORD receipts were excluded.
The model saw the existing completed Tesseract OCR text, with no gold labels;
gold was loaded after all induction calls. Graph was the verified v1.9.1 Git
commit `59f40ca2e20f7cdbc8898fcee733fcba947ab762`, with local
Qwen3-4B Q4_K_M under llama.cpp b11425. No private documents or ICORE API
calls were used.

The completed raw run is
`E:\DocAI-Benchmarks\docling-graph-schema-dev-v1\run.json`, SHA256
`645b95a4de95c7481b0269c2f7eb98c409636d587ebe8076b6de3bb2dfce6f27`.
Its directory contains `calls.jsonl`, `resource_samples.jsonl`, and every
produced SPEC, induction report, and rendered Python template. The report
contains 24 score rows: six scored source IDs, each evaluated in two arms
(reused family template and per-document induction) and two match modes
(exact field name and the frozen aliases). A failed arm remains in the
denominator with zero matches. This run is complete; repeating failed units
would constitute a new experiment.

## Schema scores

The principal match mode is the **predeclared alias** ontology. VRDU
precision/F1 are relative to a narrow creator annotation ontology; extra
fields are *out of that reference scope*, not proven hallucinations. CORD
has positive-only labels, so its precision and F1 are undefined.

| Family (scored documents) | Arm | Matched / gold | Out-of-scope or duplicate VRDU fields | Reference precision | Recall | Reference F1 | Linked pairs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Registration (2) | Reused family | 4 / 12 | 44 | 8.33% | 33.33% | 13.33% | 0 / 0 |
| Registration (2) | Per document | 4 / 12 | 9 | 30.77% | 33.33% | 32.00% | 0 / 0 |
| Ad-buy (2) | Reused family | 0 / 28 | 0 | undefined | 0% | undefined | 0 / 20 |
| Ad-buy (2) | Per document | 1 / 28 | 3 | 25.00% | 3.57% | 6.25% | 0 / 20 |
| Receipt (2) | Reused family | 0 / 13 | unjudged | undefined | 0% | undefined | 0 / 6 |
| Receipt (2) | Per document | 2 / 13 | unjudged | undefined | 15.38% | undefined | 0 / 6 |

Without aliases, the reusable registration schema matched 2/12 and its
per-document counterpart 2/12; ad-buy matched 0/28 in both arms; receipt
matched 0/13 reused and 2/13 per-document. The alias gain was limited to
registration and one ad-buy field. Across the **four VRDU scored documents**,
the alias-mode reused templates matched 4/40 with 44 extra/duplicate fields
(micro reference F1 9.09%); per-document induction matched 5/40 with 12
extra/duplicate fields (micro reference F1 17.54%). This comparison is small
and has no confidence interval. Both arms scored **0/26** linked reference
field pairs across ad-buy and receipt documents. A shared repeated object,
not separately named lists, was required for a linked-pair hit.

The reused registration template produced 24 root-reachable leaf fields;
only two names matched the six reference fields on each scored form after
aliases. The reused receipt template had one root-reachable leaf field
(`document_reference`) despite defining 12 models, and matched none of 13
positive fields. One per-document receipt SPEC did contain a repeated `Item`
model with `item_name`, `quantity`, and `unit_price`, but those names did not
map to the frozen CORD field IDs and produced no scored linked pairs. This
shows limited local structural promise, not a usable extraction result.

## Failures, runtime, and interpretation

Seven of nine induction outcomes produced SPEC/template artifacts. The
ad-buy family arm failed with `ExtractionError`: its first example exhausted
the 3,072-output-token limit twice (`finish_reason=length`), so the second
example was not called. One ad-buy per-document arm also failed with
`ExtractionError`; there is no HTTP trace for that document, and the stored
outcome does not establish its narrower cause. Both failures remained in the
scores. There were 11 HTTP calls against the hard cap of 24, and 50,986
accounted tokens against the 160,000 cap. Wall time was 243.3 seconds and
summed model-call latency 234.7 seconds. Sampled peak **host-wide** GPU use
was 5,834/8,192 MiB; minimum host available RAM was 1.71 GB and maximum
Graph Python RSS 503 MB. The GPU and available-RAM figures include other
workloads and are not isolated model-process measurements. Provider spend
was zero; GPU electricity, amortization, and review labor were not priced.

The result does not distinguish whether the dominant limitation is OCR,
small-model capacity, Graph's one-shot prompts, output budget, or ontology
scoring. The tiny, OCR-readable development selection is not a generalization
holdout. It does decisively reject promoting this exact local Graph/4B/OCR
configuration: even a reusable schema success here would still require
value extraction, source-quote and box verification, linked-row scoring,
human-review measurement, and a fresh >=2,000-distinct-source gate after a
product implementation change.

Next experiments should be bounded and paired on the same source lock:
improve OCR/text layout and test a stronger fit-verified local or priced
cloud model; compare a simpler typed schema inducer and Docling Graph on
matched input/call budgets; then evaluate value/evidence and linked rows on
source-disjoint development and reserved holdout documents. Only a candidate
that improves the actual extraction product should replace the current route.
