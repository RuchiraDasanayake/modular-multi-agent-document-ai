# Product reply integrity fixes — 15 October 2026

Scope: `idpo/product_auto` is **core**; the primary action is **simplify**, through
defect cleanup. These changes harden the current product decoder and review
boundary. They do not change the completed studies, model routing, defaults,
request prompts, provider schemas or source-coverage budgets.

## Reproduced defects and corrections

| Defect | Synthetic reproduction | Correction |
| --- | --- | --- |
| A malformed reply aborts the remaining batch | A deeply nested plain reply raises `RecursionError`; an escaped lone surrogate in plain or strict-v1 values raises `UnicodeEncodeError` during artifact writing. In a two-file batch only the first fake model call occurs and no terminal `run.json` is written. | Schema and value replies share a bounded JSON decoder. It rejects duplicate properties, nonfinite numbers, excessive nesting reported by the decoder, invalid raw Unicode and lone surrogates decoded from JSON escapes. A rejected reply follows the existing per-document failure path; the next original executes and the terminal run marker accounts for both. |
| A visual proposal violates the frontend's typed-value contract | A strict-v2 integer reply containing `"two"` is published as reviewable with complete visual coverage. The exact frontend validator rejects that artifact. | Visual scalars must coerce to the confirmed type before the reply can count as valid. Invalid values fail the complete candidate with `visual_request_invalid_values`; no partial values or complete coverage are published. Valid coercions remain review-only. |
| Confirmed Unicode identity and evidence checks diverge across languages | The valid confirmed ID `straße` is rewritten to `strasse` by the value decoder, failing an otherwise conforming response. Separately, Python accepts `STRASSE` against quote `Straße` through case folding, while the frontend's lowercase check rejects it. | An exact known field ID is preserved before legacy alias normalization. Distinct confirmed IDs remain distinct. String and linked-cell evidence comparisons use lowercase, matching the existing frontend behavior in the tested cases; the expansion-only match remains for review. |

The visual rejection also covers invalid calendar dates, blank string values and
unparseable decimal/boolean strings. It does not infer a currency or reinterpret
an invalid value. Nulls remain absent, and supported numeric/boolean/date string
coercions retain their existing behavior.

## Verification

The initial 32-case regression file produced **22 failures and 10 passing
controls before the fixes**. Two further regressions cover distinct IDs that
would collide under legacy case folding and linked-cell evidence parity.

The final focused suite passed **138 tests**:

```powershell
python -m pytest `
  idpo/tests/test_product_auto_reply_integrity.py `
  idpo/tests/test_product_auto_grounding.py `
  idpo/tests/test_product_auto_linked.py `
  idpo/tests/test_product_auto_strict_output.py `
  idpo/tests/test_product_auto_strict_output_v2.py `
  idpo/tests/test_product_visual_workflow.py `
  idpo/tests/test_product_auto_long_document.py `
  idpo/tests/test_confirmed_schema_routing.py -q
```

This includes two-original hostile-reply isolation, terminal `run.json` output,
both strict visual profiles, unchanged valid coercions, exact confirmed Unicode
IDs, scalar and linked evidence checks, existing linked-row/segment behavior,
and the existing strict-v1 prompt hash regression. One older grounding test
incorrectly expected `needs_review` after an invalid numeric reply; its
expectation and name now match the pre-existing `failed` behavior.

A separate synthetic check generated 17 Python candidates, including valid typed
visual outputs, rejected visual documents, confirmed Unicode IDs and scalar/
linked evidence cases. All 17 passed the exact current frontend validator
functions executed in isolation. This is contract parity evidence; it is not a
browser or authenticated HTTP workflow test.

Source comparisons confirmed unchanged prompt/compiler function ASTs and
unchanged workflow, provider, routing, image planning and confirmed-schema
modules. No external model or real OCR calls were made. No sealed predictions,
reference/gold files, benchmark outputs or conference artifacts were changed or
used as tuning input.

## Boundaries

Plain replies now share the strict decoder's 1,000,000-byte limit and
duplicate-property rejection. Strict wire profiles and all configuration
defaults retain their identities. Artifact and HTTP contracts are unchanged.

These checks prevent specific crashes and unusable artifacts. They do not prove
that a model chose the correct field, preserved a real document's row linkage,
or extracted all values. Source coverage and typed JSON are distinct from
semantic accuracy. The completed study results remain frozen and do not measure
these later product fixes.

## Later integration checks

The unchanged-workflow source comparison above refers to the reply-integrity
fix itself. The later [product JSON guard](PRODUCT_JSON_INPUT_20261015.md)
intentionally changes product workflow and JSON sample admission; it leaves
research intake and the completed studies unchanged.

One broader OCR regression still expected the old RapidOCR-specific multiframe
failure. Existing commit `2e05f03` had already moved rejection before OCR for all
product image engines. The test now expects `multi_frame_image_unsupported` and
`unsupported`, proves that `OcrAgent.run` is never called, and verifies one
terminal source. Its file passes five tests; its optional live test skips when
the isolated RapidOCR runtime and synthetic font are not explicitly configured.
The second optional live skip is in `test_product_rapid_ocr.py` for the same
`TEST_RAPIDOCR_PYTHON` / `TEST_RAPIDOCR_FONT` prerequisites.

The native app's resolved Node runtime is **22.20.0**. Its complete upload-stream
test file passes all 16 cases. The same file under bundled Node **24.19.0**
reproduces synthetic FormData cancellation errors inside Undici and an
intermittent later 400 response; the valid two-file case alone passes on both
versions. This identifies a direct-test runtime boundary, not a demonstrated
failure of the configured native app or a browser upload. No upload runtime
code was changed. The valid-upload assertion now includes an error response
body when it fails, to make future diagnostics actionable.


