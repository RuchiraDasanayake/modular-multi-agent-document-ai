# Luna 6 image diagnostic v2: provider-compatible image bounds

This version follows the [v1 image-size rejection](ICORE_VISION_DEV3_V1_RESULTS_20261013.md).
It preserves all three originals, family schemas, cached OCR, extraction prompts,
source order, model, output budget, timeout and review-only projection from the
[original protocol](ICORE_VISION_DEV3_PROTOCOL_20261013.md).

The parent authorized a fresh maximum of three serial Luna 6 requests with zero
SDK retries and stopping on the first provider error. The prior arm's one failed
attempt and unknown usage remain separately recorded.

Changes are limited to request bounds and receipts:

- Fit each complete page within 2,048 by 2,048 pixels, preserving aspect ratio,
  without upscaling. Maximum image area is 2,048 squared pixels and maximum PNG
  size is three million bytes.
- Limit the entire HTTP JSON body to 4 MiB (4,194,304 bytes), using the same JSON
  encoding as the installed HTTP transport. Record its prepared size and check
  the actual SDK request bytes in an HTTP request hook before transmission.
- Record the actual request-body hash and byte count, without request headers or
  credentials. Preserve sanitized full response bodies and usage/error receipts.
- Freeze a clean code commit, protocol hash and input/image/schema/request hashes
  into a separate protected external `icore-luna6-vision-dev3-v2` directory.

No label access occurs before this arm is sealed. No gold is added to requests.
There is still no automatic release, verified visual grounding, causal modality
ablation or production-quality claim. The product parser and all-review projection
are unchanged. This is a bounded request-contract correction after v1, not a
retry that overwrites failed evidence.

Five source-free tests verify the request/field contract, transport byte bounds,
image bounds, review-only values and stopping after the first provider rejection.
