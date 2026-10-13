# Reserved paired quality evaluation: frozen protocol

Status: frozen before inference and reference access, 13 October 2026.
Surface: `research_evidence`; action: `keep`.

The [source audit](QUALITY240_SOURCE_AUDIT_20261013.md) preceded a complete
rehash of all 240 originals. No OCR, model call or reference-label access was
performed during that freeze. Both arm ledgers contained 240 unstarted sources
and zero attempts when the analysis plan was registered.

## Immutable identities

| Item | SHA-256 |
| --- | --- |
| Execution protocol | `3cf41aac59be90d610a4479d1d9876bbf77894e9d55162983a8713b510594075` |
| Analysis plan | `68ba30cb8831a5805c49b0b340a83e88429720de249a2986f92efc4ea676974e` |
| Registration receipt | `7d267e6bc129c62e9c19c1323ac71da358a659132b213dc232e5af6c0d77ad30` |
| Source inventory | `214def43738fd2bafb3102d80b4f26287e5b405140206abc767c361521e135ab` |

Execution checkout: `1d1d55a501b007f6d815f4880517c3ec980b1607`. Its extraction
backend matches the selective-v2 candidate `0cce810`; the additional commit
introduces the paired coordinator, its tests and documentation. Private output:
`I:/DocAI-Benchmarks/quality240-selective-v2-20261013`.

## Fixed comparison

- 100 registration PDFs, 100 ad-buy PDFs and 40 receipt images. The stored source
  hashes are disjoint from the operational 2,000 and the six development sources.
  Template, vendor and pretraining independence are not established.
- The same three confirmed schemas, Luna 6 and fresh RapidOCR intake per arm.
  Compare bounded strict text with the development-selected selective visual v2
  path. Schema discovery is not measured by this experiment.
- Family-interleaved, counterbalanced adjacent pairs; one worker; checkpoints
  after 25 original pairs. Four attempts per source-arm maximum, 960 per arm,
  1,920 total, no SDK retries. Uncertain attempts are never replayed.
- A provider or integrity failure stops the coordinator. Explicit acknowledgement
  of a resumable provider incident permits only untouched source-arm slots.
  All 480 source-arm outcomes remain in the sealed denominator, including failures
  and any unattempted slots.
- Seal and independently verify predictions, originals and artifact receipts
  before accessing references. Hash reference inputs and conversions at first
  authorized access after that verification.

## Analysis fixed before results

Primary outcomes are creator-derived positive scalar-target recall and
order-independent, one-to-one annotated whole-row recall. Preserve historical
ordered-list scalar targets and report their type mismatch separately. Keep
ordinal-cell diagnostics separate. CORD labels are partial: no complete-document
accuracy, precision or F1 claim follows from them.

The paired uncertainty calculation resamples original documents within each
family, using the same multiplicities for both arms. It uses NumPy `default_rng`,
seed 20261013, 10,000 resamples and linear 2.5/97.5 percentile intervals. Scalar
macro recall weights all three families equally; row macro recall weights ad-buy
and receipt equally. A zero denominator is undefined and the estimable replicate
count is reported. Failed sources retain their reference counts with zero matches.

`product_eval/paired_uncertainty.py` implements that calculation independently
of reference loading and scoring. Synthetic tests check paired equality, known
sampling calculations, failure retention, macro weights, undefined denominators
and rejection of missing/duplicate originals. Its implementation was written
before quality240 inference or label access; it changes no historical metric.

The protocol contains no numerical practical-accuracy or monetary release
threshold. This is a comparative research evaluation. Token usage, coverage,
provider errors and latency are separate outcomes; dollar cost and human review
time remain unavailable. No threshold will be invented after seeing the results
and represented as a preregistered release requirement.
