# ICORE supplied-schema product development smoke

This `research_evidence` surface is kept as a bounded diagnostic. It is not a
holdout experiment, production promotion or a replacement for the final 2,000-source
execution. The user authorized ICORE Luna 6 testing. No Sonnet model is used.

Use the six previously scored development originals from
`product_eval/fixtures/docling_graph_v1_dev_sources.json`: two VRDU registration
PDFs, two VRDU ad-buy PDFs and two CORD development PNGs. The source-only lock has
canonical LF SHA-256 `61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047`.
Reserved CORD sources and the proposed quality240 cohort are excluded.

Before inference, `python -m product_eval.icore_confirmed_dev prepare` verifies
the original source hashes, freezes three family schemas, validates them using the
actual `load_confirmed_schema` interface, runs an English OCR smoke and records
the exact Python/package/parser environment and clean code commit. Per-family
field IDs and meanings are fixed in the runner from the published
[VRDU task](https://github.com/google-research-datasets/vrdu) and
[CORD categories](https://github.com/clovaai/cord). No target-document annotation
presence, field shape, gold value or evidence is used to choose its schema.

Every registration gets the same six scalar fields, every ad-buy the same nine
scalar and five linked fields, and every receipt the same five scalar and three
linked fields. Source strings remain strings; `item_price` means total line price,
not unit price. Ambiguous multiple scalar values are not arbitrarily collapsed.
The present product contract lacks scalar-list fields, which remains a limitation.
The research UUID and schema confirmations identify evaluator-supplied input;
they do not represent measured user onboarding or human review.

The `run` subcommand requires the exact frozen protocol SHA. It processes each
original through the unchanged product `process_auto`, passing the loaded confirmed
schema. Thus there is no schema-discovery call. Use only `innobot-luna-6` at the
user-provided ICORE endpoint, one value attempt per document, six total attempts,
one concurrent request, zero SDK retries, 8,192 maximum output tokens and 180 seconds
per request. Prompt caps are 50,000 characters and 200,000 UTF-8 bytes. Existing
product limits remain, including 24,000 document characters and 50 pages. No source
substitution, response repair or retry is allowed. Authentication, rate-limit or
ambiguous transport failures block further API calls while preserving outcomes.

Save requests, sanitized model replies and HTTP response bodies locally outside Git
before product parsing. Never save HTTP headers or credentials. An append-only,
flushed attempt ledger records identities, hashes, tokens, finish reason, latency,
SDK attempts and error category. A prior run-start marker prevents accidental
resumption that could duplicate billable requests. Local reply bodies enable
diagnosis of malformed output rather than retaining only an unrecoverable hash.

Keep all six documents in the denominator, including parser/context failures and
missing model calls. Verify original sources and product result receipts. Only
after outputs are sealed may the already-used development gold be read for exact
values, order-independent annotated rows and evidence-coordinate compatibility.
CORD remains positive-only; no precision or hallucination claim from unlabelled
fields. API token usage is measured; dollar cost remains unknown until billed rates
or settled charges are available. No result is automatically released by this
confirmed-schema implementation; source-quoted values still require review.
