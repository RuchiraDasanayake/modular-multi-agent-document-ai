# VRDU 2,000-source v13 gate after native tables on the model path

**Completed 13 October 2026.** The product ran from clean commit `f319d0ff74e0844237d2749e59f222cc38d209f7` on eight frozen, disjoint VRDU PDF shards. All shard processes exited zero. The gate verified **2,000 documents, 2,000 distinct original-source hashes, zero repeated source outputs, zero failed or unsupported documents**, and exact candidate/result consistency. An independent second pass checked the saved `result_sha256` for all **2,000** product results. All 2,000 results required human review; no document was automatically released.

| Strict metric | v12 | v13 |
| --- | ---: | ---: |
| Schema TP / FP / FN | 819 / 21,792 / 15,181 | **819 / 21,792 / 15,181** |
| Schema F1 | 4.2423% | **4.2423%** |
| Accepted-value F1 | 0% | **0%** |
| Proposed linked cells / complete rows | 0 / 0 | **0 / 0** |
| Gold linked cells / complete rows | 30,133 / 7,234 | **30,133 / 7,234** |
| Correct automatic releases / model calls | 0 / 0 | **0 / 0** |
| Sum of per-document durations | 5,214,736 ms | **4,782,592 ms** |

This is an operational regression gate after integrating source-backed native table rows alongside a valid dynamic model response. **No model was configured**, so the newly integrated model-assisted table path was not exercised by these 2,000 PDFs. Synthetic focused tests cover that path; this gate does not establish a real extraction-quality improvement. The duration sums are not a controlled speed comparison. Exact derived field IDs, row ordinals and OCR surface strings drive this scorer, rather than semantic aliases or the dataset publisher's official metric. These two PDF families do not establish arbitrary-document quality. API charge, local compute cost and reviewer time were not measured, so cost per correctly released document is undefined.

The run used Python 3.13.8, four workers, Tesseract `v5.5.3.20260724`, English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`, and a successful OCR preflight. Product code remained unchanged during the gate. The integrated gate verifier checked every saved result hash and candidate equality; an independent invocation of `verify_result_receipts` returned `2000`.

**Decision:** the product change passes the required 2,000-distinct-source no-model operational gate. Model-assisted table quality and cost remain unmeasured. The next broader gate adds receipt images with positive linked-row gold.

## Frozen receipts

- Cohort/gold SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90` / `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate/execution/quality/family SHA-256: `b0b47e2db5f53c52c8f3179ad45873eff3f8ab7647269667952c4dfca22c98f0` / `6e487b5ebba5368243400c54de965b7f65bbba041d26b5f210aa27fd22c64317` / `6b1f245f3691c268f15b90a3f99c2e5c25cdc4a918bd6babfa0d6abc139b3534` / `0f277e5f572a1937cdb2f534aae85b7c87cfe2b0f49f23ce3a1521c251ec3c9e`.
- Full reports and logs: `F:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v13-native-model-tables`; product sidecars: `F:\DocAI-Benchmarks\runtime\product_runs\vrdu_v13_native_model_tables_*`.
- Gate command: `python -m product_eval.run_gate --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --data-dir F:\DocAI-Benchmarks\runtime --report-dir F:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v13-native-model-tables --gate-id vrdu_v13_native_model_tables --min-unique 2000 --workers 4 <eight frozen VRDU shard directories>`.
