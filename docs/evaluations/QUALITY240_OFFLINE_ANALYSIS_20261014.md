# Frozen quality study analysis isolation

Classification: `research_evidence`; action: `keep`.

The current product contains changes made after the paired study was frozen.
Running its post-seal verifier directly from the current checkout correctly fails
the frozen-source guard for `strict_output.py`, `visual_output.py` and `logic.py`.
The guard must remain intact. Analysis must use the registered experiment source.

`scripts/quality240_offline_analysis.py` prepares a new external analysis directory
from all 269 registered Python source files in the frozen checkout. Each file must
match the protocol's exact byte hash before any output is created. Five analysis
and amendment-verification modules are added with their own manifest hashes; none
may replace a registered source. The loader itself is hash-bound, with LF line
endings preserved by Git. Imports are restricted to that tree and the selected
Python interpreter's dependencies. No bytecode is written into the tree.

## Required sequence

Run the loader with the configured extraction Python and `-I`:

1. `prepare`: supply `--frozen-root`, `--run`, a new external `--analysis-root`, and
   the independently retained `--protocol-sha256`. Retain the returned analysis
   manifest SHA independently. This step reads code and protocol only.
2. `preflight`: supply the same run, analysis directory and protocol pin plus
   `--analysis-sha256`. The unchanged fourteen-module frozen-source guard must
   pass. This step reads neither predictions nor references.
3. Wait for completed execution and the prediction seal. Independently hash the
   seal. Do not close an unfinished campaign just to obtain a report.
4. `verify`: additionally supply `--prediction-seal-sha256`, the exact
   `--transport-amendment-sha256`, every `--http408-resolution-sha256`, and a new
   external JSON `--output` file. This verifies sealed predictions without labels
   and emits an independently retainable verification receipt SHA.
5. `score`: supply the same pins, `--verification-receipt`,
   `--verification-sha256`, a new external output directory, `--vrdu-root` and
   `--cord-gold`. The original complete verifier runs again before reference
   access. Its durable `verified-before-labels.json` precedes reference loading.

Never place analysis outputs inside the campaign or staged source tree. Never
edit the campaign, frozen checkout or an existing analysis tree to make a check
pass. A partial preparation has no manifest and cannot be used; select a new
directory after investigating an interrupted preparation.

The seventeen focused tests cover altered source rejection, missing/extra files,
overlay protection, staged-byte and manifest tampering, import isolation, the
original frozen-source guard, and rejection before label access when the required
seal or independent verification receipt is absent or invalid.

## Manuscript mapping

Use `quality-results.json`, retaining undefined values as undefined. Multiply
recall estimates and confidence limits by 100 for percentages; the paired
difference then has units of percentage points.

| Table IV row | Node below `paired_uncertainty` |
| --- | --- |
| Registration scalar | `proposed_scalar_positive.families.registration-form` |
| Ad-buy scalar | `proposed_scalar_positive.families.ad-buy-form` |
| Receipt scalar | `proposed_scalar_positive.families.receipt` |
| Scalar macro | `proposed_scalar_positive.macro` |
| Ad-buy whole row | `proposed_annotated_rows.families.ad-buy-form` |
| Receipt whole row | `proposed_annotated_rows.families.receipt` |
| Whole-row macro | `proposed_annotated_rows.macro` |

Each node contains `text.estimate`, `candidate.estimate`, and
`candidate_minus_text.estimate` with its `percentile_95_interval`. Family nodes
also contain matched/reference counts. Report failures, undefined denominators
and estimable bootstrap replicates alongside these derived recall metrics.
The scorer's request-duration sums are not campaign wall time. Preregistered
latency percentiles and wall-time reporting still require the sealed timing
records and must not be inferred from these sums. Unknown usage is not zero cost.

After scoring, `scripts/quality240_timing_usage.py` requires the independently
retained prediction-seal, verification-receipt and scoring-receipt hashes. It
checks those bindings, all sealed artifact hashes and the scored usage totals
before writing a new external report. It opens no reference files and makes no
model calls. Twenty-three synthetic tests cover timing calculations, failure and
missing-value retention, receipt tampering and denominator checks.

Request p50/p95 use linear interpolation over measured request latencies,
including failed and uncertain attempts. Every summary includes its measured
count and missing observations. Source duration includes local processing and
provider work. The recorded campaign span runs from the original start event to
the last source closure, including provider and operator pauses and excluding
later sealing and analysis. Exact process-active campaign duration was not
recorded. All 240 sources per arm remain in the source denominator.

## Completed analysis, 14 October

Preparation copied all 269 exact registered modules and the five analysis modules.
The unchanged fourteen-module guard passed against the real protocol, with no
prediction contents or reference labels read and zero model calls. Independently
retained analysis manifest SHA:
`a8c712379c8c8f1ab5bea7609365f15421d3af793925466a460cb54574c2e6db`.

The campaign completed on 13–14 October UTC with all 480 source-arm slots
terminal and no unstarted slots. The prediction seal was independently verified
before reference access and isolated offline scoring. An independent count-based
recalculation passed 231 checks and reproduced every primary family/macro
bootstrap interval endpoint exactly. See the
[actual result report](QUALITY240_RESULTS_20261014.md) and
[source-union report](VERIFIED_SOURCE_UNION_RESULT_20261014.md).

| Evidence | SHA-256 |
| --- | --- |
| Prediction seal | `baed791acffbaa44171525cb51810f808db691615eebbc83b99890a75d3229cd` |
| Independent pre-reference verification | `3d7cfc983a5cf9d04eff67e21b3bc26c3b2bfe9682f53ae0544bddf82010347e` |
| Scored quality results | `61a3ba744005d607dcb7be931988bd8058395af2749bfb90ff514ddb96b75f45` |
| Scoring receipt | `ac97bdd7dfc29b9e612ffcf6e623c74e757971009b45d9495d17f95e87388809` |
| Timing/usage report | `d9531b68ff439d104d1908919502d9f94c1a7e4aa611b8db6e4e55562b58b3d3` |
| Independent numeric reconciliation | `731cbe90e26c3d3442e349a2e37882921fe44862f81413f141a6311574bf2f7e` |

Both macro paired-difference intervals include zero. Receipt whole-row recall
improves while ad-buy rows decline; candidate known token volume is higher.
The primary scalar denominator retains all 54 historical ordered-list/schema
mismatches per arm. Provider errors, 14 uncertain sources per arm and unknown
usage remain visible. These results support no universal accuracy, automatic
schema-quality or lower-USD-cost claim, and no frozen outcome was replayed.
