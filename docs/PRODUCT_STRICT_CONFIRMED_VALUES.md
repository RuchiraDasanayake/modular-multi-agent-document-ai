# Strict format for confirmed-schema values

Classification: `idpo/product_auto` is core product extraction; this profile is an opt-in addition to keep. It does not change the research evaluation profile, schema discovery, approved recipe path, or the default `plain_json` product behavior.

`process_auto(..., confirmed_schema=..., response_format_profile="strict_confirmed_values_v1")` requests a strict Chat Completions JSON Schema for **values only**. A confirmed, immutable schema is required before the run directory is created. The response format is derived from its pinned field IDs and types. The format profile and SHA-256 of the canonical request schema appear in `run.json`, each `manifest.jsonl` receipt, and each document sidecar.

The response is locally decoded with duplicate-key and nonfinite-number rejection. It must have one `values` item for every confirmed field, with no unknown fields or extra properties. Each item contains `field_id`, `value`, `page`, and `quote`. Missing values use `null`; their page and quote can also be `null`. Repeated fields contain bounded cells with `row`, `value`, `page`, and `quote`. Rows may be present in one linked column and absent in another. The parser never fills an absent quantity from a neighboring value. Non-null values still pass the existing exact source-quote and type checks and remain subject to human review.

Refusal, incomplete output, invalid JSON, a structurally invalid reply, and provider errors cannot fall back to unconstrained JSON or trigger an automatic retry. Local validation is mandatory even when a provider accepts the strict request. The provider capability was observed in two **synthetic** ICORE Luna 6 probes; that is not evidence of general enforcement or real-document accuracy. Long-document segmentation and broader measured evaluation are separate work.

The CLI and queued product dispatch must pass the exact profile string explicitly to enable this path; until then, existing runs continue with `plain_json`.
