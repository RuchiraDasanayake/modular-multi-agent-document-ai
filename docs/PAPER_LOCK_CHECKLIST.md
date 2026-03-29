# Paper Lock Checklist

Use this checklist before writing the paper.

This checklist is product-constrained.

Do not change the system to fit the paper.
Write the paper to fit the finalized product path.

## Canonical Claim

Use one narrow claim only:

`adaptive_safe is a real runtime mode in which AHMN can change policy selection and IDPO keeps those adaptive decisions safe through fallback, rollback, and defer.`

Support this claim with evidence from:

- the current canonical UI
- the current canonical run artifacts
- the current canonical benchmark

## Canonical Runtime Path

Use only this path:

`frontend upload -> /api/runs/start -> frontend job runner -> idpo.cli process-inbox -> IDPO_DATA_DIR/runs/<run_id>`

Do not use alternate wrappers, legacy routes, or paper-only flows.

## Canonical Modes

Use only:

- `static`
- `adaptive_safe`

Do not rename them after evidence collection starts.

## Canonical UI Pages

Use these pages for screenshots, demos, and evidence review:

- `/dashboard`
- `/dashboard/idpo`
- `/dashboard/idpo/runs/<run_id>`
- `/dashboard/idpo/runs/<run_id>/docs/<doc_id>`
- `/dashboard/idpo/compare`
- `/dashboard/idpo/benchmark`

## Canonical Config

Use:

`configs/idpo_research_config.json`

## Required UI-visible Evidence

The run and document pages must visibly show:

- static baseline policy
- AHMN recommended policy
- final selected policy
- whether a policy change happened
- fallback reason
- rollback / blocked-policy state
- defer status and reason
- extraction outcome
- structured-output quality signals
- latency and cost where available

The compare and benchmark pages must visibly show:

- `static` vs `adaptive_safe`
- policy change rate
- advice acceptance / fallback behavior
- extraction quality
- structured-output quality
- latency / cost / escalation
- rollback / defer / feedback status

## Required Verification

1. Run one live `static` job from the canonical UI.
2. Run one live `adaptive_safe` job from the same UI.
3. Verify the run page shows:
   - recommended policy
   - final policy
   - policy change state
   - fallback / rollback / defer state
   - extraction and structured-output outcome
4. Verify the compare page shows:
   - `static` vs `adaptive_safe`
   - quality difference
   - runtime difference
   - safety-containment difference
5. Regenerate the benchmark artifact:

```bash
python scripts/run_idpo_benchmark.py --config configs/idpo_research_config.json
```

6. Verify the benchmark page renders:
   - overall `static` vs `adaptive_safe`
   - subgroup summaries
   - per-case drilldown
   - adaptive usage snapshot
   - policy change behavior
   - fallback / rollback / defer behavior

## Freeze Rules

After verification:

- do not change policy semantics casually
- do not change runtime labels
- do not change benchmark semantics
- do not widen the claim
- do not add paper-only branches

## Product-first Positioning

For the final submission:

- present the product as the main system
- present the paper as a narrow account of the adaptive extraction path
- keep AHMN claims modest
- let IDPO carry the stronger practical claim: safe runtime containment of adaptive policy advice
