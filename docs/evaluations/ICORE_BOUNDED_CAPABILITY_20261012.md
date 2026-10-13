# ICORE bounded structured-output diagnostic, 12 October 2026

## Scope and protocol

This research-only test used the existing repository **synthetic invoice** in
[`ICORE_SYNTHETIC_PILOT.json`](ICORE_SYNTHETIC_PILOT.json). It sent no private or
user document. The fixed models were `innobot-minimax-m2-5` and
`innobot-luna-6`, both observed in the authenticated ICORE catalog during the
earlier pilot. The Chat Completions request shape followed the
[OpenAI Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create);
that reference does not establish what ICORE enforces.

The cap was **six billable chat attempts**, 1,024 output tokens per request,
60-second timeout, and zero SDK retries. All six were attempted. The first
two calls probed `response_format=json_schema` with `strict=true` and a
two-field, no-extra-properties schema. The synthetic user prompt requested
an extra `debug` field. The next calls tested the current product's two-stage
schema and value prompts with `response_format=json_object`. When MiniMax
returned HTTP 400 for that format, one separate sixth call tried a small
strict-schema induction format. No call was automatically retried.

The [sanitized machine-readable receipt](ICORE_BOUNDED_CAPABILITY_20261012.json)
contains source-fixture and source-text SHA-256 hashes, requested model ID
hashes, canonical credential-free request hashes, status, finish reason,
latency, reported token usage, response hashes, and safe exception classes.
It contains no request/response text, document text, key, provider error body,
or credential file path. USD cost is `null` because no ICORE rate card or
settled bill was available. The key was read from the local user attachment
into process memory only.

## Observations

| Model and call | HTTP / finish | Local assessment |
| --- | --- | --- |
| MiniMax strict two-field JSON schema | 200 / stop | Valid JSON, exact allowed keys and types, both synthetic facts correct. |
| Luna 6 strict two-field JSON schema | 200 / stop | Valid JSON, exact allowed keys and types, both synthetic facts correct. |
| MiniMax JSON-object schema induction | 400 / no completion | Rejected. The provider error body was discarded, so the exact rejection reason is unknown. |
| Luna 6 JSON-object schema induction | 200 / stop | Product parser accepted 12 proposed fields, including four proposed repeated-column fields. |
| Luna 6 JSON-object value extraction | 200 / stop | Product parser accepted 12 value entries; seven passed its exact source-grounding check, and four of five predeclared scalar facts matched exactly and were accepted. |
| MiniMax strict-schema induction | 200 / length | Hit the 1,024-token cap; no parseable schema. |

Five attempts returned HTTP 200, one returned HTTP 400, and **none had a
transport failure** in this tiny sequence. The five successful responses
reported 1,241 prompt tokens and 1,979 completion tokens in total; the
HTTP 400 attempt has no usage receipt. The six elapsed times ranged from
0.306 to 10.687 seconds. These are attempt receipts, not a reliability
estimate, settled charge, or quality benchmark.

The two small strict-schema replies are compatible with support for the
OpenAI-shaped parameter, but prompt following alone could also explain the
exact outputs. They do not prove provider-side enforcement across schemas,
models, refusals, or long generations. The MiniMax `json_object` rejection
means it is not a drop-in choice for the current product two-call route with
that format. Its strict induction result also shows that a valid response
format does not prevent truncation at this output budget.

The Luna extraction used a **synthetic invoice previously seen by this
project**, so four of five grounded scalar facts is a smoke observation,
not independent real-document accuracy. The proposed repeated columns were
not evaluated as linked rows here. The production route, approval policy,
and provider defaults were unchanged.

## Decision

Use Luna 6 only for a source-locked, public development-document diagnostic
with the existing product verifier and every failure in the denominator.
Keep strict ICORE schema enforcement and MiniMax product routing disabled
until a larger model/schema conformance test, real-document quality comparison,
and ICORE pricing/data terms are available. Keep cost unknown in all product
and evaluation receipts.
