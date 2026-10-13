# Strict format for confirmed-schema values

Classification: `idpo/product_auto` is core product extraction; this profile is an opt-in addition to keep. It does not change the research evaluation profile, schema discovery, approved recipe path, or the default `plain_json` product behavior.

`process_auto(..., confirmed_schema=..., response_format_profile="strict_confirmed_values_v1")` requests a strict Chat Completions JSON Schema for **values only**. A confirmed, immutable schema is required before the run directory is created. The response format is derived from its pinned field IDs and types. The format profile and SHA-256 of the canonical request schema appear in `run.json`, each `manifest.jsonl` receipt, and each document sidecar.

The response is locally decoded with duplicate-key and nonfinite-number rejection. It must have one `values` item for every confirmed field, with no unknown fields or extra properties. Each item contains `field_id`, `value`, `page`, and `quote`. Missing values use `null`; their page and quote can also be `null`. Repeated fields contain bounded cells with `row`, `value`, `page`, and `quote`. Rows may be present in one linked column and absent in another. The parser never fills an absent quantity from a neighboring value. Non-null values still pass the existing exact source-quote and type checks and remain subject to human review.

Refusal, incomplete output, invalid JSON, a structurally invalid reply, and provider errors cannot fall back to unconstrained JSON or trigger an automatic retry. Local validation is mandatory even when a provider accepts the strict request. The provider capability was observed in two **synthetic** ICORE Luna 6 probes; that is not evidence of general enforcement or real-document accuracy. Long-document segmentation and broader measured evaluation are separate work.

The CLI and queued product dispatch must pass the exact profile string explicitly to enable this path; until then, existing runs continue with `plain_json`.

## Keyed field contract v2

`strict_confirmed_values_v2` is a separate opt-in response profile for confirmed schemas. It addresses a specific failure in the completed 2,000-source operational run: 25 visual receipt replies were valid JSON but omitted requested fields. The v1 provider schema permits a subset of array entries, although the local decoder correctly rejects that subset.

V2 sends a `values` object with every confirmed field ID listed as a required property. Each property contains `value`, `page`, and `quote`; unknown properties are forbidden. Scalar types follow the confirmed schema, with null for absent values. Linked columns contain the existing bounded row cells, while the column's outer `page` and `quote` must be null. Text and visual instructions show the complete keyed shape before document data. Visual requests use `strict_visual_confirmed_values_v2` internally.

The local decoder validates the actual response before projecting it into the existing grounding and review representation. It rejects missing or extra keys, duplicate JSON properties, wrong types, nonfinite values, invalid source pages, blank linked cells and row/length limit violations. The provider schema does not yet send `minLength` or `maxItems`, whose ICORE support is unverified; these limits remain mandatory in local validation. Raw-reply provenance hashes the actual provider response, never the internal projection.

Select v2 through `autoResponseFormat` in the native configuration or `--response-format-profile` in the CLI. Queue admission seals the choice. Existing v1 requests and prompts retain their previous bytes, and the default remains `plain_json`. The deployed v1 campaign results do not measure this new contract. V2 must be evaluated separately for provider compatibility, field omission rate and semantic quality before promotion; syntactically complete fields can still contain wrong values or unjustified nulls.

The [two-request synthetic capability check](evaluations/STRICT_VALUES_V2_CAPABILITY_20261014.md) observed valid text and visual replies from ICORE Luna 6. It establishes those request/parser round trips only; field examples and the exact synthetic transcript were supplied, so it does not establish independent extraction accuracy.
