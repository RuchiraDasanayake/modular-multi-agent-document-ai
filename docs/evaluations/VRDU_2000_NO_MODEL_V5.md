# VRDU 2,000-document v5 pinned-OCR gate (2026-10-12)

This is the completed, **no-model** product-auto development gate at clean commit
`dff56e6ecfb847fa2ac7ea00aeede713f172cf9e`. It tests the deterministic label/value proposer with a working,
pinned English Tesseract installation. It does **not** test AI schema generation, linked-row model proposals, recipe
matching, reviewer corrections, or the later OCR timeout implementation (`3e42612`). The 1,500 registration and 500
ad-buy PDFs are the same two-family VRDU development cohort used in earlier runs, not an untouched arbitrary-document
holdout. This scorer uses exact derived IDs and row ordinals, not the official VRDU matcher.

## Execution and OCR

Eight disjoint 250-PDF shards exited 0. `product_eval.run_gate` verified the raw source hashes and exact 2,000:2,000
gold/candidate ID join: **2,000 distinct sources, zero repeats, zero missing outputs**. All 2,000 documents have a
`needs_review` result; none is released, failed, or marked unsupported. The gate preflight started Tesseract, loaded
English traineddata, and recognized a generated image before starting any shard. It pinned Tesseract
`v5.5.3.20260724` and `eng.traineddata` SHA-256
`7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2` in every child process.

| OCR observation | v5 result |
| --- | ---: |
| Pages with native text / Tesseract | 3,481 / 831 |
| Documents with at least one Tesseract page | 677 |
| Tesseract pages with nonzero reported confidence | 831 / 831 |
| Previously v4-unsupported PDFs now yielding text and reviewable results | 35 / 35 |
| Tesseract candidate paths: initial only / quick retry / full retry / quick plus full | 650 / 87 / 72 / 22 pages |
| OCR stage p50 / p95 across all documents | 11 ms / 9,334 ms |
| OCR stage p50 / p95 on Tesseract documents | 3,058 ms / 21,632 ms |
| Maximum OCR stage time on one document | 139,875 ms |

The v4 run lacked the OCR executable; its 35 `unsupported` outcomes were an execution-environment error, not proof of
unreadable source PDFs. V5 recovered text on all 35. Nonzero OCR confidence shows the engine ran; it does not prove
transcription or field correctness. The sum of per-document durations was 4,993,602 ms across four concurrent
workers; this is **not** wall time or a cloud/compute price. The report files were written about 22.3 minutes after
preflight began on this host, but filesystem timestamps are only an approximate wall-time record. All API, compute,
and reviewer cost fields remain null.

## Extraction quality and decision

| Metric | v4 with missing OCR | v5 with pinned OCR | Interpretation |
| --- | ---: | ---: | --- |
| Strict schema F1 | 4.327% | **4.245%** | More readable text did not make label-derived schema IDs semantically accurate. |
| Strict schema TP / FP / FN | 816 / 20,898 / 15,184 | **819 / 21,769 / 15,181** | Three additional matches and 871 additional spurious IDs. |
| Pre-review accepted-value F1 | 0% | **0%** | Unapproved dynamic schemas remain in review. |
| Proposed linked cells / rows | 0 / 0 | **0 / 0** | Gold contains 30,133 cells in 7,234 rows. |
| `needs_review` / `unsupported` / `failed` | 1,965 / 35 / 0 | **2,000 / 0 / 0** | The OCR environment was repaired; quality still fails. |
| Model calls / correct automatic releases | 0 / 0 | **0 / 0** | This run cannot assess model-backed extraction or cost per correctly released document. |

By family, strict schema F1 is **1.221%** on 500 ad-buy PDFs (70/7,000 gold slots matched) and **5.524%** on 1,500
registration PDFs (749/9,000 matched). The strict scorer does not infer semantic aliases: for example, it treats
`foreign_principal_name` and the dataset's `foreign_principle_name`, and `registration_number` and `registration_num`,
as distinct. This makes the score intentionally strict, but the 15,181 missed and 21,769 spurious slots and absence of
all proposed linked cells remain substantial failures. The registration and ad-buy templates also do not establish
performance on unfamiliar document families.

**Decision: volume and OCR-environment gate passed; extraction quality and cost gates failed.** Keep every schema and
value in review. Do not promote this as a useful automatic extractor, a world-class result, a lower-cost result, or a
new camera-ready paper result. The local Qwen and ICORE public pilots are separate bounded experiments, and the
new OCR timeout code requires its own pinned 2,000-source gate before promotion. A fixed-schema local-model diagnostic
can isolate value extraction from schema discovery, but an oracle schema must never be scored as an automatic schema.

## Reproduction record

- Pinned source repository: [Google VRDU](https://github.com/google-research-datasets/vrdu), creator commit
  `04a4df7ac5cc694e51c48115c03fe428f0e240cc`.
- Frozen cohort SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`.
- Frozen derived gold SHA-256: `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
- Candidate JSONL SHA-256: `242bdec7ea85859753536214cec7910286dbe313c0345b5230d34019953ee0a0`.
- Execution / quality / family report SHA-256: `72e60e0208bfe5e3373ec4335fc8799154986816c791a7449921ebf7fd061de1` /
  `86185a5cdbd35bd39ab564421f4868d3a3be1d75e41dc66586cbd2f03ce572e9` /
  `ebc6d01a66375c248693ba4e5bf8ba274ee743300f0fbf83ba61b13444871532`.
- Command: `python -m product_eval.run_gate --gold <frozen gold> --cohort <frozen cohort> --data-dir
  E:\DocAI-Benchmarks\runtime --report-dir E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v5 --gate-id vrdu_v5
  --min-unique 2000 --workers 4 <eight pinned shard directories>`, with `TESSERACT_CMD` and `TESSDATA_PREFIX` set to
  the paths recorded in `provenance.json`.
- Full reports, candidates, logs, and provenance: `E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gate-v5` (outside Git).
