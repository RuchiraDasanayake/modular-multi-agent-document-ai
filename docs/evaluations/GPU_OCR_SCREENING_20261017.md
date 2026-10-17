# GPU OCR screening — 17 October 2026

Classification: supporting research evidence; action: keep.

## Decision

Keep the deployed CPU RapidOCR worker. The CUDA trial proves a large warm OCR
speedup on two development receipts, but it does not justify changing a product
that starts a bounded child process for each page. The unprofiled first-page
process was slower in the same trial harness, one of 37 OCR lines differed, and
the GPU process used substantially more RAM. No product code, worker protocol,
frozen benchmark, or installed CPU runtime was changed.

## Trial boundary

- Hardware: Windows host, Intel i5-10400F (6 cores/12 threads), 24 GB RAM,
  NVIDIA RTX 3060 Ti (8 GB, compute capability 8.6), driver 610.88.
- Existing CPU interpreter: Python 3.11, `rapidocr==3.10.0`,
  `onnxruntime==1.31.0`, `opencv-python-headless==5.0.0.93`,
  `Pillow==12.3.0`, `numpy==2.4.6`.
- New isolated interpreter: Python 3.11, `rapidocr==3.10.0`,
  `onnxruntime-gpu==1.31.0`, `opencv-python-headless==5.0.0.93`,
  `Pillow==13.0.0`, `numpy==2.4.6`; NVIDIA CUDA runtime 13.4.92,
  cuDNN 9.27.0.42, cuBLAS 13.8.0.4. The installed ONNX Runtime wheel reports
  CUDA **13.0** as its build version. `pip check` passed.
- Identical, locally hashed models in both lanes: `PP-OCRv6_det_small.onnx`
  `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`,
  `PP-OCRv6_rec_small.onnx`
  `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`,
  `ch_ppocr_mobile_v2.0_cls_mobile.onnx`
  `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`.
- Inputs were two **previously used development originals**, never an untouched
  holdout: CORD `cord_test_0083.png` (864×1296,
  SHA-256 `28a8c9e154f9971aaae01212e395618460e610da9eca8f82d05b9b5277eb8c7c`)
  and `cord_test_0017.png` (960×1280,
  SHA-256 `4322ab5ec4f0b1365e08af0c31288e65e8cbd2c8eb5241adfb329244acbbb30b`).
  No gold labels or model APIs were used.

The trial used explicit model paths, disabled RapidOCR downloads, preloaded
NVIDIA DLLs from the isolated interpreter, selected CUDA only in that
interpreter, and saved receipts in `I:\DocAI-Runtime\gpu-ocr-trial-20261017`.
The installed CPU environment was read only. ONNX Runtime's
`get_available_providers()` alone was not treated as proof of GPU execution.

## Timing and memory

All times are milliseconds. The 2,000-document CPU campaign was running on the
same host, so these are screening measurements under changing contention, not a
controlled throughput benchmark. Profiling was separate from the timings below.

| Path | `0083` one-page process wall | First OCR call | Peak process working set |
| --- | ---: | ---: | ---: |
| Deployed CPU worker, exact `-I -B` product entrypoint | 5,197 | included in wall | worker not separately sampled here |
| Deployed CPU interpreter, unprofiled trial harness | 2,647 | 1,323 | 253 MiB |
| Isolated GPU interpreter, same unprofiled trial harness | 5,572 | 2,504 | 1,250 MiB |

The deployed CPU worker took 6,884 ms for a separate cold `0017` process.
Different harnesses and different moments on a busy host must not be combined
into a speed ratio. The same-harness first-page pair favors CPU in this run.

| Two-page, eight-call same-harness run | Process wall | `0083` warm median | `0017` warm median | Peak working set |
| --- | ---: | ---: | ---: | ---: |
| Deployed CPU interpreter | 28,943 | 2,445 | 2,632 | 360 MiB |
| Isolated GPU interpreter | 5,667 | 112 | 524 | 1,278 MiB |

Each warm median uses three calls to the same page after its first call. GPU
total device memory reported by `nvidia-smi` rose from 1,644 to at most
2,487 MiB during the eight-call process; that **843 MiB device-wide delta**
is not a process-specific allocation measurement. The GPU process peak was
already about 1,278 MiB against the current worker's 1,536 MiB RAM limit,
without testing larger pages. The installed GPU virtual environment occupied
2,199,947,169 file bytes, versus 312,693,593 for the deployed CPU environment.

The GPU profiling receipt recorded CUDA provider execution in all three models:
190 detection, 358 classification, and 362 recognition **node executions**;
recognition also had four CPU node executions. All three sessions listed CUDA
first. These event counts are repeated executions, not unique graph-node counts.

## Output agreement

The deployed CPU worker and CPU trial harness produced the same ordered text on
both pages. Within each lane, all repeated runs on each page had the same text.

| Input | Ordered line text | Largest polygon coordinate difference | Largest absolute line-score difference |
| --- | --- | ---: | ---: |
| `0083` | 12/12 lines identical | 0 px | 0.00669 |
| `0017` | 24/25 lines identical | 1 px | 0.01958 |

The differing `0017` line was `Dlsount` on CPU and `Dlisount` on GPU: one
inserted character. No annotation was consulted, so this is an agreement
finding, not a claim that either output is correct. The different Pillow
versions also prevent attributing this difference solely to CUDA.

## Limits and follow-up

Additional cold pairs were stopped before launch when available host RAM fell
to 2.9 GB while the campaign and other desktop workloads were active, below
the 4 GB reserve for the campaign.
The sample is two receipts, lacks ground-truth scoring, and says nothing about
general-document extraction accuracy, monetary savings, or 2,000-document GPU
throughput. The GPU result must not be substituted into the CPU benchmark or
paper claims.

If a persistent OCR worker is later justified, test it as a separate versioned
adapter with the same complete dependency closure, strict source/model hashes,
provider-node verification, page/resource limits, isolation, failure behavior,
and representative development quality gates. Repeated cold process tests are
required before any per-page GPU rollout. Keep the current CPU provider and
receipt contract until such evidence exists.

Local receipts: `comparison-summary.json`, `result-cpu-production.json`,
`result-gpu.json`, `result-gpu-single-profile.json`, the production worker
results, and the trial scripts in the isolated I: directory above. The
comparison summary SHA-256 is
`25824f92ede324cbd59f0911b7c1c8a11eaab75ccfff18d82811dad781150ccf`.

## Primary sources

- [RapidOCR installation and execution engine documentation](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/install/)
- [ONNX Runtime CUDA provider requirements and DLL preloading](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
- [ONNX Runtime Python profiling and session API](https://onnxruntime.ai/docs/api/python/api_summary.html)
- [ONNX Runtime GPU 1.31.0 release files](https://pypi.org/project/onnxruntime-gpu/1.31.0/)
