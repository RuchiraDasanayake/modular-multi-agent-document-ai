# Selective visual routing v2

This opt-in routing profile was selected after the
[six-source paired development comparison](PAIRED_PRODUCT_DEV6_RESULTS_20261013.md),
before opening the reserved 240-source quality references. It is a candidate
decision, not a validated accuracy or cost claim.

The comparison recovered 29/43 complete annotated rows with bounded images
versus 0/43 using text alone. However, image input used 3.83 times as many
tokens overall. On the two registration forms it used 7.97 times as many
tokens with the same strict scalar count. The six additional scalar matches
came entirely from a long ad document whose text reply was truncated.

## Decision

`bounded_visual_selective_v2` retains the existing bounded image preparation,
strict output, complete-page accounting and mandatory human review. Before
any model call it chooses the image route for an image or PDF requiring OCR
when at least one of these conditions applies:

- The confirmed schema contains repeated columns (`array[object]`).
- There is no usable OCR text.
- Extracted text exceeds the strict single-call limit of 24,000 characters.

Short scalar schemas with usable text use the strict text route. Native text
PDFs and native Office/text formats keep their existing text route. Incomplete
PDF OCR page coverage retains the failure guard; selection cannot bypass it.
The profile performs no paid fallback after a failed text call.

The no-text branch is a bounded recovery rule; its real-document accuracy has
not been established by the six-document result. Long source text and the
presence of repeated fields are routing signals, not proof that image input
will be more accurate on every source.

## Reproducibility and verification

`bounded_visual_v1` keeps its original behavior. Queued jobs seal the exact
profile string, and runtime, CLI, native configuration and the model-gate
freezer explicitly validate both versions. Receipts identify the actual
route and its reason. Selection uses the confirmed schema and source text,
never reference answers, dataset family names or measured correctness.

Synthetic integration checks exercise repeated fields, empty OCR, long text,
short scalar text, the exact 24,000-character boundary, incomplete PDF page
coverage and native-format handling. The final-gate tests exercise both
profiles through real local intake and image preparation with fake providers.
The reserved paired evaluation will compare text-only extraction against
this profile on all preselected sources, including failures and abstentions.
