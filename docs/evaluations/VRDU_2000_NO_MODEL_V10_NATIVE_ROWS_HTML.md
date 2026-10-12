# VRDU 2,000-source v10 gate after native rows and HTML recovery

**Completed 13 October 2026.** Eight disjoint 250-PDF product shards exited zero. The verifier found **2,000 documents, 2,000 distinct original-source SHA-256 hashes, zero repeated outputs, zero failed or unsupported documents**, and matching candidate/gold IDs. All 2,000 documents remained `needs_review`; none was automatically released. This is a clean-start PDF execution regression gate for the native row proposal and HTML parser changes. Its two VRDU families do **not** test those native formats or establish arbitrary-document extraction quality.

| Strict metric | v9 | v10 |
| --- | ---: | ---: |
| Schema TP / FP / FN | 819 / 21,792 / 15,181 | **819 / 21,792 / 15,181** |
| Schema F1 | 4.2423% | **4.2423%** |
| Accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | **30,133 / 7,234** |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |
| Sum of per-document durations | 4,440,790 ms | **4,839,003 ms** |

The duration sums are **not** a controlled speed comparison. The strict scorer uses exact derived field IDs, row ordinals, and OCR surface strings, without semantic aliasing or the dataset creator's official matcher. The no-model PDF route still cannot propose the annotated rows. Zero model calls does not mean zero compute cost: API, local compute, reviewer minutes, and total money cost were unreported for all 2,000 documents. Cost per correctly released document remains undefined because no document was released.

The gate began from product commit `49e54b340136bbeae766f80a59db878660b5e076` with `working_tree_dirty=false`, Python 3.13.8, four workers, Tesseract `v5.5.3.20260724`, English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`, and a successful OCR preflight. Docs and evaluation-only commits landed while shards ran; no `idpo/` or `frontend/` product code changed before completion. The provenance identifies the gate's startup product commit, and the report hashes bind its actual outputs.

**Decision:** operational regression passed; field meaning, linked rows, automatic release, and total cost remain unproven or poor. Preserve the review-only native adapter. The separate ten-real-file native product diagnostic recovered zero linked rows without gold labels, so it cannot be treated as a quality win. The pending sealed-review implementation is a new product change and requires a **fresh** 2,000-distinct-source gate after integration.

## Reproduction and receipts

- Frozen cohort/gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` / `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate/execution/quality/family SHA-256: `ce20dfa939a3532381e8ffb2e7400709d41d3826d4785954e0a5ddc3e425b9ff` / `13b5bf0f1cd3c1062e2ce53baa5931af59fb966823d353056a82d872b2e0659d` / `a5b388add565ade8d9fb2917319e56eca0f90212b2ec0d14c85c04dd289621e3` / `f2df6bdc65ff9326336eb281ff9f6a23ff525e53c10697c8e4ecdb3b7f4c2dd0`.
- Command: `python -m product_eval.run_gate --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --data-dir E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v10-native-rows-html --gate-id vrdu_v10_native_rows_html --min-unique 2000 --workers 4 <eight pinned shard directories>`. Tesseract executable and tessdata were pinned through environment variables; child processes removed provider secrets.
- Full reports, logs, and candidates remain outside Git at `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v10-native-rows-html`; per-document sidecars are under `E:\DocAI-Benchmarks\runtime\product_runs\vrdu_v10_native_rows_html_*`.
