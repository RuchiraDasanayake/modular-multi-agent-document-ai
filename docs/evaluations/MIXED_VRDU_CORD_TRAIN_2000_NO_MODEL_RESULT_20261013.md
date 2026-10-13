# Mixed VRDU and CORD train: 2,000-source no-model product gate

**Completed 13 October 2026** from clean product commit `de289de5bac68bf74cab68d374c712d728a60135`. The unchanged `process-auto` product path processed eight frozen shards: 897 VRDU registration PDFs, 305 VRDU ad-buy PDFs, and 798 CORD v2 train receipt images. All **2,000 raw source SHA-256 values are distinct**. The eight shard subprocesses exited zero; the gate verified original-source hashes, one candidate per source, saved result hashes, and candidate/result equality. A separate invocation of `verify_result_receipts` independently returned **2,000**. No model was configured or called.

| Operational result | Count |
| --- | ---: |
| Distinct sources / saved results | 2,000 / 2,000 |
| Failed / unsupported / repeated source outputs | 0 / 0 / 0 |
| Documents requiring review / automatically released | 2,000 / 0 |
| Model calls | 0 |
| Sum of per-document durations across four workers | 13,750,297 ms |

The **strict combined schema F1 was 3.375%** (485 TP, 13,637 FP, 14,134 FN), with zero accepted values and zero proposed linked cells or complete rows. This combined F1 is an operational regression diagnostic, **not a homogeneous extraction-quality estimate**: CORD gold annotates positive receipt values but not absent fields, and the VRDU strict scorer requires exact derived field IDs and OCR surface strings. The separate family slices are more useful:

| Family | Sources | Strict schema F1 | Gold linked cells / rows | Proposed cells / rows |
| --- | ---: | ---: | ---: | ---: |
| VRDU registration form | 897 | 5.465% | 0 / 0 | 0 / 0 |
| VRDU ad-buy form | 305 | 1.242% | 18,672 / 4,443 | 0 / 0 |
| CORD train receipt | 798 | 0% exact ID diagnostic | 6,066 / 2,098 | 0 / 0 |

The independent **CORD positive-only** scorer reverified the complete gate and its source/candidate receipts before scoring the receipt subset. It found **0/2,654** exact proposed scalar positives, **0/6,066** exact proposed linked-cell positives, and **0/2,076** scored complete rows. The row scorer requires both `item_name` and `item_price` annotations, so its denominator is smaller than the 2,098 published menu rows in the bundle. These are recall measures; CORD precision and F1 are undefined because unannotated negatives are unknown. The subset is from **train**, with raw-byte exclusion against locally available CORD test images; no vendor/layout or validation-split disjointness is established.

**Decision:** the no-model product passes the requested 2,000-distinct-source **execution** gate but does not meet a useful automatic-extraction or lower-total-cost gate. Every result needs human review, and the system proposed no linked row on either table-bearing family. API calls were zero, but compute/electricity and reviewer minutes were not priced or measured; cost per correctly released document is undefined. Do not promote a parser, OCR engine, local VLM, agent loop, or cloud provider from this baseline alone. A precommitted, evidence-checked local model diagnostic is the next quality gate; any product extraction change requires a new 2,000-source run.

## Reproduction and receipts

- Frozen source bundle: `I:\DocAI-Benchmarks\mixed-vrdu-cord-train-2000-v1`; cohort SHA-256 `3de27807196afa0aa37365f733d2d30903ffa1824420f8684922d355ea7c831d`; gold SHA-256 `b3eb6d705e435caf07d495b450a312a84214abc44378df894fc79e18d90b0440`.
- Full gate reports and eight logs: `I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1`. Final provenance SHA-256 `60131261635f32462cef732250f1411931aa5f792943ef1f7dd694ef41102f3b`; aggregate candidate SHA-256 `91fd16007559f2e83c62728fdeddb80f122dbd794f8bb14d26308bb79616d9ba`; execution report SHA-256 `3133d8ea46311c5d142dd0ef91f92956d0c9c67c81cc07cc0af1a8eaca2e97bf`; quality report SHA-256 `374e9cce8a4afb74a9477427c8c78c7f9eb39b7ee5826b78d540700e2ce375f9`; family report SHA-256 `0da506b816ba3d8d7a8dd5ba0bcfdd36c1b63cd9d9ab5f6174994be84efba4f9`.
- CORD positive-only report: `I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1\cord-positive.json`, SHA-256 `9ff65d50639ecf0ced155c9ed40e21982ac57d99ccfdb1c62d91a58b78e1976`.
- Python 3.13.8, four shard workers, pinned Tesseract `v5.5.3.20260724`, English traineddata SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`; OCR smoke passed. Original run ID: `mixed_vrdu_cord_train_v1`.
- Run command: `python -m product_eval.run_gate <the eight frozen bundle/shards/shard_00..07 paths> --gold I:\DocAI-Benchmarks\mixed-vrdu-cord-train-2000-v1\gold.jsonl --cohort I:\DocAI-Benchmarks\mixed-vrdu-cord-train-2000-v1\cohort.jsonl --data-dir I:\DocAI-Benchmarks\runtime --report-dir I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1 --gate-id mixed_vrdu_cord_train_v1 --min-unique 2000 --workers 4`. Both run IDs and report directory must be new for a repeat; existing partial or completed runs are never silently reused.
- Positive scorer command: `python -m product_eval.datasets.mixed_cord_positive --bundle-dir I:\DocAI-Benchmarks\mixed-vrdu-cord-train-2000-v1 --gate-report-dir I:\DocAI-Benchmarks\mixed-vrdu-cord-train-run-v1 --output <fresh path>`.
