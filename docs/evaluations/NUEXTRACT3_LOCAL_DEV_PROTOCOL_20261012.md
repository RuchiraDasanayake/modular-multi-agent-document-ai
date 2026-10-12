# NuExtract3 local development protocol

**Frozen before inference, 12 October 2026.** This is a bounded feasibility
diagnostic, not a product rollout or a new conference-paper result. Use the
same six *scored* public sources in the earlier [Docling Graph development
lock](../../product_eval/fixtures/docling_graph_v1_dev_sources.json): two VRDU
registration forms, two VRDU ad-buy forms, and two CORD v2 **development**
receipts. The two example sources per family are verified but are not sent to
NuExtract3. The 40 reserved CORD receipts remain untouched.

## Package and boundary

[NuMind's pinned NuExtract3 GGUF model card](https://huggingface.co/numind/NuExtract3-GGUF/tree/28a1aae6288c5d50bdf999ca2e572240966d669b)
describes a JSON-template extraction mode, template-generation mode, and
text/image inputs. The model is Apache-2.0. The exact repo revision is
`28a1aae6288c5d50bdf999ca2e572240966d669b`; Q4_K_M weights are
2,783,445,984 bytes / SHA256
`7ee3c0ee9e5699a4391624ae758487f583f73b3242aa4e73dc2bb33e508d703e`;
the BF16 vision projector is 675,569,184 bytes / SHA256
`9a506ce43544691f4f56f1533768f43e1887ef69b8cd74b2e7a46c4d9a155a01`.
The existing local `llama-server.exe` is build 11425, SHA256
`4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306`.
Its CLI exposes `--mmproj` and `--chat-template-kwargs`; **successful model
loading and template-kwarg behavior still require an empirical check**.
Start this pinned build with `--reasoning off` as well as `--jinja` and the
verified projector. Before the first scored completion, require `/props` to
report vision support and `/apply-template` to show different rendered prompts
for generic, `template-generation`, and JSON-template settings. This probe
contains no document or gold data and performs no model inference. A failed
probe is a compatibility no-go, not an extraction result.

`product_eval/nuextract3_dev_diagnostic.py` uses only a loopback server. It
adds no runtime dependency to the product and makes no cloud call. Every raw
source, image, prompt, reply, resource trace, and score stays under a new
`E:\DocAI-Benchmarks\nuextract3-dev-*` directory outside Git. Only a
source-free aggregate report may be committed. Verify the complete source,
gold, OCR-sidecar, server, weight, and projector hashes before any call.

## Frozen input and arms

Render **all** pages for each selected source at 120 dpi, cap the longest
dimension at 1,600 pixels, encode RGB JPEG at quality 85, and include up to
6,000 characters of its already completed Tesseract OCR with page labels.
No document is selected using NuExtract3 output. Image downsampling and OCR
quality are measured limitations, particularly for six-page ad-buy tables.

There are two distinct one-call-per-source arms, each over all six scored
sources. Use temperature 0.2, seed 42, non-thinking mode, one slot,
12,288-token context, and 3,072 maximum output tokens per call:

1. **Blind per-document schema discovery:** send images plus OCR and a generic
   request for a compact typed JSON template with repeated objects for
   line-item rows, using `chat_template_kwargs.mode=template-generation`.
   No gold field name, type, shape, value, evidence, alias, or family label is
   available to this call. Gold is parsed only after every discovery call has
   ended. Failure, invalid JSON, or truncation leaves an empty prediction in
   the denominator.
2. **Reference-schema value upper bound:** build the JSON template from the
   existing *per-document* gold field IDs and shapes after discovery has
   ended. All leaves use `verbatim-string`; linked columns share one repeated
   `line_items` object. The model sees names and shapes, **never gold values,
   quotes, or row content**. This is an oracle schema, not an automatic-schema
   product result. Invalid JSON or truncation is a failed source.

The schema scorer uses the already frozen
[conservative alias ontology](../../product_eval/fixtures/graph_schema_aliases_v1.json)
SHA256 `24950fd476469d5a433ec3ef423d005eba8ecb703e730b44a8f7f538e306bd03`.
Report exact field-ID and predeclared-alias matches, scalar/list/repeated
object shape, and pairs of linked fields in one repeated object. VRDU extras
are outside its narrow reference ontology, not proven hallucinations. CORD
labels are positive-only, so schema precision is undefined.

For values, report exact typed scalar positives, wrong non-null values,
missing positives, and separately OCR-verbatim grounding. Report linked cell
and complete-row equality by field and normalized surface, both annotation
ordinal and order-independent one-to-one row matching. NFKC/casefold/space
normalization is a secondary view; the strict view uses raw strings. No
post-hoc alias, amount/date conversion, or model judge is allowed. Model
outputs do not carry verifiable page boxes or OCR spans, so **zero values are
auto-accepted** and HITL/release quality is not established.

## Stop and promotion gates

At most 12 chat completions, 3,072 output tokens per completion, 120,000
reported total tokens, 300 seconds per completion, zero retries, and one
model request at a time. Check available host RAM and GPU memory before
starting; keep at least 2 GiB RAM and 1 GiB GPU headroom. Abort on a server
load error, incompatible chat-template kwargs, context overflow, timeout, or
resource guard. Failed sources remain in the six-source denominators. Local
provider spend is zero; electricity, GPU amortization, and review labor are
unpriced. Report wall time and sampled *host-wide* RAM/GPU usage, without
presenting those as isolated process costs.

Only a clear gain in **actual grounded values and linked rows** on these
source-locked development documents can justify a product candidate. Any
product extraction change then requires a fresh >=2,000-distinct-source gate,
with a separate permitted diverse holdout and reviewer/time/cost evidence.
The six-source result alone never supports an arbitrary-document or
world-class quality claim.
