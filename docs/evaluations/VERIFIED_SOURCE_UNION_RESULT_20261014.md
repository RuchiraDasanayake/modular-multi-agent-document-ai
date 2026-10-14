# Verified distinct-original union of the two completed studies

Classification: `research_evidence`; action: `keep`.

Status: separately verified operational and paired-study attestations reconciled,
14 October 2026. Only the selective `candidate` quality arm contributes to this
union; the paired text baseline contributes no sources, attempts or results.

The two source-disjoint inventories contain **2,240 selected originals**.
Begun-request markers cover **2,225**, strict valid replies with complete recorded
source coverage cover **2,147**, and **2,146** have at least one non-null proposal
under those coverage criteria. These are structural processing counts. They do
not establish correct documents, complete semantic extraction or human release.

## Stage counts with separate denominators

| Stage | Operational study | Quality selective arm | Distinct union |
|---|---:|---:|---:|
| Selected originals | 2,000 | 240 | **2,240** |
| Originals with a begun request | 1,987 | 238 | **2,225** |
| Valid full-coverage originals | 1,930 | 217 | **2,147** |
| Non-null valid full-coverage originals | 1,929 | 217 | **2,146** |

The stage sets have zero shared original byte hashes between studies. An original
is counted once at each stage. No pair of partial outputs is combined into a
successful original. The helper retains both study denominators and their
uncertainty rather than treating the quality baseline as additional volume.
Byte disjointness does not establish template, vendor or pretraining independence.

| Family | Selected | Begun request | Valid full coverage | Non-null full coverage |
|---|---:|---:|---:|---:|
| Registration | 997 | 997 | 988 | 987 |
| Ad-buy | 405 | 400 | 373 | 373 |
| Receipt | 838 | 828 | 786 | 786 |
| Total | **2,240** | **2,225** | **2,147** | **2,146** |

A begun-request marker does not prove delivery, completion or billing. Valid full
coverage requires the existing verifier's strict parsed replies and complete
recorded source scope. A non-null proposal can still be wrong. All valid proposals
require review. No accuracy, active human review time or USD cost is measured by
this union.

## The operational gate remains failed

The original operational study still has 1,930 valid full-coverage outputs among
its 2,000 selected originals, with 13 pre-model rejections, 26 uncertain provider
sources and 31 invalid-values sources. It has 1,974 sealed and 26 uncertain ledger
states. Its all-source operational gate **did not pass**. Adding the separate
quality cohort does not change that outcome or its historical denominator.

The quality selective arm has 226 sealed and 14 uncertain source states, including
217 valid full-coverage outputs. Its 247 begun requests have 14 uncertain attempts
and 16 attempts with unknown usage; missing input and output usage refer to the
same 16 attempts and must not be added to make 32. The operational study has 2,053
known SDK attempts, 26 uncertain attempts and 26 attempts with unknown usage.
Request and ledger counters do not establish billing or correctness.

The registered extraction profiles retain the same model alias, OCR, strict
output, long-document and selective-visual settings. Study execution differs:
the operational run used four workers and a 2,500-request campaign cap, while
quality used one worker, paired ordering and a 960-request cap per arm. Endpoint
amendments, provider uncertainty and immutable model-weight limitations remain
disclosed in the [paired quality report](QUALITY240_RESULTS_20261014.md). Quality
scores are not pooled with these operational counts.

## Verification and public projection

The union helper consumed pinned completed operational verification/receipt files
and quality scoring/verification attestations. It did not rerun their complete
source, prediction and reference verification. Its no-label/no-prediction access
flags describe this metadata calculation, not the earlier quality scorer.
The subsequent independent numeric reconciliation passed all 231 checks across
the paired results and supplied operational/union reports. This is not independent
semantic annotation or a new extraction run.

[`source-union.json`](quality240_20261014/source-union.json) publishes stage,
family and study totals, profile hashes and input pins. The private original-level
list is omitted. The separately reviewed
[reconstruction manifest](quality240_20261014/reconstruction-manifest.json)
intentionally retains public corpus identifiers for reproducing the quality
cohort; no original identities or values appear in the union aggregate.

| Artifact | SHA-256 |
|---|---|
| Original private union report | `b69438a7555fc191c230eeef7bd9220950d92e092c9ae424cb1eeefb0a83b9f2` |
| Public union aggregate | `f1a8ffacd2a4f51edb2f95b6a96b91cdf28b65c7f01171b55d84b478c4fe78fc` |
| Operational verification | `d18822bee95558bc66b34452152868104acf4e3b2571eda82e0916d8555ec4cb` |
| Operational receipt | `a1f6023f66002abb37bb5b9c1b57fdf519670392b60462601c79081f133fa57f` |
| Operational seal | `700e380ff440b93e485ad90e511c93b2f82e126dd8013a2a7878b346e44c97ea` |
| Quality scoring receipt | `ac97bdd7dfc29b9e612ffcf6e623c74e757971009b45d9495d17f95e87388809` |
| Quality prediction seal | `baed791acffbaa44171525cb51810f808db691615eebbc83b99890a75d3229cd` |
| Independent numeric reconciliation | `731cbe90e26c3d3442e349a2e37882921fe44862f81413f141a6311574bf2f7e` |

The [publication manifest](quality240_20261014/publication-manifest.json) records
the original-to-public transformation and package hashes. The
[operational result](MODEL2000_VERIFIED_OPERATIONAL_20261013.md),
[paired quality result](QUALITY240_RESULTS_20261014.md) and
[union helper contract](VERIFIED_SOURCE_UNION_20261013.md) retain their distinct
questions and limitations. Structural volume above 2,000 does not certify
general-purpose accuracy, lower cost or production readiness.
