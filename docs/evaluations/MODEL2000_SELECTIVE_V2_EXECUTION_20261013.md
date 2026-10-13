# Frozen 2,000-original model execution — selective v2

Status: **running**, after a successful first checkpoint of 25 originals.
This document records admission and the checkpoint, not a completed benchmark
or an accuracy result. All reported observations are from 13 October 2026.

## Frozen candidate

- Detached backend commit: `0cce810734c863f01f7e6956c792ee34e64da3c7`.
- Protocol SHA-256:
  `b9571b78a9be196573cd14c7ac8b4050cb741f091646eeb1c76257bfdae69eeb`.
- 2,000 byte-distinct originals: 897 registration PDFs, 305 ad-buy PDFs and
  798 CORD training receipts. Source bytes, schemas, executing Python sources,
  runtime installation manifests and OCR model files are pinned.
- Fresh product intake; RapidOCR when needed; Luna 6; strict confirmed values;
  bounded text segments; `bounded_visual_selective_v2`.
- Four workers, 8,192 output tokens, 180-second requests, four calls per source
  and a global maximum of 2,500 attempts. SDK retries are disabled.
- Checkpoints every 25 originals. An uncertain paid attempt is retained and
  never automatically replayed. Resume dispatches only untouched sources.
- Private output: `I:\DocAI-Benchmarks\final-model2000-selective-v2-20261013`.

The call cap is not a monetary price estimate and may stop the campaign before
all sources if too many require multiple requests. Provider prices are not
verified. The runner retains failures and unattempted sources in its accounting.

## Four-worker resource admission

A separate fresh run of the six development originals exercised the actual
candidate worker before parallel admission. It made eight calls, completed all
six sources (two text and four visual), and recorded zero errors, retries or
uncertain attempts. No labels were opened. Peak sampled process-tree RSS was
2,208,235,520 bytes; minimum available host memory was 4,833,091,584 bytes.
Sampling every 50 ms produced 1,803 samples with no sampler errors.

The probe used a stricter, pilot-only first-provider-error stop. No such error
occurred. Its resource receipt matched the final backend, profile and runtime.
All 83 sealed probe artifacts were independently hash-verified before freezing
the 2,000-source run. Probe prediction-seal SHA-256:
`871d62c983223326bbde7c333fea41e8ab632123a848e0353d1332652691db3a`.

## First 25-original checkpoint

| Family | Completed / selected | Full text coverage | Full image coverage |
| --- | ---: | ---: | ---: |
| Registration | 14 / 897 | 14 | 0 |
| Ad-buy | 3 / 305 | 2 | 1 |
| Receipt | 8 / 798 | 0 | 8 |
| Total | **25 / 2,000** | **16** | **9** |

All 25 made one known model call, produced non-null proposals, passed strict
response and full input-coverage checks, and retained the required review
boundary. Reported usage: 85,686 input and 20,389 output tokens. No provider
errors, unknown attempts or stop reason were recorded. Checkpoint SHA-256:
`5734531c4c08db744c63f9a5d40f5185625de0b5880cc6d3c6f503baa861f511`.
The process then resumed the remaining 1,975 originals with the same protocol.

## Interpretation

This is an operational extraction gate, with no reference answers passed to
the model and no quality scoring yet. Complete input coverage and valid JSON
do not establish correct values. The separate, source-disjoint quality240
comparison will evaluate text against the selective candidate after predictions
are sealed. Its execution and metric plan are frozen before accessing references.
The host also performs application verification during this operational run;
its timings are not unloaded, controlled hardware performance measurements.
