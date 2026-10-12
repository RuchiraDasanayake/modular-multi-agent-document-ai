# VRDU 2,000-source v12 gate after approved-recipe routing

**Completed 13 October 2026.** Eight disjoint 250-PDF product shards exited zero. The gate verified **2,000 documents and 2,000 distinct original-source SHA-256 hashes**, with zero repeated source outputs, failed documents, or unsupported documents. All 2,000 outputs required review; none was automatically released. An independent verifier recomputed the SHA-256 of all 2,000 saved `result.json` files and checked each sealed result's embedded candidate against the scored `candidates.jsonl`: **2,000 passed, zero mismatches**.

| Strict metric | v11 | v12 |
| --- | ---: | ---: |
| Schema TP / FP / FN | 819 / 21,792 / 15,181 | **819 / 21,792 / 15,181** |
| Schema F1 | 4.2423% | **4.2423%** |
| Accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | **30,133 / 7,234** |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |
| Sum of per-document durations | 4,883,162 ms | **5,214,736 ms** |

This is an operational and review-integrity regression gate. The approved-recipe path was **not exercised**: the gate deliberately ran with no model and no selected recipe. The unchanged strict quality result is therefore expected and does not validate approved-recipe extraction. The duration sums are not a controlled speed comparison. The scorer matches exact derived field IDs, row ordinals, and OCR surface strings, without semantic aliases or the dataset creator's official matcher. Two PDF families do not establish arbitrary-document performance. Zero model calls does not mean zero compute cost: API, local compute, reviewer minutes, and total USD cost were unreported for all 2,000 documents. Cost per correctly released document remains undefined.

The gate began from product commit `1c18d996d6149fe2bfbd861523bd27ba01c226aa` with `working_tree_dirty=false`, Python 3.13.8, four workers, Tesseract `v5.5.3.20260724`, English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`, and a successful OCR preflight. Product code stayed unchanged during the gate. The independent result/candidate verifier was run from isolated evaluation-only commit `5d49450` after the gate; that verifier was not part of the v12 product runner.

**Decision:** the approved-recipe integration passes this 2,000-source no-model product regression. Its selected-recipe quality and model cost remain unmeasured. Subsequent product implementations require a fresh 2,000-distinct-source gate under the user's requirement.

## Reproduction and receipts

- Frozen cohort/gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` / `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate/execution/quality/family SHA-256: `488857a1dff6d5dcf0f4ebaeeb46cb602675a7fa409c244fe36084c597d9aed0` / `7800472cc01be71af8a04147aaa819ee07e3e5f452ef690c066042e25f7f9260` / `442bce5ac341dce354aa5faeeb62d532348a92c808a7c47dff86e5c6aa376ed5` / `56f80d352dff501328112b10ce9909b6746ff240f179d870f9a558c641fff373`.
- Command: `python -m product_eval.run_gate --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --data-dir F:\DocAI-Benchmarks\runtime --report-dir F:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v12-approved-recipe --gate-id vrdu_v12_approved_recipe --min-unique 2000 --workers 4 <eight pinned VRDU shard directories>`. Tesseract executable and tessdata were pinned through environment variables; child processes removed provider secrets.
- Full reports, logs, and candidates: `F:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v12-approved-recipe`. Per-document product sidecars: `F:\DocAI-Benchmarks\runtime\product_runs\vrdu_v12_approved_recipe_*`.
