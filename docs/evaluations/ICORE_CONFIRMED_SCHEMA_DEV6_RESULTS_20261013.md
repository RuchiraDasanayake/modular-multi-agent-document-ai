# ICORE supplied-schema smoke: six development originals

## Scope and receipts

This retained `research_evidence` report describes a diagnostic, not a holdout
result or the final 2,000-source experiment. The protocol is
[the frozen six-source plan](ICORE_CONFIRMED_SCHEMA_DEV6_PROTOCOL_20261013.md).
Code was clean at `4660c08e96ae3762d82817f0d813539de65039f9` before inference.
Protocol SHA-256: `f69920e4113b37061f22209f52e52af427006c75706dbb05dfcb7e15e3301356`.
The protected external run directory is `icore-confirmed-schema-dev6-v2` under
the operator's benchmark root. Its `summary.json`, `calls.jsonl`,
`sealed-run-verification.json`, source/result receipts, requests, sanitized raw
HTTP bodies and parsed replies preserve the execution. No credentials or source
content are included in this report. The earlier v1 directory was preparation
only and made no API calls.

All six original-file hashes and six product result receipts verified. The five
requests contained exactly the frozen family fields, intent and fresh product
page text. Verification was sealed before reading the already-used development
gold. No reserved or quality240 labels were opened. Python 3.13.8, pypdf 6.5.0,
pypdfium2 5.14.0 and Tesseract 5.5.3 provided intake; this was the existing native
text/Tesseract route, without a vision request or a local generative model.

## Measured outcomes

- Six terminal product outcomes, all `needs_review`; zero automatic releases.
- Five `innobot-luna-6` calls, zero retries, discovery calls or response repairs.
- Five structurally valid replies; no transport/provider error.
- 5,535 prompt + 5,777 completion = **11,312 reported tokens**; **94.6 s** total
  elapsed execution. Dollar cost is unknown without billed rates/charges.
- The sixth-page ad-buy document contained 28,772 text characters and hit the
  existing 24,000-character product cap before any model call. It remains in all
  denominators. No replacement source or extra call was used.

| Family (two originals each) | Exact proposed scalar strings | Exact accepted scalar strings | Annotated whole-row matches |
| --- | ---: | ---: | ---: |
| VRDU registration | 4/10 | 4/10 | Not applicable |
| VRDU ad-buy | 2/15 | 1/15 | 1/36 |
| CORD receipts | 2/7 | 2/7 | 1/7 |

Two additional ad-buy fields have scalar-list labels; neither was recovered, and
the current supplied-schema contract cannot express those lists. Thus the
non-linked totals are 8/32 exact proposed strings plus 0/2 scalar-list fields,
and 7/32 exact accepted strings. An accepted value still has pending human
review. The six-page blocked ad-buy accounts for 30 of its family's 36 rows.

Rows use order-independent, one-to-one matching from `scope_aware_v1`; a CORD row
checks its annotated cells only. CORD is positive-only, so unmatched predictions
and extra fields are **unassessed**, not established hallucinations. Do not pool
these heterogeneous denominators into a headline accuracy or report CORD
precision. The old ordinal diagnostic is retained separately: 8/171 ad-buy and
8/21 CORD proposed cells match exactly.

Thirteen VRDU accepted values quote genuine fresh product text. All thirteen
gold-span coordinate comparisons are incompatible because the frozen gold and
candidate text hashes differ. Quote authenticity is not proof of a correct
value, visible source correspondence or gold-span support. CORD has no gold text
span annotations here. All historical scores and references remain unchanged.

## Reproduced failure causes

1. **Invisible native text replaces visible form content.** Rendered first pages
   of both registration PDFs contain completed scanned forms. Their native text
   layer instead contains invisible administrative metadata (`Tr=3`) over a
   full-page raster. The product's length/cleanliness shortcut uses this metadata
   and skips OCR. The model never receives the visible foreign-principal text.
   Metadata registrant names also differ from the visible completed fields.
2. **The ad-buy scan's hidden OCR layer is corrupt.** Its first-page native text
   also uses `Tr=3`. Words, columns and dates run together; the model preserves
   wrong characters and omits most row dates. One semantic mistake selects the
   station/channel label as the property name. Invisible text can be valid OCR
   in other searchable PDFs; visibility alone does not prove corruption.
3. **Receipt OCR loses content and grouping.** Receipt 0083 produces nearly
   unreadable text and a wrong cash value with an authentic OCR quote. Receipt
   0017 preserves totals but damages item spelling and multiline row grouping.
   A stronger text-only model cannot recover information absent from its input.
4. **Long-document coverage is absent.** One six-page original is rejected as a
   whole despite readable text. A bounded page/chunk strategy is needed, with
   explicit partial coverage and document/row reconciliation.
5. **Evidence ambiguity withholds a correct proposal.** The correct ad-buy gross
   amount has a repeated short quote. It remains review-required; better context
   or a spatial locator is preferable to accepting an arbitrary occurrence.
6. **Some exact-score failures are specification/annotation issues.** The frozen
   registration `file_date` meaning excludes report/signature dates, but these
   two development labels use them. One ad-buy date reference is visibly
   truncated while the proposed start date is complete. Word spacing and
   punctuation also penalize otherwise similar strings. These observations do
   not change the frozen scores. Any revised field meanings or normalized
   scoring must be specified before a new holdout experiment.

## Decision

Do not run the final 2,000-source quality experiment on this configuration.
First fix PDF native-text representativeness and retain the rejection reason,
original text hash, OCR route and fresh page evidence. Recheck the same six
development originals with unchanged schemas and bounded calls to isolate that
change. Then address long-document coverage and evaluate a vision or layout
route for scans whose OCR still loses values. Neither this six-source result nor
the earlier NuExtract run (different schema shapes and modalities) establishes a
controlled model ranking, low dollar cost or production accuracy.
