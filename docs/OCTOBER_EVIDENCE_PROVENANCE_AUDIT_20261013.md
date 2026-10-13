# October paper evidence provenance audit

Date: 13 October 2026. Surface: `research_evidence`. Action: `keep`.

## Finding

The October results in [FINAL_EVIDENCE.md](../paper/FINAL_EVIDENCE.md)
remain historical ledger transcriptions, **not independently regenerated**.
The original scorer is available, but none of the eight named raw bundles
was found in the completed local searches. Do not describe this audit as
replication, or remove the working manuscript's provenance warning.

No inference, OCR, simulation, or reserved quality-label access occurred.
The frozen final model-run worktree was not modified. The accepted May
manuscript, October adaptive-policy experiment and current confirmed-schema
product study remain distinct.

## Recovered and missing evidence

The ledger first appears in commit `5235433c71f1ffb988818b1b56f51827bf08b793`,
authored on 11 October, and states a freeze date of 8 October. The three
aggregation, error-analysis and benchmark-scoring scripts are unchanged from
that commit after CRLF normalization. No `paper_evidence.json` is tracked
there.

All paths below are relative to `<IDPO_DATA_DIR>/runs/benchmarks/` and require
the nested `paper_evidence.json` plus the run directories it references.

| Pack | Final relative guard | First absolute guard |
|---|---|---|
| CORD-dev | `benchmark_1791441991` | `benchmark_1791272981` |
| CORD-holdout | `benchmark_1791274931` | `benchmark_1791272484` |
| FUNSD-20 | `benchmark_1791274020` | `benchmark_1791271549` |
| HARD-13 | `benchmark_1791274329` | `benchmark_1791271853` |

Exact probes at six likely local data roots found none of these bundles.
The older project data directory contains 69 April `benchmark_1777...`
evidence files. Four ZIP/TAR archives contain neither the October IDs nor
`paper_evidence.json`. Those older artifacts cannot substitute for October.
This is a bounded search, not an exhaustive whole-disk or other-author-machine
search; cancelled broad searches and uninspected RAR archives are excluded.

The four tracked pack manifests verify 133 case positions and 438 labelled
values. All referenced input paths are absent relative to the audited
checkout. CORD identifiers are subset positions, not stable source identities:
the claimed 126 unique originals requires original source-index manifests
and hashes, not a count of case IDs or filenames.

The ledger's own error totals reproduce its rounded micro scores:

| Pack / condition | TP / FP / FN | P / R / F1 |
|---|---|---|
| CORD-100 static | 293 / 30 / 47 | .907 / .862 / .884 |
| CORD-100 adaptive | 293 / 33 / 47 | .899 / .862 / .880 |
| FUNSD-20 both | 41 / 16 / 6 | .719 / .872 / .788 |
| HARD-13 both | 48 / 1 / 3 | .980 / .941 / .960 |

This is **internal arithmetic consistency only**. Per-document outcomes,
paired confidence intervals, timings, routing, reward correlation and the
guard comparison cannot be regenerated from aggregate tables.

## Reproduced limitation in the historical scorer

`_case_metrics` in [run_idpo_benchmark.py](../scripts/run_idpo_benchmark.py)
accepts all nonnumeric values, including dates, when normalized string
similarity is at least 0.75 **or** complete parsed calendar dates agree. The
similarity condition can admit wrong and incomplete dates. Each synthetic
probe below returned `(TP, FP, FN) = (1, 0, 0)` in the unchanged scorer:

| Expected date | Prediction |
|---|---|
| January 11, 1999 | January 1999 |
| January 11, 1999 | January 12, 1999 |
| 1999-01-11 | 1999-01-12 |

The historical wording “partial dates never match” is therefore incorrect.
Describe these metrics as lenient text/date matching, not strict date
accuracy. This audit does not establish how often the issue occurs in the
original predictions or whether stricter rescoring changes the paired result.
Do not silently change the historical scorer or relabel old metrics; any
corrected-date sensitivity analysis needs raw predictions and a separate
frozen scoring rule applied equally to both conditions.

## Recovery and publication gate

Obtain a read-only archive from the original October run owner containing
the eight bundles, referenced per-condition validated normalized outputs,
timing and policy records, and CORD source-index manifests/input hashes.
Before aggregation, require both conditions and all expected unique case
IDs; the original aggregator otherwise skips missing conditions. Validate
normalized files explicitly because the underlying loader can fall back to
raw structured fields. Preserve original paths and hashes when making a
separate rebased scoring copy.

Then run the ledger's existing aggregation and error-analysis commands
without new inference. Preserve document order for seeded resampling. The
paired interval measures mean document-F1 differences, not micro F1 or
variation between adaptive-router runs. The simulation table remains a
separate unrerun claim; RABI and DAAF were not active in the measured runtime.

The external verification bundle is named
`Paper2/audit/october-evidence-verification-v1`. It contains the exact path
probes, archive member inventories, code hashes, manifest counts, synthetic
probes and a reproducible read-only audit script. The working Word manuscript
and reviewer-response matrix carry these limitations. New operational volume
cannot repair this historical provenance gap or establish held-out accuracy.

Audit receipt SHA-256:
`4410035a50d7fc125d2baaf48111d52aa3d69e141c5692062776c68770ef8188`.
Detailed report SHA-256:
`7090f031aab0ba4c54df095d047e1897e10ca56eba37f968d6d617f4163ea32a`.
