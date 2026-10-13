# Receipt OCR replay with Luna 6: useful scalar gain, rows unresolved

Classification: `research_evidence`; primary action: `keep`.

The [frozen two-receipt replay](CORD_LUNA_OCR_REPLAY_PROTOCOL_20261013.md) completed
two Luna 6 calls without provider errors or retries. The sealed RapidOCR PP-OCRv6
small page strings replaced the Tesseract page strings, while the exact receipt
schema, extraction prompt, product parser and grounding rules stayed fixed.

| Development measure, same two original images | Product Tesseract baseline | Cached RapidOCR replay |
| --- | ---: | ---: |
| Exact proposed scalar strings | 2/7 | 4/7 |
| Exact machine-accepted scalar strings | 2/7 | 4/7 |
| Complete annotated menu rows, order independent | 1/7 | 0/7 |
| Proposed linked cells | 11 | 3 |
| Documents requiring review | 2/2 | 2/2 |

The baseline is the receipt subset of the [six-document supplied-schema run](ICORE_CONFIRMED_SCHEMA_DEV6_RESULTS_20261013.md).
Positive-only labels leave precision, false positives and F1 unassessed. Machine
acceptance means the value passed text checks; it is not human approval or proof
that OCR matches the image. All exported releases still require the product's
review contract. The three incorrect scalar strings were nevertheless machine
accepted because the quoted OCR text contained them.

## Observed failure mechanisms

The first receipt's page text became readable. Cash and change matched the labels;
three other amounts differed only in printed comma versus OCR period separators.
The strict raw-string comparison preserves those three errors. One menu row was
proposed, but its price had the same separator difference and ambiguous repeated
text evidence. No locale normalization was introduced after scoring.

The second receipt's cached text contained names and prices but omitted the
quantity column. Several item names also wrapped around intervening prices. The
model returned null for all three repeated columns. The frozen intent asks for
complete row relationships; conservative abstention can therefore discard known
cells when another column is unreadable. This is a reason to test visual evidence
and explicit partial-row handling, not to weaken source checks or invent quantities.

## Receipts and limits

- Code: `7775cb0`; protocol SHA:
  `e793c023601c4b91972aee96b37c0078406af78d0f602f920f856a663df7711c`.
- Two model calls, 1,324 reported prompt tokens and 2,323 completion tokens;
  26.2 seconds for replay and model work. No fresh OCR execution, no vision.
- Output candidates SHA:
  `803ece6a25064dd9c319ebf869c5ec4badf7a438d467911dc304910572b1e996`.
- Original images, schema bytes, cached page identities and offsets were checked
  before calls. All sealed output hashes were verified before reading development
  gold. Requests, raw HTTP bodies, replies, source references and assessment remain
  outside Git in the `cord-luna-rapid-replay-v1` experiment directory.
- Provider dollar prices are unverified, so dollar cost remains unknown. Runtime
  and resource use of fresh OCR come from the earlier separate OCR experiment.
- These are two previously used development receipts. The gain is diagnostic;
  no statistical or generalization claim is supported. The reserved forty receipts
  were not opened and the final 2,000-document requirement remains outstanding.

**Decision:** reuse the stronger local OCR implementation in a bounded candidate
adapter and measure the entire path. Retain human review. Test visual recovery and
partial rows before expanding the quality evaluation; text-only OCR replacement
has not solved repeated-row extraction.
