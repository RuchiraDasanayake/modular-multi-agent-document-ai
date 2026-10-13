# VRDU 2,000-source v11 gate after review-result receipts

**Completed 13 October 2026.** Eight disjoint 250-PDF product shards exited zero. The verifier found **2,000 documents, 2,000 distinct original-source SHA-256 hashes, zero repeated source outputs, and zero failed or unsupported documents**. All 2,000 documents were `needs_review`; none was automatically released. An independent pass recomputed the SHA-256 of all **2,000 saved `result.json` files** and matched every manifest `result_sha256` (zero missing receipts, mismatches, or files). This is an operational and review-integrity regression gate, not evidence of improved extraction quality.

| Strict metric | v10 | v11 |
| --- | ---: | ---: |
| Schema TP / FP / FN | 819 / 21,792 / 15,181 | **819 / 21,792 / 15,181** |
| Schema F1 | 4.2423% | **4.2423%** |
| Accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | **30,133 / 7,234** |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |
| Sum of per-document durations | 4,839,003 ms | **4,883,162 ms** |

The duration sums are **not** a controlled speed comparison. The strict scorer uses exact derived field IDs, row ordinals, and OCR surface strings, without semantic aliasing or the dataset creator's official matcher. The two VRDU PDF families do not establish arbitrary-document quality. Zero model calls does not mean zero compute cost: API, local compute, reviewer minutes, and total money cost were unreported for all 2,000 documents. Cost per correctly released document remains undefined because no document was released.

The gate began from product commit `af2aceed93b458dfcce48b472a5d0bae64b6fffc` with `working_tree_dirty=false`, Python 3.13.8, four workers, Tesseract `v5.5.3.20260724`, English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`, and a successful OCR preflight. Product code stayed unchanged while the gate ran. This commit includes the result-byte receipt and review audit provenance changes; the new recipe-routing path is not in this gate.

**Decision:** the review-result receipt regression passed. Field meaning, linked rows, automatic release, and total cost remain poor or unproven. Any subsequent product implementation requires another fresh 2,000-distinct-source gate under the user's requirement.

## Reproduction and receipts

- Frozen cohort/gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` / `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate/execution/quality/family SHA-256: `ebfd2f71fe97ea3f4ec57e493e14b9cfc980fac9341d0bd9fc7ea089803070ac` / `500bd51191cb103e3768776ee81c50f3fc71d3ac46e035e3376be9f5c325c22c` / `685a29b8c7f44d44dd4b5307830b37695252c35e72190c5ffd8de6d99962a045` / `3bbee4f38d07a74b1098361d96f3952eb7d4480b755f8024b35927e7d83c2866`.
- Command: `python -m product_eval.run_gate --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --data-dir E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v11-review-result-receipt --gate-id vrdu_v11_review_result_receipt --min-unique 2000 --workers 4 <eight pinned shard directories>`. Tesseract executable and tessdata were pinned through environment variables; child processes removed provider secrets.
- Full reports, logs, and candidates: `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v11-review-result-receipt`. Per-document product sidecars: `E:\DocAI-Benchmarks\runtime\product_runs\vrdu_v11_review_result_receipt_*`.
