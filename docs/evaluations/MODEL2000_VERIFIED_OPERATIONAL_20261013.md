# Verified 2,000-original operational extraction results

Classification: `research_evidence`; action: `keep`.

Status: terminal accounting and independent offline verification complete;
**the all-source operational gate did not pass**. This records the campaign
frozen on 13 October 2026, with its final report packaged on 14 October.
The separate [paired quality evaluation](QUALITY240_PREREGISTRATION_20261013.md)
remains pending. The product remains a research prototype with unvalidated
general-purpose accuracy, cost per correct document and production readiness.

## Method and denominator

The frozen backend is `0cce810734c863f01f7e6956c792ee34e64da3c7`.
The inventory contains 2,000 distinct original byte hashes: 897 registration
PDFs, 305 ad-buy PDFs and 798 CORD training receipt images. Extraction used
three fixed, confirmed family schemas, fresh product intake and RapidOCR when
required. No reference answers were provided to the extractor. Schema discovery
and independent value correctness are not measured by this operational study.

The configured provider alias was `innobot-luna-6` through ICORE. Profiles were
`strict_confirmed_values_v1`, `bounded_text_segments_v1` and
`bounded_visual_selective_v2`, with 8,192 maximum output tokens, 180-second
requests, at most four requests per original, four workers and a global cap of
2,500 attempts. SDK retries were disabled. Uncertain attempts were retained;
resumption dispatched only untouched sources. The
[execution admission and first checkpoint](MODEL2000_SELECTIVE_V2_EXECUTION_20261013.md)
remain a separate historical record.

All 2,000 selected originals remain in every source-level denominator below.
The final report records 2,000 outcome/prediction receipts and no unstarted
originals. The offline verifier checked the final seal, original byte hashes,
request/reply hashes, product receipts and operational counters without labels.
This documentation independently reconciles its pinned report and family
totals; it does not repeat extraction or open source or prediction contents.

## Outcome by document family

| Family | Selected | Request begun | Strict/full coverage | Valid non-null | Pre-model rejection | Provider uncertainty | Invalid values |
|---|---:|---:|---:|---:|---:|---:|---:|
| Registration | 897 | 897 | 893 | 892 | 0 | 4 | 0 |
| Ad-buy | 305 | 301 | 287 | 287 | 4 | 9 | 5 |
| Receipt | 798 | 789 | 750 | 750 | 9 | 13 | 26 |
| **Total** | **2,000** | **1,987** | **1,930** | **1,929** | **13** | **26** | **31** |

Strict-parsed output with complete recorded source coverage was obtained for
**1,930/2,000 originals (96.50%)**: 1,072 with complete extracted-text coverage
and 858 with complete page-image coverage. Of these, 1,929 contain at least one
non-null proposed value and one registration output is valid all-null.
All 1,930 require human review; 19 ad-buy outputs also carry scalar conflicts.

These are coverage and response-validity results, not accuracy. A non-null
proposal need not be correct or grounded. Valid all-null output counts toward
the operational gate; non-null coverage is a separate measure. The gate failed
because valid complete model extraction does not cover all 2,000 originals and
uncertain outcomes remain. The campaign alone also does not establish 2,000
distinct originals with model requests: the recorded count is 1,987.

### Disjoint unsuccessful outcomes

| Outcome | Originals | Share of all selected | Recorded reasons |
|---|---:|---:|---|
| Rejected before a model request | 13 | 0.65% | Six raster-size bounds; seven encoded-page-size bounds |
| Provider uncertainty | 26 | 1.30% | Nine text value-provider, 16 visual request-provider and one long-document segment-provider error |
| Invalid model values | 31 | 1.55% | Five strict text-value responses; 26 visual-value responses |

These categories sum to 70 and do not overlap. The recorded provider error
category is `provider_server` for 26 uncertain attempts. The report does not
distinguish every invalid-values failure into JSON syntax, schema and other
validation subtypes, so the 31 sources must not all be called malformed JSON.

## Attempts, states and review

- Ledger states: **1,974 sealed, 26 uncertain, zero unstarted**. Sealed includes
  44 unsuccessful originals: 13 pre-model rejections and 31 invalid-value
  outcomes. It is a terminal accounting state, not a correctness judgment.
- There are **2,053 begun-request markers and 2,053 known SDK attempts** across
  1,987 originals. The 26 uncertain attempts are included in that total.
  Markers and SDK counters do not establish request delivery or billing.
- There are **1,996 strict-valid reply attempts**: 1,993 requests on the 1,930
  complete originals and three valid partial requests on ultimately uncertain
  originals. The latter do not supply complete-source coverage.
- Requests per original: zero for 13 originals, one for 1,941, two for 30,
  three for 12 and four for four. Multiple requests may cover text segments or
  image groups; this distribution is not a retry count.
- Finish reasons: 2,023 `stop`, four `length`, 26 unknown. No refusal was
  recorded. SDK attempt counts and recorded latency have no missing entries;
  token usage is unknown for 26 attempts.
- `needs_review` totals 1,935 because five invalid text-value outcomes retain
  that status. It cannot be used as a count of valid extractions. Similarly,
  the 71 all-null outcomes include 70 unsuccessful sources and one valid
  complete all-null output.
- Machine-accepted counters are 4,499 non-null fields and 5,114 linked cells.
  These are machine grounding/status results, not human-reviewed releases or
  independently correct values. No human-release accuracy or review time was
  measured in this campaign.

## Known usage and timing

| Family | SDK attempts | Known input tokens | Known output tokens | Attempts missing usage | Summed provider seconds |
|---|---:|---:|---:|---:|---:|
| Registration | 897 | 1,668,848 | 383,037 | 4 | 5,491.625 |
| Ad-buy | 367 | 4,641,135 | 1,057,421 | 9 | 9,757.617 |
| Receipt | 789 | 2,310,247 | 795,555 | 13 | 12,986.333 |
| **Total** | **2,053** | **8,620,230** | **2,236,013** | **26** | **28,235.575** |

Known total usage is **10,856,243 tokens** from 2,027 attempts with usage.
Missing usage is not treated as zero. The mutable model alias does not identify
immutable vendor weights or verified prices. Total billed usage and USD cost
are unavailable; this result cannot establish cost per correct document.

Summed provider-call latency is 28,235.575 seconds. Summed per-document duration
is 58,691.190 seconds. Both aggregate individual records under a four-worker
profile on a shared host. Neither is campaign wall time or an end-to-end
throughput measurement.

## Frozen backend versus release `c24eda8`

A source audit compared the frozen backend with release
`c24eda8fe25ea773f9842b18b8f86b26a6d80759`. The paired coordinator
`1d1d55a501b007f6d815f4880517c3ec980b1607` has the same `idpo` and `ahmn_core`
trees as the frozen backend, but its separate quality results are still pending.

| Changed surface | Consequence for this evidence |
|---|---|
| Shared PDF intake in `idpo/agents/intake.py` | Adds a bounded preview entry point. Full intake retains complete page enumeration and the existing paint/text logic. Preview behavior was not exercised by this frozen confirmed-schema run. |
| Image-frame guard and its workflow hook | Rejects non-single-frame or unreadable containers before OCR. Passing single-frame images proceed to the existing extraction logic; the extra header open changes timing. |
| Native Office readers and XML preflight | Adds allocation and structure bounds for DOCX, XLSX and PPTX. This PDF/PNG cohort does not validate those guards or Office extraction quality. |
| Schema-suggestion preview | Uses shared bounded intake/OCR and revised suggestion contracts. It is outside this confirmed-schema experiment. |
| Product admission, review/export, readiness and recovery | Separate product behavior changed. Direct extraction calls do not benchmark HTTP admission, human review, export correctness, authentication or recovery. |

The audit found no changes to the provider, strict/visual output contracts,
visual request preparation/routing, segmentation/merge, confirmed-schema loader,
RapidOCR adapter/worker, PDF paint/raster helpers or product dependency manifests
in this revision range. Static source continuity does not prove identical
installed runtimes, configuration, provider weights, output bytes or latency.
The product extraction path does not execute the separately simulated adaptive
memory and bandit controller.

### Post-seal image-header compatibility

After independent final verification, a separate read-only check examined the
current release's image-frame admission rule against all selected originals.
It verified the pinned protocol/report/receipt association before source access
and checked original SHA-256 values before and after each header operation.

| Family | Selected | Single-frame PNG pass | PDF outside frame guard | Header/hash errors |
|---|---:|---:|---:|---:|
| Registration | 897 | 0 | 897 | 0 |
| Ad-buy | 305 | 0 | 305 | 0 |
| Receipt | 798 | 798 | 0 | 0 |
| **Total** | **2,000** | **798** | **1,202** | **0** |

All 798 images were PNGs with one frame. All 2,000 before/after hashes matched.
The check used Python 3.13.8, Pillow 12.1.0 and the committed release guard.
PDFs were hashed without parsing; their status was
`not_changed_by_frame_guard`. The check requested no pixel decoding, OCR,
model inference or label/prediction access and retained uncertain campaign
states in its denominator.

This resolves the new image-frame admission uncertainty for this operational
cohort only. It neither reruns extraction nor upgrades a failed historical
outcome. No model-output equivalence is inferred. Quality-cohort frame
compatibility, full installed-runtime reconciliation and an end-to-end benchmark
of the newer release are not established by this check.

## Integrity pins and evidence availability

Private evidence contains original documents and model artifacts; this public
summary publishes aggregate counts and integrity pins only. It does not grant
redistribution rights or imply that all raw artifacts are publicly available.
The independently verified report binds 28,030 referenced artifact hashes and
82 separately hashed unreferenced artifacts. The latter never increase
extraction counts.

| Evidence | SHA-256 |
|---|---|
| Frozen operational protocol | `b9571b78a9be196573cd14c7ac8b4050cb741f091646eeb1c76257bfdae69eeb` |
| Final seal `seals/1791915983142407300.json` | `700e380ff440b93e485ad90e511c93b2f82e126dd8013a2a7878b346e44c97ea` |
| Independent `verification.json` | `d18822bee95558bc66b34452152868104acf4e3b2571eda82e0916d8555ec4cb` |
| Independent verification `receipt.json` | `a1f6023f66002abb37bb5b9c1b57fdf519670392b60462601c79081f133fa57f` |
| Independent `report.md` | `6336dc2897dd27f0b0fc81e93da096d05ca6de7f38a851830b4dc9e6e3ada665` |
| Reconciled publication table inputs | `2a4f2fe40ec13f1c7d06c8b4c466ec8b7fac6534ab270498fb105e530e54be07` |
| Private operational analysis | `de07be8346070a4b35509a9ee5ed8ab0c390d7d80f0ee2ac10d7597740505bd2` |
| Frozen-to-release source audit | `a5102392af2794ffafc9807ec68dbd288a213a0b9adb1a944ecdd3971d5ad9cc` |
| Post-seal frame/header report | `4cff6a36c16f3e7008019a29c2d85555696ba998da240034c8ec3402fc16dcd0` |
| Frame/header checker | `75fbe78dfabcc72a00b7e492606b4c93cbeadc89369f9a705ec594e32db1fa1c` |
| Release frame guard, raw bytes and committed blob | `e7fcd0891ea6b6ef722af5bd56439442c80192b0a4f3f12cf60530378de6d291` |

The original source hashes, profile, schemas and runtime/model receipts remain
bound to the frozen protocol. They were not changed to produce this summary.
Earlier negative development baselines and historical research summaries remain
available with their original limitations; this operational result does not
replace or validate them.

## Remaining evaluation

Complete the preregistered, source-disjoint paired quality study, independently
verify both arms before reference access, and report creator-label agreement
with its annotation limits and paired uncertainty. Its confirmed-schema metrics
will still not establish schema-discovery accuracy or universal document quality.
The [prospective source-union helper](VERIFIED_SOURCE_UNION_20261013.md) can later
account for distinct selected, attempted and complete originals across the two
studies while preserving their separate denominators and this failed gate.
No such combined result is claimed here.
