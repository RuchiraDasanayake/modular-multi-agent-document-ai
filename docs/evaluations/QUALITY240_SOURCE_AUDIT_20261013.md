# Reserved quality240: source-only audit and execution design

Status: source metadata audited, 13 October 2026. No reserved document bytes,
labels, OCR or model calls accessed. Surface: `research_evidence`; action: `keep`.

`conference-evaluation-plan/candidate_quality240_sources.json` has SHA-256
`214def43738fd2bafb3102d80b4f26287e5b405140206abc767c361521e135ab`.
It contains 100 registration PDFs, 100 ad-buy PDFs and 40 reserved CORD test PNGs:
240 distinct stored hashes, zero overlap with mixed2000 or the paired dev6.
All paths exist and stat sizes agree: 142,769,086 bytes total, largest 17,240,894,
all under 20 MiB. Final freeze must rehash originals; this audit used metadata only.

The VRDU sources come from 556 remaining PDFs outside the old VRDU2000 source set.
The saved source audit checked five historical development locks; other prior
exploration cannot be reconstructed. Source disjointness does not establish
template/vendor/pretraining disjointness. This is not the official VRDU unseen
template split or the full CORD test benchmark. CORD entries lack the VRDU-specific
`selection_rank` field. The existing active v2 pointer binds the operational2000
plan, not a ready-to-run quality240 campaign.

## Frozen paired design

Use the exact three family schema bytes and final product/runtime/model profile
selected before reserved-label access. Compare fresh RapidOCR + strict + bounded
text with the same path plus the selected bounded visual profile. Preserve all
240 originals and all 480 source-arm outcomes. The visual profile is adaptive;
report its actual visual/text route counts. Different prompts/response contracts
make this a deployed-path comparison, not an isolated vision-model experiment.

Freeze a family-interleaved source schedule and counterbalance first-arm order
within each family. Keep pairs adjacent; use one spawned process by default and
checkpoint every 25 originals/50 slots. Max four requests per source-arm yields
1,920 total and 960 per arm; 480 is the minimum only if every source reaches both
model paths. The current planned candidate is `bounded_visual_selective_v2`,
derived from dev6: visual-eligible source and either confirmed row groups or more
than one strict text segment. Its implementation must be validated before freeze.
At 8,192 requested completion tokens, the maximum is 15,728,640 plus
input tokens. This is not a monetary cap. Worst-case serial request time alone
at 180 seconds is 96 hours; use current development measurements for forecasts.

Reuse `final_model_gate._run_source`, `summary` and `_verify_existing` through
separate arm output directories and ledgers, preserving original product IDs.
A thin coordinator owns the frozen paired schedule, shared global budget/stop
state and checkpoints. Each arm's durable cap is 960, so their sum cannot exceed
1,920; the coordinator must check both ledgers before any further dispatch.
Resume only unstarted source-arm slots. A started slot whose outcome is uncertain
remains terminal for automatic dispatch, even when its paired arm can finish.
Never replay uncertain paid calls or discard failed/unattempted pair members.

Do not copy the full final runner, loosen its exact mixed2000 guard, change
production extraction behavior or reuse old OCR outputs. A separate quality
freeze binds the exact 240 inventory, schemas, clean code/runtime and source hashes.
Stop both arms on provider/integrity/uncertain outcomes. Seal prediction artifacts
before a separate offline scoring command can load references. Test crash/resume,
source drift, cross-arm stopping, budgets and failure denominators with fake models.

## Metrics and the creator-matcher caveat

Preserve strict mapped scalar and one-to-one whole-row recall as primary metrics,
with ordinal cells as historical diagnostics. Keep partial-label extras and
incompatible OCR evidence coordinates unassessed. Report source coverage, valid
strict output, non-null proposals, conflicts, source-grounded values, review
burden, tokens and latency separately. A full-page request is not visual correctness.
Use paired document-level, family-stratified uncertainty; cells are not independent
samples. No statistical interval establishes template generalization here.

The pinned creator VRDU `get_matching_result_per_doc` scans all predictions again
for every reference and later checks extra predictions by value membership.
Two synthetic cases independently reproduced these assignment defects:

| Case | Pinned function TP / FN / FP | One-to-one expectation |
| --- | ---: | ---: |
| Two equal reference rows, one prediction | 2 / 0 / 0 | 1 / 1 / 0 |
| One reference row, two equal predictions | 1 / 0 / 0 | 1 / 0 / 1 |

Only two extracted pure functions with synthetic exact matching were executed;
no creator entities or reserved labels were read. Code SHA-256:
`9a598cb28dc7c48a57fc0348dc3a3eafd1596a74f85c40f1420eae3f0f0fc7f8`.
The [creator evaluator](https://raw.githubusercontent.com/google-research/google-research/master/vrdu/benchmark_utils.py)
therefore must not silently replace the duplicate-preserving project metric.
Its scalar occurrence alternatives are a separate valid semantic distinction:
one entity can match any acceptable occurrence, unlike the historical ordered
list representation. Any new lane needs a named, pinned adapter and independent
tests; preserve original scores and do not relabel toward predictions.

## Minimum defensible conference plan

1. Paired quality240 on the frozen text/selected candidate, with per-family strict
   results, complete failure denominators, uncertainty, usage and label limitations.
2. Genuine postimplementation operational2000 on distinct originals, reporting
   real attempts, valid complete values and terminal outcomes independently.
   Failed/no-call outcomes do not become successful model extractions.
3. Clearly small development input-guard ablation; offline raw-proposal versus
   evidence-filtered assessment from the same sealed calls, reporting recall loss
   and review burden alongside quality. No additional model calls are needed.
4. Format-faithfulness and queue/review/export tests as engineering evidence.
   Three form/receipt families do not establish arbitrary-format accuracy.
5. Narrow unmeasured scientific claims. The broader protocol's memory-learning,
   policy-routing, schema-discovery, local-vs-cloud and timed HITL comparisons
   remain unrun. Existing architecture is not measured benefit. Independent
   source-only visual adjudication is still unavailable.

The six-page conference paper should distinguish original-paper results,
development pilots and final sealed experiments. This plan cannot guarantee
acceptance, correct extraction on arbitrary documents or a completion date.

External source-only audit/script/expanded plan:
`I:/DocAI-Benchmarks/conference-evaluation-plan/quality240-source-audit-20261013-v1`.
Metadata receipt SHA-256:
`29465a7b81cf9adcdf86d5d9ee6ceb33478d268edf56d432defd7f78e5bd678d`.
