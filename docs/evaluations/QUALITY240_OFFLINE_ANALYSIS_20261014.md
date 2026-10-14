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

## Execution checkpoint, 14 October

Preparation copied all 269 exact registered modules and the five analysis modules.
The unchanged fourteen-module guard passed against the real protocol, with no
prediction contents or reference labels read and zero model calls. Independently
retained analysis manifest SHA:
`a8c712379c8c8f1ab5bea7609365f15421d3af793925466a460cb54574c2e6db`.

The prediction campaign is incomplete. At the latest inspected provider HTTP 503
stop, text had 146 sealed, 6 uncertain and 88 unstarted sources; candidate had 147
sealed, 5 uncertain and 88 unstarted sources. These are execution states, not
accuracy measurements. The consecutive provider errors were preserved without
replay. Execution remains stopped at control SHA
`d5c2f133a2d997d2dfe53da83875da35477f2a9ee13e440202bbe1062bf866ef`.
No prediction seal exists, and scoring has not run. A successful small provider
canary earlier in the session did not establish reliability for document requests.
Investigate provider availability before resuming untouched sources; retain every
original denominator and unknown-usage event.
