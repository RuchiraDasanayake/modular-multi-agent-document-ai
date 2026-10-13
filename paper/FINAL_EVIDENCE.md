# Final Evidence

Frozen on 2026-10-08 for `paper/ieee/main.tex`. Every number in the paper comes from the runs and commands below.
This file supersedes `paper/evidence_table.md` and `paper/PAPER_LOG.md`, which describe earlier, unpaired runs.

**Verification note, 13 October 2026:** the eight named October raw run bundles
were not found in the completed local audit. The tables below are preserved
historical records, not independently regenerated results. Aggregate arithmetic
is internally consistent, but paired intervals, timings and routing cannot be
verified without the original artifacts. The unchanged scorer also accepts some
incorrect or incomplete dates through its general fuzzy-text rule. See the
[provenance and scorer audit](../docs/OCTOBER_EVIDENCE_PROVENANCE_AUDIT_20261013.md).
This annotation does not change historical scores or establish their strict-date accuracy.

## What was compared

| Condition | Policy store | Routing |
| --- | --- | --- |
| `static` | `configs/policy_store_baseline.json` (`default` only) | router off |
| `adaptive_safe` | `configs/policy_store_research.json` (16 policies) | AHMN direct advisor (Thompson sampling) and the `adaptive_safe` gate |

Both conditions share `configs/idpo_research_config.json`, the images, PaddleOCR 2.9.1 (CPU), `qwen3.5:9b` through
Ollama 0.35.1 (temperature 0, top_p 0.8, top_k 20, num_ctx 8192, reasoning off, JSON schema), validation, recovery and
the scorer. Rollback guard in the final runs: L = 60 s, F = 0.5, rho = 0.25, delta_v = 0.10, delta_q = 0.08, W = 10,
m = 5. The first runs used absolute limits only (2.5 s p95 latency, 0.25 validation failure rate). Platform and setup:
`docs/REPRODUCING_RESULTS.md`.

## Run folders

The folders live under `<IDPO_DATA_DIR>/runs/benchmarks/` and are not part of the repository. Rescoring needs them,
together with the run directories their `paper_evidence.json` points to.

| Pack | Pack file | Final run (relative guard) | First run (absolute guard) |
| --- | --- | --- | --- |
| CORD-dev | `datasets/cord_pack_50.json` | `benchmark_1791441991` | `benchmark_1791272981` |
| CORD-holdout | `datasets/cord_holdout_50.json` | `benchmark_1791274931` | `benchmark_1791272484` |
| FUNSD-20 | `datasets/funsd_pack_20.json` | `benchmark_1791274020` | `benchmark_1791271549` |
| HARD-13 | `datasets/hard_docs_13.json` | `benchmark_1791274329` | `benchmark_1791271853` |

## Regenerating the numbers

```powershell
$b = "..\idpo-data\runs\benchmarks"
function ev($id) { "$b\benchmark_$id\paper_evidence.json" }

# Table III and the paired differences (final runs); use the first-run IDs for Section VI-D
.venv\Scripts\python scripts\aggregate_benchmark_evidence.py --rescore `
  "CORD-dev=$(ev 1791441991)" "CORD-holdout=$(ev 1791274931)" `
  "CORD-100=$(ev 1791441991),$(ev 1791274931)" "FUNSD-20=$(ev 1791274020)" "HARD-13=$(ev 1791274329)"

# Error analysis and reward vs accuracy (Sections VI-E and VI-F)
.venv\Scripts\python scripts\analyze_benchmark_errors.py `
  "CORD-100=$(ev 1791441991),$(ev 1791274931)" "FUNSD-20=$(ev 1791274020)" "HARD-13=$(ev 1791274329)"

# Simulation (Section VI-G, Table V)
.venv\Scripts\python -m ahmn_core.experiments.run_experiments
```

## Results of the final runs

Micro precision, recall and F1 over labelled fields; mean document F1; perfect documents; validation pass rate
(documents with no validation issue); mean latency per document.

| Pack | Condition | P | R | F1 | Doc F1 | Perfect | Val. pass | Latency (s) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CORD-dev | static | 0.916 | 0.881 | 0.898 | 0.896 | 32/50 | 0.88 | 8.6 |
| CORD-dev | adaptive | 0.906 | 0.900 | 0.903 | 0.897 | 30/50 | 0.88 | 13.8 |
| CORD-holdout | static | 0.899 | 0.844 | 0.871 | 0.876 | 27/50 | 0.78 | 9.3 |
| CORD-holdout | adaptive | 0.892 | 0.828 | 0.859 | 0.852 | 26/50 | 0.74 | 11.9 |
| CORD-100 | static | 0.907 | 0.862 | 0.884 | 0.886 | 59/100 | 0.83 | 9.0 |
| CORD-100 | adaptive | 0.899 | 0.862 | 0.880 | 0.875 | 56/100 | 0.81 | 12.9 |
| FUNSD-20 | static | 0.719 | 0.872 | 0.788 | 0.768 | 6/20 | 0.65 | 13.5 |
| FUNSD-20 | adaptive | 0.719 | 0.872 | 0.788 | 0.768 | 6/20 | 0.60 | 14.0 |
| HARD-13 | static | 0.980 | 0.941 | 0.960 | 0.961 | 10/13 | 0.92 | 13.0 |
| HARD-13 | adaptive | 0.980 | 0.941 | 0.960 | 0.961 | 10/13 | 0.92 | 10.9 |

Paired differences, adaptive minus static, with 95% percentile bootstrap intervals (10,000 resamples, seed 17).

| Pack | Doc F1 difference [95% CI] | Better / worse / tied | Latency difference, s [95% CI] |
| --- | --- | --- | --- |
| CORD-dev | +0.0012 [-0.0281, +0.0305] | 7 / 6 / 37 | +5.20 [+3.69, +6.63] |
| CORD-holdout | -0.0232 [-0.0680, +0.0030] | 1 / 4 / 45 | +2.61 [+1.16, +4.12] |
| CORD-100 | -0.0110 [-0.0383, +0.0106] | 8 / 10 / 82 | +3.91 [+2.84, +4.95] |
| FUNSD-20 | 0 | 0 / 0 / 20 | +0.54 [-1.38, +2.22] |
| HARD-13 | 0 | 0 / 0 / 13 | -2.09 [-6.99, +0.81] |

No accuracy difference is significant. Adaptive routing is significantly slower on receipts.

## Routing in the adaptive condition

| Pack | Guard | Specialist recommended | Specialist ran | `default` | Other | Rollbacks |
| --- | --- | --- | --- | --- | --- | --- |
| CORD-dev | absolute | 42 | 6 | 26 | 18 (6 each: `noisy_ocr_rescue`, `noisy_ocr_precision_local`, `scanned_text`) | 8, latency |
| CORD-dev | relative | 35 | 35 | 15 | 0 | 0 |
| CORD-holdout | absolute | 10 | 5 | 40 | 5 (`noisy_ocr_rescue`) | 2, latency |
| CORD-holdout | relative | 29 | 17 | 21 | 12 (`noisy_ocr_rescue`) | 1, validation (from `cord_holdout_0067`) |
| FUNSD-20 | absolute | 12 | 6 | 8 | 6 (5 `noisy_ocr_rescue`, 1 `noisy_ocr_precision_local`) | 3, latency |
| FUNSD-20 | relative | 13 | 6 | 7 | 7 (`noisy_ocr_rescue`) | 2, validation |
| HARD-13 | absolute | 3 | 3 | 4 | 6 | 0 |
| HARD-13 | relative | 2 | 2 | 8 | 3 | 0 |

`semantic_doc_type` was `unknown` for every document, because routing runs before OCR. Specialist eligibility
therefore came from the vendor cluster, which is the case-ID prefix of the file name.

## First runs (absolute guard)

| Pack | Static P / R / F1 / Doc F1, perfect | Adaptive P / R / F1 / Doc F1, perfect | Doc F1 difference [95% CI], B/W/T | Latency difference, s [95% CI] |
| --- | --- | --- | --- | --- |
| CORD-dev | 0.916 / 0.881 / 0.898 / 0.896, 32/50 | 0.910 / 0.881 / 0.895 / 0.895, 31/50 | -0.0011 [-0.0110, +0.0098], 1/2/47 | +0.85 [-0.19, +2.04] |
| CORD-holdout | 0.899 / 0.844 / 0.871 / 0.876, 27/50 | 0.888 / 0.839 / 0.863 / 0.856, 26/50 | -0.0200 [-0.0600, 0.0000], 0/1/49 | +1.15 [+0.38, +2.11] |
| CORD-100 | 0.907 / 0.862 / 0.884 / 0.886, 59/100 | 0.898 / 0.859 / 0.878 / 0.875, 57/100 | -0.0105 [-0.0337, +0.0038], 1/3/96 | +1.00 [+0.34, +1.76] |
| FUNSD-20 | 0.719 / 0.872 / 0.788 / 0.768, 6/20 | identical | 0, 0/0/20 | +0.07 [-1.66, +1.68] |
| HARD-13 | 0.980 / 0.941 / 0.960 / 0.961, 10/13 | 0.979 / 0.922 / 0.949 / 0.935, 9/13 | -0.0256 [-0.0769, 0.0000], 0/1/12 | -0.14 [-2.91, +3.13] |

Static accuracy was identical in both rounds on every pack. Mean latency is 9-14 s per document, so the 2.5 s limit
blocked every non-default policy after five observations.

## Scorer correction

The original scorer compared dates as strings and read a dot as a thousands separator only when it occurred once.
Validation rewrites some dates in ISO form, so seven correct FUNSD dates were scored as errors, and one CORD subtotal
written `2.000.000` did not match `2,000,000`. `scripts/run_idpo_benchmark.py` now treats repeated dot groups of three
digits as thousands separators and adds a branch for date fields that name the same complete calendar date.
The general similarity threshold of 0.75 is still evaluated before that branch; it can accept incomplete or wrong
dates. The earlier statement that partial dates never match was incorrect. Tests: `test_case_metrics_reads_repeated_dot_groups_as_thousands_separators`,
`test_case_metrics_matches_the_same_date_written_differently` and
`test_case_metrics_does_not_match_partial_or_different_dates` in `idpo/tests/test_research_features.py`.

| Run | Old scorer | Current scorer | Results changed |
| --- | --- | --- | --- |
| FUNSD-20, both rounds | F1 0.654, doc F1 0.635, 5/20 perfect, tied | F1 0.788, doc F1 0.768, 6/20 perfect, tied | 14 (7 documents x 2 conditions) |
| CORD-holdout, final | -0.0182 [-0.0651, +0.0127], 2/4/44 | -0.0232 [-0.0680, +0.0030], 1/4/45 | 1 (a static result) |
| CORD-100, final | -0.0085 [-0.0361, +0.0137], 9/10/81 | -0.0110 [-0.0383, +0.0106], 8/10/82 | 1 |
| CORD-holdout, first | -0.0200 [-0.0600, 0.0000], 0/1/49 | unchanged | 2 (one receipt, both conditions) |
| CORD-dev and HARD-13, both rounds | | unchanged | 0 |

No paired comparison changed sign or significance. In the final holdout run the correction helped the static condition,
so it slightly widened adaptive's deficit.

## Error analysis (final runs)

CORD-100, labelled values per field (correct / wrong / missed of labelled; values returned for unlabelled fields):

| Field | Labelled | Static | Adaptive |
| --- | --- | --- | --- |
| total | 98 | 92 / 5 / 1; 2 | 90 / 6 / 2; 2 |
| subtotal | 67 | 58 / 4 / 5; 2 | 57 / 4 / 6; 7 |
| tax | 47 | 35 / 8 / 4; 0 | 35 / 5 / 7; 0 |
| cash | 64 | 58 / 5 / 1; 0 | 57 / 5 / 2; 1 |
| change | 64 | 50 / 4 / 10; 0 | 54 / 3 / 7; 0 |
| all | 340 | 293 / 26 / 21; 4 | 293 / 23 / 24; 10 |

Seven of the 21 static omissions are change amounts of zero. Recurring causes of wrong values: OCR digit errors
(59,500 read as 595009), values taken from a neighbouring line, and receipts that print an exact and a rounded total.

FUNSD-20 (identical in both conditions): date 12 / 1 / 0 of 13, recipient 13 / 1 / 3 of 17, sender 16 / 1 / 0 of 17,
and 13 values for unlabelled fields (7 dates, 3 recipients, 3 senders).

HARD-13 (identical in both conditions): 48 of 51 correct. The faded receipt photograph's cash amount was read as `9`
for `6,000.00`, and `cord_validation_0003` (tax `0`) and `cord_validation_0042` (change `0`) were omitted.

Label-free reward vs exact document F1 (Pearson r): CORD-100 adaptive 0.07, static -0.01; FUNSD-20 0.74; HARD-13 0.84.
On CORD-100 the adaptive reward counted 94 of 100 documents as successes (reward >= 0.5); 42 of them had document F1
below 1 and 34 had a wrong or missing labelled value.

## Simulation (RABI and DAAF)

Cumulative regret, mean +/- standard deviation over 30 seeds (`ahmn_core/output/experiment_results.json`, regenerated
by the command above and not tracked). Each seed fixes both the NumPy and the Python random generators, and two full
runs produced identical results files.

| Method | Stationary (1000) | Cold start (1500) | Concept drift (1500) | Combined (2000) |
| --- | --- | --- | --- | --- |
| Random | 188.7 +/- 3.8 | 267.1 +/- 5.0 | 294.5 +/- 7.0 | 340.8 +/- 4.5 |
| epsilon-greedy (decaying) | 61.1 +/- 3.1 | 67.9 +/- 10.9 | 150.1 +/- 4.7 | 60.7 +/- 13.8 |
| UCB1 | 134.8 +/- 1.0 | 211.2 +/- 0.8 | 129.6 +/- 1.9 | 232.5 +/- 1.6 |
| TS | 43.2 +/- 2.1 | 85.9 +/- 3.5 | 107.7 +/- 4.7 | 67.2 +/- 1.9 |
| TS + RABI | 43.2 +/- 2.1 | 58.4 +/- 3.5 | 107.7 +/- 4.7 | 63.6 +/- 3.5 |
| TS + DAAF | 44.1 +/- 2.1 | 87.0 +/- 3.9 | 74.6 +/- 5.6 | 68.0 +/- 2.1 |
| TS + RABI + DAAF | 44.1 +/- 2.1 | 59.0 +/- 2.8 | 74.6 +/- 5.6 | 65.1 +/- 3.5 |

RABI lowers cold-start regret by 32% against TS and DAAF lowers drift regret by 31%; the full system lowers combined
regret by 3%. Where RABI has nothing to transfer (stationary and drift) its runs are identical to TS, and DAAF raises
regret by 1-2% in the scenarios without drift. Decaying epsilon-greedy has lower regret than TS in the cold-start and
combined scenarios (21% and 10%), with 3.1 and 7.2 times its standard deviation.

Ablations (TS regret is 85.9 in cold start and 107.7 under drift):

- RABI similarity threshold, vendor-embedding spread widened to 0.5: 62.6 at 0.2 and 66.8 at 0.3 (27% and 22% below
  TS), and 85.9 from 0.4 to 0.8, where no stored vendor passes the threshold and RABI reduces to TS.
- RABI temperature, unmodified cold-start scenario: 58.3-58.4 for every temperature from 0.1 to 2.0 (58.37 at the
  default 0.5). The stored vendors that pass the threshold have similarities within 0.04 of each other (0.90-0.95), so
  at temperature 0.5 any two softmax weights differ by at most 8%. An earlier version of this ablation widened the
  spread to 0.4; there at most one stored vendor passed the threshold, its weight was always 1, and the temperature
  could not change the result.
- DAAF window, unmodified drift scenario: 65.3 (10), 66.2 (20), 69.0 (30), 74.6 (50, the main setting), 80.7 (75),
  85.9 (100).

The simulator updates posteriors fractionally (alpha += r, beta += 1 - r), unlike the runtime's Bernoulli update. RABI
and DAAF are not active in the measured runtime. The previous paper draft reported 41.2% (RABI) and 23.7% (DAAF), and
an earlier version of this file used a run in which the Thompson-sampling draws were not seeded; both are replaced by
the figures above.

## Limits of this evidence

- Each adaptive configuration ran once. The runtime's sampler is unseeded and four documents run concurrently, so
  routing, and with it adaptive accuracy, varies between runs; the bootstrap intervals cover document sampling only.
- The guard limits were changed after the first runs; both rounds are reported.
- Prompts, normalisers and the specialists' context were written while inspecting CORD-dev and FUNSD-20. The receipt
  context names Indonesian tax labels common in CORD. CORD-holdout is the only clean holdout.
- Specialist eligibility relies on file-name prefixes that reveal the dataset.
