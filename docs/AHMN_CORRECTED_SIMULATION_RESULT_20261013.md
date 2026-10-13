# Corrected AHMN simulation result — 13 October 2026

Surface: `research_evidence`. Primary action: `keep`.

## Study identity

This is a **new corrected numerical experiment**, not reproduction of the
October extraction study or a replacement of its missing raw evidence.
The [scenario-isolation fix](AHMN_SIMULATION_ISOLATION_20261013.md) prevents
one seed or method from inheriting another run's final drift state.
Historical April artifacts and the October ledger were preserved unchanged.

The frozen backend commit is
`b967efe73c60a219d2b87dee8ee0a5d872ae8dbc`.
Python 3.13.8 and NumPy 2.4.6 ran all seven methods, seeds 0–29 and four
existing synthetic scenarios: stationary (1,000 rounds), cold start (1,500),
concept drift (1,500), and combined (2,000). Three six-setting sensitivity
sweeps each used 30 seeds and 1,500 rounds. Total: **1,380 runs and 2,070,000
synthetic rounds**, with raw curves retained for every run.

One process ran at below-normal priority with numerical-library threads
limited to one. Completion took 190.10 seconds; peak RSS sampled at run
boundaries was 189,739,008 bytes. The operational product evaluation was
active concurrently, so this is not an isolated latency benchmark. There
were **zero document-model calls, zero OCR runs and no reserved-label access**.

## Executed mechanism details

Each vendor has five policy arms, initially Beta(1,1). The simulator adds
reward and one-minus-reward as fractional success/failure counts. RABI
initializes a newly observed vendor from qualifying observed neighbors using
cosine similarity at least 0.4, at least five samples per neighbor arm,
softmax temperature 0.5, and a cap of 10 on transferred excess counts.
Although `RABIInitializer` stores `k=5`, its executed `initialize_prior`
method neither sorts nor truncates the supplied neighbors to that number.
It weights **all qualifying supplied neighbors**. Do not describe the
experiment as enforced top-five retrieval. This clarification describes
the frozen code; it does not alter the completed experiment.

DAAF uses recent and older per-arm reward windows of 50, minimum sample count
10, shift thresholds 0.05/0.15 and standardized-gap thresholds 2/3. It shrinks
excess counts toward Beta(1,1), with extra halving on an abrupt classification,
before adding the current fractional reward. Decaying epsilon-greedy uses
`max(0.01, exp(-0.003 * round))`; UCB1 uses exploration coefficient 2.
The frozen sources and protocol retain the exact update equations and every
scenario's reward means, vendor weights, arrival times and embeddings.

## Main comparison

Cumulative pseudo-regret, mean ± population SD over 30 seeds; lower is better.
Regret uses the difference between the highest configured reward mean and
the chosen policy's configured mean. The console label `Final F1` denotes a
synthetic reward, not measured document extraction F1.

| Method | Stationary | Cold start | Concept drift | Combined |
|---|---:|---:|---:|---:|
| Random | 188.7 ± 3.8 | 267.1 ± 5.0 | 273.2 ± 4.4 | 344.7 ± 4.6 |
| Decaying epsilon-greedy | 61.1 ± 3.1 | 67.9 ± 10.9 | 229.4 ± 4.3 | 120.2 ± 17.8 |
| UCB1 | 134.8 ± 1.0 | 211.2 ± 0.8 | 111.7 ± 2.1 | 239.0 ± 1.5 |
| Thompson sampling | 43.2 ± 2.1 | 85.9 ± 3.5 | 147.9 ± 17.6 | 103.5 ± 4.2 |
| TS + RABI | 43.2 ± 2.1 | 58.4 ± 3.5 | 147.9 ± 17.6 | 86.1 ± 3.8 |
| TS + DAAF | 44.1 ± 2.1 | 87.0 ± 3.9 | 90.0 ± 12.3 | 88.4 ± 4.2 |
| TS + RABI + DAAF | 44.1 ± 2.1 | 59.0 ± 2.8 | 90.0 ± 12.3 | 71.8 ± 3.4 |

Within these constructed scenarios, RABI reduces mean cold-start regret by
32.0% relative to TS; DAAF reduces drift regret by 39.1%; their combination
reduces combined-scenario regret by 30.6%. These are comparisons with the
TS baseline, not universal gains or extraction-accuracy improvements.

Paired seed-level mean regret differences against TS have the following
descriptive 95% percentile bootstrap intervals (10,000 resamples, RNG seed
17). Negative values favor the variant. Intervals are unadjusted for multiple
comparisons and are not confirmatory significance claims.

| Variant / scenario | Mean difference | 95% interval |
|---|---:|---:|
| RABI / cold start | -27.53 | [-28.93, -26.10] |
| DAAF / concept drift | -57.88 | [-65.23, -50.30] |
| Full / combined | -31.65 | [-33.22, -30.12] |
| DAAF / stationary | +0.88 | [+0.38, +1.36] |
| DAAF / cold start | +1.06 | [-0.10, +2.20] |

The tradeoffs matter: DAAF raises stationary regret, RABI has no effect when
there is no eligible transfer, and epsilon-greedy beats plain TS in cold
start. UCB1 also beats plain TS under drift. The full table retains every
baseline. Stationary and cold-start means agree with the historical ledger
at its displayed precision; drift and combined results change materially
after state isolation. Do not combine old and corrected cells in one table.

## Sensitivity results

Each setting uses the same 30-seed rule. The threshold sweep widens embedding
spread to 0.5; it is a modified scenario, not a second baseline for the
unmodified cold-start table.

| Sweep | Setting → mean regret |
|---|---|
| RABI temperature | 0.1 → 58.337; 0.3 → 58.387; 0.5 → 58.375; 0.7 → 58.373; 1.0 → 58.373; 2.0 → 58.368 |
| DAAF window | 10 → 83.525; 20 → 91.046; 30 → 92.607; 50 → 90.036; 75 → 91.400; 100 → 94.585 |
| RABI similarity threshold, wider spread | 0.2 → 62.628; 0.3 → 66.767; 0.4/0.5/0.6/0.8 → 85.905 |

Temperature has little effect in the chosen near-similarity setting. At
thresholds of 0.4 and above, the wider-spread RABI run reduces to the TS
baseline. The corrected window curve is not monotonic; the smallest tested
window has the lowest mean in this scenario, but the main setting remains
50. No parameter was retuned after viewing these results.

## Verification and limits

- Before the fix, four focused isolation regressions failed. After it, 17
  algorithm and isolation tests passed, including repeated seeds through
  both drift points and method-order independence.
- Offline verification checked hashes, all 1,380 unique run records, all
  46 groups with seeds 0–29, 2.07 million round positions, curve lengths,
  numeric ranges, monotonic regret, and final-regret agreement. Means, SDs
  and paired intervals were regenerated from raw records.
- This is record/statistical verification, not an independent algorithm
  implementation. The whole 1,380-run experiment was executed once, not
  repeated twice.
- Rewards, vendor similarity and change points are designed synthetic
  inputs. Rewards are Gaussian samples clipped to [0,1]. The drift scenario
  applies discrete changes at rounds 500 and 1000; the combined scenario
  applies its own discrete change at round 600. The drift source's first-change
  label “gradual” does not implement continuous gradual drift.
- Simulation uses fractional posterior updates; the historical document
  runtime uses a Bernoulli threshold. Neither the historical measured
  extraction path nor the current confirmed-schema product invokes RABI
  and DAAF. These results address algorithm behavior under declared
  assumptions, not real-document component benefit, cost or accuracy.

## Artifacts

The private bundle is
`Paper2/audit/corrected-ahmn-simulation-20261013-v1`.
It contains the pre-run protocol and all scenario parameters, code/runtime
hashes, start/completion receipts, 143,091,266-byte JSONL raw curves,
per-seed summaries, all main/sensitivity statistics and verification output.
The adjacent frozen runner and verifier preserve the execution procedure.

| Artifact | SHA-256 |
|---|---|
| `protocol.json` | `093bf2973f7b043bd196d1e178f9a406acee12871889dfb9888835fd94cae3d7` |
| `results.json` | `ce91a416ca4b05996e118c9333952ff7b89add45efa9140f0d6df2ca4766090e` |
| `all_run_curves.jsonl` | `eba6f0cc20eea224ecc899a35e2d0eefd6fca6e107d02da96ac9062522f5e34a` |
| Verifier source | `b8c2b8df7656de2e374081f3634b2ab7f3e5b18509ccc6e59199f608b3f01473` |

If retained in the camera-ready paper, identify this as a dated corrected
simulation with its own table and disclose the state-leak correction.
It can strengthen the synthetic ablation response while the missing October
document evidence and the separate product quality evaluation remain open.
