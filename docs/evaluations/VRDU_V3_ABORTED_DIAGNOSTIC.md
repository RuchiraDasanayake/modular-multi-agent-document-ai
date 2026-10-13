# VRDU corrected-OCR diagnostic v3: aborted, not a 2,000-document gate

The no-model v3 rerun began at code revision `17c9104d7f0e2a36a4bdb39b94dbcdf97c37619a` after correcting a stale
Tesseract data path. Its original intent was a full 2,000-distinct-PDF gate. It was stopped on 2026-10-11 UTC after
the legacy multipass OCR route proved too slow on scans. **No 2,000-document completion or quality claim is made for
v3.** The [v2 safety run](VRDU_2000_NO_MODEL_V2.md) remains the latest complete gate for that earlier candidate.

Four of eight 250-PDF shards completed. `product_eval.verify_execution` rehashed their source bytes and verified
1,000 distinct sources, no repeated output, and 1,000 `needs_review` statuses. Four other shards were incomplete and
have no `run.json` completion marker. A separate partial-artifact audit rehashed all 1,229 written sidecars, found
1,229 distinct source hashes and matching candidate IDs/statuses, and labeled the diagnostic `full_gate_passed: false`.
Among 35 sources unsupported by v2, 12 had nonempty OCR text and `needs_review` outcomes in the partial v3 set.
This is evidence that the corrected OCR can recover some scans, not a field-accuracy or generalization result.

For the 1,229 **completed sidecars only**, the sum of document durations was 8,043,252.94 ms, median 174.687 ms,
p95 30,455.725 ms, and maximum 517,221.111 ms. These are conditional partial-run statistics, not full-cohort latency
or parallel wall time. The long tail made a corrected but unchanged multipass route impractical for this gate.
The next candidate uses a product-only single initial OCR variant with quality-triggered retry; it needs a fresh full
2,000-source execution and score before any quality or cost comparison. Reviewer minutes and priced compute remain
unmeasured.

Local artifacts outside the repository:

- `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\v3-aborted-diagnostic.json` (SHA-256
  `a3d01cd99ceb743eb7c758379a0920ffbaa4a355daa696e65550bd409a6440e2`).
- `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\execution-report-v3-completed-shards.json` (SHA-256
  `c6acca5be6e177af67b016735069f33ede42a1c5302fe3b25594d4a988693471`).

The four partial run directories are retained under `E:\DocAI-Benchmarks\runtime\product_runs`. Their sidecars must
not be concatenated with completed shards and presented as a verified full run.
