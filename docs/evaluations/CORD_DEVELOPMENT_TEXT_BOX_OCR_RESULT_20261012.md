# CORD development text-box OCR diagnostic: result (2026-10-12)

**Decision:** PP-OCRv6 small is the stronger recognizer for these frozen CORD
text-box crops. Test it next in a source-locked full-page detection-plus-
recognition pipeline before considering a product OCR change. This result does
not measure complete receipt extraction, row linking, source evidence, or cost
per correct document.

The paired, recognition-only experiment followed the frozen
[plan](CORD_DEVELOPMENT_TEXT_BOX_OCR_PLAN.md). It used the same 1,389 saved PNG
crops from 796 creator-annotated `valid_line` entries in 60 CORD v2 development
receipts. The 40 reserved receipts were excluded. Both engines saw the same
crop bytes; all failed outputs would have remained in the denominator. Text
was normalized with Unicode NFKC and collapsed whitespace. Case and
punctuation remained significant. A box can contain spaces and is not always
a lexical word. Only annotated boxes were scored, so the experiment has no
text-detection or full-page false-positive denominator.

| Measure | Tesseract 5.5.3 | RapidOCR 3.10.0 / PP-OCRv6 small | Rapid minus Tesseract |
| --- | ---: | ---: | ---: |
| Exact boxes | 733 / 1,389 (52.772%) | 1,226 / 1,389 (88.265%) | +35.493 points |
| Exact, receipt macro | 52.414% | 87.109% | +34.695 points |
| Character edits / 6,853 gold code points | 1,439 / 6,853 | 176 / 6,853 | -1,263 edits |
| CER, micro | 20.998% | 2.568% | -18.430 points |
| CER, receipt macro | 21.359% | 2.849% | -18.510 points |
| Crop failures / timeouts | 0 | 0 | 0 |
| Crop latency p50 / p95 | 137.519 / 198.236 ms | 13.308 / 19.633 ms | — |
| Sum of sequential crop calls | 200.493 s | 20.243 s | — |

The exact paired categories were **695 both correct, 38 Tesseract only, 531
RapidOCR only, and 125 neither**, summing to 1,389. RapidOCR had more exact
boxes on 56 receipts, Tesseract on 2, and they tied on 2; character-edit
counts have the same 56/2/2 pattern. A 10,000-replicate paired bootstrap over
the 60 receipts (seed `20261012`) gave a 95% interval of **+30.350 to +40.551
percentage points** for the exact-box micro difference and **-22.644 to
-14.584 points** for the micro CER difference. These intervals describe this
fixed development slice, not unseen document families.

## Runtime and resource scope

Tesseract ran as one Windows process per crop, `--oem 3 --psm 7`, with
`OMP_THREAD_LIMIT=4` and a 15-second crop timeout. RapidOCR used the pinned
English PP-OCRv6 small ONNX recognizer with detection and classification off,
four intra-op and one inter-op CPU threads. The runner verified the actual
`CPUExecutionProvider`; CUDA and DirectML were disabled. RapidOCR's first
crop took 218.001 ms, including lazy model load. The raw file's creation to
summary-write timestamps span about **222 seconds**; this is an approximate
wall-clock receipt, while the table reports measured in-call sums. A single
early process snapshot showed about 121 MiB peak working set at that point;
the experiment did **not** instrument whole-run peak RAM or energy, so those
costs remain unknown. No API, GPU inference, or cloud bill was involved.

The apparent crop-call speed advantage depends on launching Tesseract 1,389
times while reusing one RapidOCR session. It is not a measured full-page
throughput or deployment price ratio. Crop rectification also gives both
engines creator-provided geometry that a product detector would have to find.
The next comparison must include detector recall/false positives, page order,
exact source evidence, linked rows, HITL decisions, and compute/review cost
on locked scans. Keep the reserved 40 CORD receipts out of iterative choices.

## Reproduction and independent checks

- Frozen manifest SHA-256:
  `03eeddf3526b28031582460419b3c1ed27bcacc285e194d193b19110fbb610f5`.
  Development cohort SHA-256:
  `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a`.
- Tesseract executable SHA-256:
  `c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420`;
  English traineddata SHA-256:
  `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
  PP-OCRv6 small recognition ONNX SHA-256:
  `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`.
- Runtime: RapidOCR 3.10.0, ONNX Runtime 1.23.2, Pillow 12.3.0,
  `CPUExecutionProvider`. Source and model licenses are recorded in the plan.
- Raw prediction SHA-256:
  `329c259145dadb14450fc82839008826ce0a44857572b8527e2f57636d01cf47`;
  full summary SHA-256:
  `6df1904d57f2699b503e1878510704dceb7016ea46b2ba26cc0239bdaea0341d`.
  Both files and the crops remain outside Git at
  `E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\word-ocr-dev-v1`.
- The plan's exact `check` returned `ready=true` before inference. Afterward,
  `load_manifest` verified every crop hash, raw rows were joined by crop ID,
  source SHA and order, and `score_predictions` independently reproduced the
  saved counts, rates, latencies, and per-receipt totals. All 60 raw source
  hashes equal the development cohort; none occurs in the reserved cohort.
