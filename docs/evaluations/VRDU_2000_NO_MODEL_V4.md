# VRDU 2,000-document v4 run with missing OCR dependency (2026-10-12)

This run evaluated the opt-in product path at commit `331b8b7ad192cef98e402f487b4cd25e1e45f541` from a clean,
detached worktree. It configured a Tesseract single initial pass and bounded quality retry, but the intended portable
Tesseract executable was absent from the gate process environment. **The configured OCR did not run successfully on
scans.** No model was configured:
schema and values came from the deterministic label/value proposal. It is a development volume and safety gate, not
an evaluation of AI schema discovery, model-backed linked rows, the frontend review workflow, or arbitrary document
types. The 1,500 registration and 500 ad-buy PDFs are the same two-family VRDU development cohort used in v1/v2;
they are not an untouched holdout and the scorer is not the official VRDU matcher.

## Verified execution

`product_eval.run_gate` ran eight disjoint 250-PDF shards, rehashed each raw PDF, checked the frozen cohort and gold
IDs, and found **2,000 distinct sources**, zero repeated outputs and zero missing candidates. All eight runs have
completion markers. The evaluated worktree was clean. The source corpus is
[Google's VRDU repository](https://github.com/google-research-datasets/vrdu) at creator commit
`04a4df7ac5cc694e51c48115c03fe428f0e240cc`.

| Metric | v2 safety baseline | v4 bounded OCR | Interpretation |
| --- | ---: | ---: | --- |
| Strict schema F1 | 4.33% | **4.33%** | No gain in field discovery. |
| Strict pre-review accepted-value F1 | 0% | **0%** | No value was released automatically. |
| Proposed linked cells / complete rows | Not scored | **0 / 0** | Gold contains 30,133 cells in 7,234 rows. |
| `needs_review` / `unsupported` / `failed` | 1,965 / 35 / 0 | **1,965 / 35 / 0** | Review or abstention for every document. |
| Sum of per-document duration | 1,819,247 ms | **1,488,499 ms** | Invalid as an OCR speed comparison: v4 lacked the executable. Neither number is wall time. |
| API, compute and reviewer cost coverage | 0 / 2,000 | **0 / 2,000** | Cost per correctly released document is unavailable. |

The v4 schema counts are TP 816, FP 20,898 and FN 15,184 over 16,000 gold field slots (F1
`0.0432730551`). Accepted-value counts are TP 0, FP 0 and FN 12,878 present gold values. The linked-row diagnostic
uses exact derived field ID, row ordinal and OCR surface string; it is not semantic row alignment or the creator's
official evaluator. It found 2,500 gold linked-field records, 30,133 gold cells and 7,234 gold rows, against zero
candidate cells or rows. The source documents contain table relationships that the no-model path does not propose.

The 35 unsupported PDFs had no text after attempted OCR. The remaining outcomes were 1,965 `needs_review`, including
unapproved schemas and other bounded-path limits. A separate v3 diagnostic used the portable executable and recovered
text on 12 of these 35 sources among its 1,229 partial sidecars. On those same 12, v4 produced zero characters. The
v4 sidecars mark 831 pages for Tesseract; all 831 report confidence 0.0, 828 are empty, and the other three contain
only raw-text fallback. The OCR helper swallowed `TesseractNotFoundError` into an empty result. The v4 provenance
did not record an OCR binary. The v3 diagnostic stopped early because multipass latency was high, so neither run
establishes bounded-OCR accuracy or speed. The v4 candidate is an **invalid OCR comparison** and must be rerun with
the executable, traineddata and OCR smoke recorded.

## Reproduction record

- Gate command: `python -m product_eval.run_gate --gold <frozen gold> --cohort <frozen cohort> --data-dir
  E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v4 --gate-id vrdu_v4
  --min-unique 2000 --workers 4 <eight pinned shard directories>`.
- Frozen cohort SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`.
- Frozen derived gold SHA-256: `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate JSONL SHA-256: `a8607a33223e8e159d1110919a02fa37a3cb8e65c73eaec48c30f7660908d37e`.
- Execution report SHA-256: `f05267f44fa8096bd8e6069c39791bf99427677ff00e1ebbdd48f4f1ff12aaec`.
- Quality report SHA-256: `7ade5cee10a1361538bcad3d4063c3cb05bb470b178dfd44044fd3b5c3000a60`.
- Family analysis SHA-256: `dfabb12cec963b21d2b69abb353f6922b5dada6c07b94935d3c2f9c3b0707c39`.
- All reports, candidates and `provenance.json` are retained under
  `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v4`, outside Git. The command and hashes identify the actual
  executed code, inputs and outputs.

## Decision

**Volume gate passed; OCR experiment invalid; quality and cost gates failed.** Keep abstention on unapproved schemas.
Do not promote this pipeline as a useful automatic extractor, claim lower cost, or use these results as a new
camera-ready paper result.
Test parser/OCR coverage, schema semantics, linked records and model reliability on small authorized development
slices; any substantive promoted extraction change requires another verified 2,000-unique-source run and a distinct
unseen-family holdout with human adjudication and measured total cost.
