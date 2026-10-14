# Paired quality results on 240 reserved originals

Classification: `research_evidence`; action: `keep`.

Status: execution closed, predictions independently verified, references scored and
231 independent numeric reconciliation checks passed on 14 October 2026.

The selective path produced mixed results. Its scalar macro recall was 65.09%
versus 64.77% for strict text, a paired difference of +0.31 percentage points
(95% interval −3.93 to +4.58). Whole-row macro recall was 41.74% versus 34.13%,
a difference of +7.61 points (−1.34 to +17.76). Both macro difference intervals
include zero. Receipt whole-row agreement improved, while ad-buy whole-row
agreement declined. Known token usage increased; USD cost remains unavailable.
This result does not establish a general accuracy or lower-cost advantage.

## Design and interpretation

The frozen cohort contains 100 registration PDFs, 100 ad-buy PDFs and 40 CORD-v2
test receipt images. All 240 original byte hashes are distinct and disjoint from
the six development originals and the operational 2,000-original cohort. This is
not the official VRDU unseen-template split or the complete CORD benchmark;
vendor, template and pretraining independence are not established.

Both arms use the same fixed family schemas, the requested `innobot-luna-6` alias,
fresh local intake/RapidOCR, an 8,192-output-token limit and 180-second requests.
Family-interleaved adjacent pairs counterbalance first-arm order. One worker,
four requests per source-arm, 960 requests per arm, 1,920 globally and zero SDK
retries were registered. The comparison concerns complete execution paths:
prompts, response contracts and admitted modalities differ. It does not isolate
the causal effect of image input alone.

The primary outcomes are creator-derived positive scalar-target recall and
order-independent, one-to-one annotated whole-row recall, preserving duplicate
rows and their cell links. Partial positive labels leave extra predictions
unassessed; these results do not supply complete-document precision, F1 or
independently adjudicated visual truth. Automatic schema discovery, human release
quality, review effort and real-document RABI/DAAF benefit were not measured.

All **480 assigned source-arm outcomes** remain in the final accounting. Failed
sources retain their reference targets with zero matches. Uncertain paid attempts
were preserved and never replayed. There were zero unstarted slots at sealing.

## Primary results

Values are matches/reference targets and recall percentages. Macro values weight
families equally rather than pooling their target counts. The paired difference
is selective minus text in percentage points, calculated before rounding.

| Outcome | Strict text | Selective v2 | Paired difference [95% interval] |
|---|---:|---:|---:|
| Registration scalar | 252/460 (54.78%) | 252/460 (54.78%) | +0.00 [−4.22, +4.23] |
| Ad-buy scalar | 473/768 (61.59%) | 456/768 (59.38%) | −2.21 [−8.46, +3.99] |
| Receipt scalar | 99/127 (77.95%) | 103/127 (81.10%) | +3.15 [−7.38, +13.28] |
| Scalar macro | 64.77% | 65.09% | +0.31 [−3.93, +4.58] |
| Ad-buy whole row | 376/1,409 (26.69%) | 258/1,409 (18.31%) | −8.37 [−19.53, +3.08] |
| Receipt whole row | 37/89 (41.57%) | 58/89 (65.17%) | +23.60 [+9.62, +40.23] |
| Whole-row macro | 34.13% | 41.74% | +7.61 [−1.34, +17.76] |

The fixed paired bootstrap resamples originals within family using the same
multiplicities in both arms: NumPy `default_rng`, seed 20261013, 10,000 resamples
and linear 2.5/97.5 percentile intervals. Scalar macro gives each of three families
weight 1/3; row macro gives ad-buy and receipt weight 1/2. All seven primary
outcomes have 10,000 estimable replicates for each arm and the paired difference.
Intervals are descriptive and unadjusted for multiple comparisons. Full unrounded
estimates, **each arm's interval**, paired intervals and estimable counts are in
[`aggregate-results.json`](quality240_20261014/aggregate-results.json), under
`primary_metric_uncertainty`.

The 1,355 primary scalar targets include **54 historical ordered-list targets**,
all in ad-buy. The frozen adapter encodes divergent acceptable scalar occurrences
as ordered lists, while these output fields require scalar strings. Both arms
therefore have 54 schema/list incompatibilities and match 0/54 of these targets.
They remain in the primary denominator. The separately named string-only ad-buy
diagnostic is 473/714 (66.25%) for text and 456/714 (63.87%) for selective.
[`secondary-diagnostics.json`](quality240_20261014/secondary-diagnostics.json)
preserves those diagnostics, historical ordered-list outcomes, incompatibility
counts and ordinal-cell results. Ordinal cells are sensitive to row position and
cannot replace the linked whole-row metric. Zero-denominator secondary outcomes
remain undefined.

## Coverage, failures and actual routes

| Family | Selected per arm | Text valid full coverage | Selective valid full coverage | Text uncertain sources | Selective uncertain sources |
|---|---:|---:|---:|---:|---:|
| Registration | 100 | 95 | 95 | 5 | 5 |
| Ad-buy | 100 | 89 | 86 | 8 | 9 |
| Receipt | 40 | 38 | 36 | 1 | 0 |
| Total | 240 | **222** | **217** | **14** | **14** |

Each arm has 226 `sealed` and 14 `uncertain` source states. Sealed is a terminal
ledger state and includes unsuccessful results: four text and nine selective
sealed sources do not meet valid full coverage. Validity and complete recorded
input coverage do not establish correct values. All valid proposals require
human review. The 28 uncertain sources differ from 27 uncertain attempts
(13 text, 14 selective); one text source was interrupted without a model attempt.
Both arms have begun-request markers for 238 originals.

Actual source routes were text 238/unexecuted 2 for the baseline and text
176/visual 62/unexecuted 2 for selective. Selective's 247 requests comprise
176 text and 71 visual requests; the baseline has 239 text requests. A source
can need multiple planned requests, and a source's paired arm can finish after
the other arm fails. These counts must not be described as 240 image extractions
or successful model completions per arm.

## Usage and latency

| Recorded quantity | Strict text | Selective v2 |
|---|---:|---:|
| Begun-request/known SDK attempts | 239 | 247 |
| Known input tokens | 507,706 | 1,224,006 |
| Known output tokens | 370,741 | 373,174 |
| Known input + output components | 878,447 | 1,597,180 |
| Attempts with unknown usage | 13 | 16 |
| Request latency p50 / p95 | 11.184 / 47.359 s | 14.515 / 51.878 s |
| Request times measured / missing | 239 / 0 | 247 / 0 |
| Source execution duration p50 / p95 | 23.477 / 59.983 s | 24.413 / 68.192 s |
| Source durations measured / missing | 239 / 1 | 240 / 0 |

Request quantiles include measured failed and uncertain attempts. Source duration
uses the worker's monotonic interval from source verification through product
verification, including OCR and provider calls and excluding outcome persistence;
measured pre-model failures are retained. Quantiles use linear interpolation at
`(n−1) × p`. The JSON contains family slices and the separate model-attempted-source
population. Missing measurements remain missing.

Selective used 1.82 times as many **known reported token components**. Unknown
usage is not zero usage, and token totals are not a verified USD bill. Provider
pricing, cost per correct document and active human review time are unavailable.

The recorded control-start to last-source-close span is **77,117.874 seconds**,
from 13 October 2026 18:56:11.021733 UTC to 14 October 2026 16:21:28.895967 UTC.
It includes provider/operator pauses, integrity checks and backoff; it excludes
later sealing and analysis. Exact process-active duration was not recorded.
This span is not an isolated throughput measurement. The distinct start-to-final-
preseal-checkpoint span is 77,118.860 seconds; it uses a later endpoint and must
not replace the recorded source-closure span. Summed request durations are
4,309.222 text and 4,932.661 selective seconds and are not campaign wall time.

## Execution amendments and provider incidents

After inference began and before reference access, a pinned amendment changed
authentication and the endpoint to the dedicated project route. The requested
model alias stayed `innobot-luna-6`; immutable weights and equivalence between
routes remain unverified. Source-arm transport cohorts and begun requests are:

| Arm | Personal / project source-arm cohort | Personal / project requests |
|---|---:|---:|
| Text | 47 / 193 | 46 / 193 |
| Selective | 48 / 192 | 48 / 199 |

An HTTP 408 preservation resolution retained the original `request_rejected`
classification, failed outcome, unknown usage and denominator. It permitted only
untouched slots to continue. The control chain contains one start, **30 stops and
30 acknowledgements**. The sealed saved-error metadata records 11 HTTP 502,
10 HTTP 503, three HTTP 504, one HTTP 408, one HTTP 429, one connection error and
two timeouts. Recorded categories are 24 `provider_server`, one
`transport_connect`, two `transport_timeout`, one `rate_limit` and one
`request_rejected`. They do not identify whether an underlying server failure
was capacity, quota or another cause. Error counts, uncertain attempts and
uncertain sources are different quantities.

[`incident-accounting.json`](quality240_20261014/incident-accounting.json)
contains aggregate counts and amendment pins. Failed and unknown outcomes were
not replayed or replaced with synthetic successes. Small successful availability
checks established only small-request availability and were separate from this
registered comparison.

## Verification and provenance

The independent prediction verification passed before reference loading. Scoring
reverified the sealed evidence before label access. A later count-only independent
audit passed 231 checks, re-expressed the paired bootstrap with zero interval-endpoint
differences and independently recomputed source-duration quantiles. It did not
perform independent semantic reference adjudication; request quantile populations
and sums were reconciled with the pinned attestations.

| Artifact | SHA-256 |
|---|---|
| Registered execution protocol | `3cf41aac59be90d610a4479d1d9876bbf77894e9d55162983a8713b510594075` |
| Prediction seal | `baed791acffbaa44171525cb51810f808db691615eebbc83b99890a75d3229cd` |
| Independent pre-label verification | `3d7cfc983a5cf9d04eff67e21b3bc26c3b2bfe9682f53ae0544bddf82010347e` |
| Scoring receipt | `ac97bdd7dfc29b9e612ffcf6e623c74e757971009b45d9495d17f95e87388809` |
| Full private derived result | `61a3ba744005d607dcb7be931988bd8058395af2749bfb90ff514ddb96b75f45` |
| Timing report | `d9531b68ff439d104d1908919502d9f94c1a7e4aa611b8db6e4e55562b58b3d3` |
| Independent numeric audit | `731cbe90e26c3d3442e349a2e37882921fe44862f81413f141a6311574bf2f7e` |
| Public primary aggregate | `4790ed93d0766a61785ab4317fe31c7913214afe1dc0e8b3fc50595660192148` |

The registered execution coordinator is `1d1d55a501b007f6d815f4880517c3ec980b1607`;
the pinned public analysis revision is
[`f2a8ef93b92757845c67fe86aeec5c3a4e14754c`](https://github.com/RuchiraDasanayake/modular-multi-agent-document-ai/tree/f2a8ef93b92757845c67fe86aeec5c3a4e14754c).
The [reviewed package](quality240_20261014/README.md) provides exact schema bytes,
source-only reconstruction metadata and safe aggregates. The
[publication manifest](quality240_20261014/publication-manifest.json) records
original-to-public hashes and every publication transformation. Individual source
identities are deliberately confined to the reconstruction manifest; metric,
incident and union aggregates contain no individual identities or raw values.
Source documents, labels, predictions, credentials and raw requests/responses are
not redistributed. A verified private archive retains the prediction seal and
its 7,237 registered files on the same drive; it is not disaster recovery.

## Decision and limits

Retain strict text as the comparator. These data support a family-specific receipt
row result and expose worse ad-buy row agreement, greater known token usage and
provider uncertainty. Both macro difference intervals cross zero. There is no
registered numerical product-release threshold, and none is invented after the
results. This study does not validate automatic schema discovery, arbitrary
documents, lower monetary cost, human-release accuracy or deployed adaptive-memory
benefit. The separate [distinct-original union](VERIFIED_SOURCE_UNION_RESULT_20261014.md)
accounts for operational volume while preserving each study's denominator and the
failed operational 2,000-source gate.
