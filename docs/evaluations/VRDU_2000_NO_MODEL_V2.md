# VRDU 2,000-document no-model safety revision (2026-10-12)

This is a **product development run**, separate from the submitted paper, October research study, and official VRDU
benchmark. It tested backend commit `20da665ece2c9026e66fa53200a58057cd5ebcea` with local Tesseract and no model
calls. It reuses the same two-family development cohort as [v1](VRDU_2000_NO_MODEL_V1.md), so it is **not** an untouched
holdout or evidence of generalization. The code revision made an unapproved dynamic schema require human review; it did
not add a new field-discovery model or linked-row extractor.

## Execution and quality

The eight disjoint 250-PDF runs `vrdu_2000_shard_{ad_00,ad_01,reg_00,reg_01,reg_02,reg_03,reg_04,reg_05}_v2`
produced 2,000 candidate records. `product_eval.verify_execution --min-unique 2000` rehashed the actual sources and
confirmed **2,000 distinct PDF hashes**, no repeated source output and no missing candidate. All 2,000 matched the
creator-derived gold IDs when scored. The cohort and gold hashes are unchanged from v1.

| Metric | v1 no-model | v2 no-model | Interpretation |
| --- | ---: | ---: | --- |
| Strict schema F1 | 4.33% | **4.33%** | Field proposals remain poor. |
| Strict pre-review accepted-value F1 | 0.95% | **0%** | v2 abstains from automatic acceptance; this is a safety change, not an accuracy gain. |
| Wrong or spurious accepted values | 12,023 | **0** | v2 holds all unapproved proposals for review. |
| `processed` documents | 997 | **0** | No automatic release on an unapproved schema. |
| `needs_review` / `unsupported` / `failed` | 968 / 35 / 0 | **1,965 / 35 / 0** | The 35 unsupported sources remain unresolved. |
| Total-cost and review-minute coverage | 0 / 2,000 | **0 / 2,000** | No cost-per-correct-document conclusion is possible. |

The strict v2 schema counts are TP 816, FP 20,898 and FN 15,184 across 16,000 gold field slots. The pre-review value
counts are TP 0, FP 0 and FN 12,878 present gold values. Zero false acceptance is useful, but a system that releases
no result is not a useful automatic extractor. The 1,819,247.231 ms reported latency is the **sum of document
durations**, not wall-clock time. The workflow lacks priced API/compute costs, reviewer time and row-level output.

## Reproducibility

- Frozen cohort manifest SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`.
- Derived gold SHA-256: `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Local provenance record: `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\execution_provenance_v2.json`, SHA-256
  `589ae036ef66e7bc1623394e2f1a12654cd6616470a0584799f09b0b76c02714`.
- Verified execution report: `execution-report-v2.json`, SHA-256
  `4a14b99a5b1be56ff99c28c530bebb9a7de4966959445641119fa2d3b7b18ad4`.
- Concatenated candidate JSONL: `candidates-v2.jsonl`, SHA-256
  `89a1432886dd01aa7125a4b533964c4c585065e4dfafcab7072b84d130b48b07`.
- Strict quality report: `quality-report-v2.json`, SHA-256
  `38b4ac4b670d1134422a726358b4369fe5bd8a1cb1f8d1024476b7fca1e7ae65`.

The four local artifacts above live under `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7`; source PDFs and OCR output are
not committed. Re-run the documented [execution verifier](../../product_eval/README.md) and scorer on those artifacts.
The source repository is [VRDU](https://github.com/google-research-datasets/vrdu) at commit
`04a4df7ac5cc694e51c48115c03fe428f0e240cc`; the official benchmark match functions are not used in this strict
scorer.

## Decision

Keep the v2 abstention rule. Do **not** present the v2 zero false-accept count as improved extraction accuracy.
Investigate the 35 unsupported inputs, compare structured OCR/layout parsers and model-backed schema/value extraction
on development slices, and add linked rows. Promote a candidate only after another verified 2,000-distinct-source run
and a separate untouched multi-family holdout with measured review and total cost.
