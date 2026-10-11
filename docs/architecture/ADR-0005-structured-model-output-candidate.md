# ADR-0005: Constrained model output at the product boundary

**Status:** Candidate for a source-locked diagnostic, 12 October 2026. No
product extraction code or model run is changed by this record.

## Decision

Use the installed local `llama.cpp` server's schema-constrained chat output
and the already declared Pydantic dependency for a bounded comparison. Keep
the product's exact source-evidence, typed-value, duplicate-field, and linked-row
checks. Do not add a custom JSON decoder or a general agent/retry framework.
Do not enable constraints on an arbitrary OpenAI-compatible endpoint merely
because it accepts the same URL shape: support is a pinned provider capability
that must pass a preflight and a saved-response validation test.

The decision criterion is **more correct, reviewable fields and linked rows per
unit of total cost**, not JSON validity alone. A syntactically valid answer can
still name the wrong field, copy an unrelated amount, or link table cells to the
wrong row.

## Current path and measured failure

`idpo/product_auto/workflow.py::_process_document` calls a `ChatModel` twice:
schema discovery, then values against that schema. Its only concrete product
adapter, `idpo/product_auto/provider.py::OpenAICompatibleChat.complete_json`,
uses the OpenAI SDK with a prompt asking for JSON but sends no
`response_format`. `idpo/product_auto/logic.py::parse_schema_reply` and
`parse_values_reply` decode JSON and hand-check the envelope, field IDs, types,
cell ordinals and evidence. One malformed value entry rejects the entire value
reply. The workflow already rejects errors and non-`stop` finish reasons and
keeps a newly discovered schema pending human review.

The [source-hash-selected Qwen3-4B oracle-schema pilot](../evaluations/LOCAL_QWEN_ORACLE_SCHEMA_VRDU_TWELVE_PILOT.json)
is the relevant local control. It passed gold field IDs/types to a text model,
so its perfect schema score measures no discovery. With `json_object` output on
the pinned llama.cpp server, seven of twelve documents had a parseable value
response; three whole responses failed the strict parser, one was truncated,
and one exceeded the product's 24,000-character document limit without a call.
It matched 11/98 exact scalars, had 14 false accepted scalar values, and
matched 0/111 exact linked rows. All twelve documents required review. The
three malformed responses included missing `value` keys, duplicate field IDs,
and an unknown field ID. Constraining structure may reduce those failures;
it has no demonstrated effect on the wrong values and rows.

The separate [frozen October paper evidence](../../paper/FINAL_EVIDENCE.md)
reported 0.884 micro F1 on CORD-100 for its static pipeline using PaddleOCR
2.9.1 and `qwen3.5:9b` through Ollama 0.35.1 with pack-defined fields. That
result is a useful stronger local-model reference, but it uses a different
receipt pipeline, field contract, and scorer. It does not measure product-auto
schema discovery and cannot be compared directly with this 4B VRDU pilot.
The 4B constraint comparison below tests the **output interface**, not the
best local model choice. This host has neither the Ollama binary nor the 9B
model blobs. After the volume gate, a source-locked 9B product-auto pilot may
be more valuable for schema discovery if disk and memory permit.

## Reuse choice

| Option | Assessment |
| --- | --- |
| Prompt-only JSON plus current parser | Zero new dependency; the 12-document pilot shows whole-reply structure failures and no reliable linked rows. Keep as a paired control. |
| **Pinned llama.cpp constraint + Pydantic shape validation** | Best small trial. The installed `E:\DocAI-Benchmarks\tools\llama-b11425\bin\llama-server.exe` reports build 11425, commit `e117148a4`; its executable SHA256 is `4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306`. The [same-version server guide](https://github.com/ggml-org/llama.cpp/blob/b11425/tools/server/README.md) documents `response_format` schema constraints. The [same-version grammar guide](https://github.com/ggml-org/llama.cpp/blob/b11425/grammars/README.md) warns that it converts only a JSON Schema subset and silently skips unsupported features. Pydantic can produce a schema and validate the returned shape; it cannot prove source truth. |
| Ollama structured output | [Ollama documents](https://docs.ollama.com/capabilities/structured-outputs) a JSON Schema in `/api/chat`'s `format` field and Pydantic validation. Ollama was not found on this host's PATH or in the two usual install paths during this audit, and no Ollama process was running. Do not imply its local installation or transport was tested. |
| Instructor / Outlines | [Instructor](https://python.useinstructor.com/concepts/retrying/) adds validation retries and token budgets; retries add requests and can obscure per-attempt cost unless explicitly controlled. [Outlines](https://dottxt-ai.github.io/outlines/main/guide/architecture/) adds another generation abstraction, while its server integrations delegate constraints to the server. Neither package is installed here. The pinned server already offers the narrow capability to test first. |

The project declares `pydantic==2.13.3` in `requirements.txt`; this interactive
Python environment has 2.12.5. Run any comparison in a pinned environment.
[Pydantic's documentation](https://docs.pydantic.dev/latest/concepts/json_schema/)
supports `model_json_schema()` and strict model validation. An offline check
with the installed Pydantic 2.12.5 showed `extra='forbid'` rejects an extra key
and strict `int` rejects a numeric string, but duplicate JSON object keys are
silently reduced to the last value. Thus a small duplicate-key guard must
remain before Pydantic, and duplicate field IDs after canonicalization must
remain a product invariant. Never treat Pydantic as the whole source-grounding
parser.

## Exact integration seam after the diagnostic

1. Extend the `ChatModel.complete_json` boundary in
   `idpo/product_auto/workflow.py` to accept a phase-specific response schema
   and a declared capability. In `idpo/product_auto/provider.py`, send the
   documented `response_format` only for a pinned, probed local llama.cpp
   adapter. A future Ollama adapter would map the same logical schema to its
   different `/api/chat` `format` parameter. Unsupported providers must fail
   closed or use an explicitly selected prompt-only mode; never silently
   downgrade a requested constraint. Keep `max_retries=0` for unknown billable
   providers and record schema hash, provider mode, finish reason and tokens.
2. Introduce small Pydantic models for the JSON **shape** at
   `idpo/product_auto/logic.py::{parse_schema_reply,parse_values_reply}`. Use
   strict types, bounded counts, required `value`, forbidden unknown keys,
   and a duplicate-key check before validation. Preserve those functions'
   public candidate shape and legacy tests. Generate only the subset of JSON
   Schema verified on the pinned server; avoid unsupported nested references
   and `uniqueItems`. The [llama.cpp grammar guide](https://github.com/ggml-org/llama.cpp/blob/b11425/grammars/README.md)
   explicitly lists these limits. A generated schema is not itself proof the
   server enforced it; validate every reply locally.
3. Keep `normalize_field_id`, `coerce_value`, `value_matches_quote`,
   `resolve_evidence`, `_parse_linked_value`, status/review policy, and the
   reviewer provenance contract as product checks. In particular, exact OCR
   quote uniqueness and row alignment cannot be delegated to generic JSON
   Schema. A schema-valid but ungrounded value stays in review.

## Frozen 12-document diagnostic, deferred until the volume gate is idle

Use the same six registration and six ad-buy sources selected by lowest raw
source SHA256 within family, independent of gold. The frozen cohort JSONL SHA256
is `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`;
gold JSONL SHA256 is `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
The local Qwen3-4B Q4_K_M GGUF SHA256 is
`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
Reverify the twelve raw source hashes, completed OCR sidecar hashes, model
weight, and server build before a new call. Gold values and evidence must not
enter prompts or provider logs. Gold schema IDs/types are deliberately supplied
in **both** arms, so this trial isolates value-output structure and cannot
measure schema discovery.

Run a new paired control and candidate on the same eleven model-eligible
sidecars, with identical saved OCR pages, prompt, model, seed, sampling,
12,288-token context, 3,000-token completion cap, and no retry. Retain the one
over-limit document in all twelve-document denominators. Control:
`response_format={"type":"json_object"}` as in the earlier pilot. Candidate:
a minimal `json_schema` envelope with `values` array, at most the supplied
field count, an enumerated known `field_id`, required `value`, and no extra
properties. Keep value type and row-cell semantic checks downstream; do not
silently claim that this small grammar solves nested tables. Check the exact
`b11425` response-format request form with a bounded local conformance probe
before the paired run. Save raw reply hashes and all failures outside Git.

Score both arms on: schema-conformance and local validation failures (including
duplicate IDs), truncations, exact typed scalar TP/FP/FN, false accepted
values, exact linked cells/complete rows, source-quote grounding, accepted
versus pending status, latency, tokens, host/GPU memory and priced compute if
measurable. Inspect per-family results. Do not promote based solely on fewer
parse errors; require a gain in correct values or rows without more false
acceptances or unacceptable cost. No 2,000-document model gate is justified
by the historical Qwen result alone.

Focused implementation tests must cover the schema payload for the pinned
provider, unsupported-provider refusal, local conformance failure, no silent
fallback, duplicate JSON keys, duplicate canonical IDs, missing `value`,
unknown fields, non-finite/oversized numbers, invalid page/quote, repeated
quotes, duplicate row ordinals, truncated finish reasons, old artifact
compatibility, and a schema-valid but semantically wrong value remaining in
review. Preserve the raw candidate and immutable reviewer audit in any later
integration.
