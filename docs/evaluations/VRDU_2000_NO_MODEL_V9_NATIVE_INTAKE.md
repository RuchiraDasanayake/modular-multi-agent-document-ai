# VRDU 2,000-source v9 gate after native-format intake (12 October 2026)

The no-model `process-auto` gate completed eight disjoint 250-PDF shards. The verifier found **2,000 documents with 2,000 distinct raw-source hashes**, complete candidate/gold IDs, zero repeated outputs, and zero failed or unsupported documents. All 2,000 remain `needs_review`; none was automatically released. This was a PDF regression and operations gate for the newly added DOCX/XLSX/PPTX/HTML/EML intake. It does not measure those formats.

| Strict metric | v8 | v9 |
| --- | ---: | ---: |
| Schema TP / FP / FN | 819 / 21,792 / 15,181 | 819 / 21,792 / 15,181 |
| Schema F1 | 4.2423% | **4.2423%** |
| Accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | 30,133 / 7,234 |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |
| Sum of per-document durations | 4,672,868 ms | **4,440,790 ms** |

The elapsed-duration change is not a controlled speed comparison. The strict scorer uses exact derived field IDs, row ordinals, and OCR surface strings; it does not infer semantic aliases or use the creator's official matcher. Native intake did not fix the PDF schema or linked-row gap. The 500 ad-buy and 1,500 registration documents do not represent arbitrary document types. API, compute, total money cost, and reviewer minutes were not reported for any of the 2,000 documents. Zero model calls is a measured count, but **cost per correctly released document remains undefined**, because no document was released and local compute/review costs were not priced.

The gate used product commit `d6e560232ef1d8b667173a95cb79e9ab760a3545`, Python 3.13.8, four workers, Tesseract `v5.5.3.20260724`, and English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. Its provenance records `working_tree_dirty=true`, so this is weaker than v8's clean-detached provenance. The committed diff from that commit through gate completion contained evaluation code/docs but no product implementation change. The dirty flag does not preserve an exact startup working-tree snapshot, so do not treat this as a clean-run claim. Every shard exited zero, the source-hash verifier passed, and the report hashes below bind the actual outputs.

**Decision:** execution regression passed; extraction quality and automation did not. Keep the new native formats review-only. Evaluate them on real, rights-cleared files separately, and run another fresh 2,000-distinct-source gate after the pending row/review/parser changes.

## Reproduction and receipts

- Frozen cohort/gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` / `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate/execution/quality/family SHA-256: `e2cc16ee73be17a2b7113813a13998fee5d808afbe389b14c47e6600f13e9704` / `116f29a3924d28559b0415e58c3f559ccdc74640c1be04f645e4826215d7635e` / `cbd1b055f112348ca5058927f47cfa87751c20033c4b06d62be50aadfb7597d2` / `c99f74ad308a8239812689aa60585bc89f99591e9f76d66d21c12b322d4b1678`.
- Command: `python -m product_eval.run_gate --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --data-dir E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v9-native-formats --gate-id vrdu_v9_native_formats --min-unique 2000 --workers 4 <eight pinned shard directories>`. Tesseract executable and tessdata were pinned through environment variables; child processes removed provider secrets.
- Full reports, logs and candidates remain outside Git at `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v9-native-formats`; per-document sidecars are at `E:\DocAI-Benchmarks\runtime\product_runs\vrdu_v9_native_formats_*`.
