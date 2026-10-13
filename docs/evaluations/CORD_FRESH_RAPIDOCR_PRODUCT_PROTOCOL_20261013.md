# Fresh RapidOCR through the product: two development receipts

Classification: research_evidence; action: keep.

This diagnostic tests the newly integrated product adapter on exactly the two
previously selected original receipt images from the
[cached replay](CORD_LUNA_OCR_REPLAY_PROTOCOL_20261013.md). It includes fresh intake,
fresh local OCR, unchanged supplied-schema prompting and product artifact checks.

## Frozen design

- Source selection, original bytes and receipt schema are fixed by the prior replay
  protocol SHA `e793c023601c4b91972aee96b37c0078406af78d0f602f920f856a663df7711c`.
  Prepare verifies the two original hashes, image bounds and exact RGB PNG identity.
- Use only the explicit RapidOCR product engine: pinned PP-OCRv6-small models,
  RapidOCR 3.10.0 and ONNX Runtime 1.31.0. One child per page, CPU only, 120-second
  timeout, 1536 MiB sampled RSS threshold. Previous cached OCR used ORT 1.23.2.
- Maximum two Luna 6 calls, one per original, 8192 output tokens and 180-second
  timeout, sequential execution, no SDK retries. No Sonnet, vision, row-geometry
  prompt, new schema induction or value-specific prompt changes.
- Invoke `process_auto` on the actual original files, not cached OCR or injected
  pages. Preserve complete product candidates, sidecars, manifests and provenance.
  Audit input-raster hash, model identity, exact text hash and every line offset.
- Save requests, redacted raw HTTP responses and replies privately. Verify both
  distinct source receipts and seal every output hash before a separate scorer
  reads existing development gold. Keep both originals in denominators, including
  OCR or model failures. The exclusive attempt marker prevents billed reruns.
- Score raw scalar strings and complete annotated menu rows separately, using the
  same scoped scorer as the previous replay. Positive-only labels do not support
  precision, false-positive or F1 claims. Report proposed and machine-accepted
  results separately; text validation does not establish image correctness.

The runner is `product_eval/cord_rapidocr_product_smoke.py`. Prepare and run require
a clean committed checkout. The frozen protocol records the complete Python source
inventory and original/schema hashes. No reserved images or labels are opened.

This is a two-document development comparison. It can establish that the adapter
is usable in the product path and expose failures. It cannot establish general
accuracy, calibrated automatic acceptance, scalability, a default-engine decision,
or completion of the final 2,000-document extraction requirement. Dollar prices
remain unknown unless independently verified.
