# AHMN simulation state isolation

Date: 13 October 2026. Surface: `research_evidence`. Action: `keep` and correct.

## Reproduced defect

`run_single` changes vendor policy distributions at scheduled drift points.
The experiment driver reused the same scenario across seeds and methods, so
subsequent runs could begin with the previous run's final distributions.
Seeding the random generators does not reset that mutable state.

Before the fix, four focused regression cases failed: caller-state preservation,
method-order independence on a two-round scenario, and repeatability for seeds
0 and 3 through the real drift points at rounds 500 and 1000. The existing
300-round repeatability test never reached a drift event.

Each run now copies its input scenario before applying drift. The optional
embedding-service export is lazy, preserving explicit import behavior while
allowing pure NumPy simulations to run without importing model dependencies.
The algorithm and isolation suites pass: 17 tests. No scoring, policy,
reward, scenario or drift parameters were changed.

## Evidence boundary

April private simulation artifacts were found, with 840 main records across
30 seeds and a recorded 115.5-second main-plus-ablation runtime. Their results
differ from the October ledger; they are not that ledger's raw evidence.
They and the October historical files remain unchanged.

A corrected run must be a newly dated study. Freeze code, scenario parameters,
runtime, seeds 0–29 and all seven methods before execution. The existing main
matrix is 840 runs / 1,260,000 rounds; the three six-setting sensitivity sweeps
add 540 runs / 810,000 rounds. Preserve per-seed curves and summaries for all
1,380 runs, not only aggregate ablation means. Use one CPU process and report
any concurrent workload when interpreting elapsed time.

These synthetic comparisons can support an algorithm ablation under the
declared reward/embedding assumptions. They cannot demonstrate real-document
quality, repair missing October extraction outputs, or establish benefits
from RABI/DAAF in the current product, which does not invoke them.
