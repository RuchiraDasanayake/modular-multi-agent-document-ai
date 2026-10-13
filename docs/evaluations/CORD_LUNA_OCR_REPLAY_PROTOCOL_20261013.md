# Cached receipt OCR with supplied-schema extraction

Classification: `research_evidence`; primary action: `keep`. This bounded diagnostic
tests a specific failure behind the poor six-document development extraction:
whether the already measured PP-OCRv6 small text is useful to the confirmed-schema
Luna 6 extractor. It does not install or promote another product OCR path.

## Frozen comparison

- Exactly the two receipt originals from the supplied-schema six-document baseline.
- Reuse their complete page text from the sealed 60-document RapidOCR development
  cache. Verify cache, original image, document identity, and line-offset hashes.
- Copy the baseline receipt schema byte for byte. Use unchanged product value
  prompting, parser, grounding checks, and review rules.
- Maximum two Luna 6 calls, one per source, 8,192 output tokens, 180-second timeout,
  sequential execution, no SDK retries. Record request, raw response, reply, usage,
  and failure receipts. Do not use Sonnet.
- Seal outputs before offline scoring with the existing development positive labels.
  Keep both documents in denominators; extra predictions remain unassessed under
  partial labels. Report scalar-string and complete annotated-row recall separately.
- No reserved images or labels, gold-derived prompts, image geometry in prompts,
  vision calls, schema discovery, or value-specific prompt modifications.

The runner is `product_eval/cord_model_ocr_replay.py`. Its `prepare` command accepts
the baseline protocol, sealed OCR cache and a new private output directory. `run`
requires that protocol SHA and a credential file. The frozen code checkout must be
clean. Existing attempt markers prevent replaying billed calls under the same run.

## Interpretation

The baseline used the product's adaptive Tesseract path. The candidate replays
previously measured full-page RapidOCR output; it does not measure current OCR
runtime, original intake, or fresh end-to-end latency. Only downstream extraction
and model usage are measured. A gain justifies implementing and testing a real
adapter. Two familiar development receipts cannot establish general-purpose
accuracy, reliable automatic acceptance, or fulfil the 2,000-document requirement.

RapidOCR provides a reusable local ONNX OCR implementation; the project's official
[repository](https://github.com/RapidAI/RapidOCR) documents installation and licensing.
The pinned earlier OCR experiment, including exact model hashes and runtime, is
documented in [the full-page result](CORD_FULL_PAGE_OCR_DEV_RESULT_20261012.md).
