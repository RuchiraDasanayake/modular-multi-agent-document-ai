# Local model decisions — 8 November 2026

Classification: `research_evidence`; action: `keep`. These are sourced trial
candidates, not measured product improvements. No vendor benchmark establishes
our extraction accuracy, evidence quality, review burden or latency. Existing
conference results used different models and remain frozen.

## First measured trials

| Role | Candidate and verified release | License | Native Windows option and download | Decision |
| --- | --- | --- | --- | --- |
| Schema interpretation and structured extraction | `Qwen/Qwen3.5-4B`, 2 March 2026 [official release history](https://github.com/QwenLM/Qwen3.5) | Apache 2.0 | [Ollama `qwen3.5:4b-q4_K_M`](https://ollama.com/library/qwen3.5:4b-q4_K_M), 3.3 GB including projector; observed digest prefix `d8b0f5e9760c` | First fixed local baseline. Explicit quantization avoids selecting another backend variant. |
| Scan, table and prescribed field extraction | `openbmb/MiniCPM-OCR-1.0`, 27 October 2026; SDK 1.0.4, 2 November [official release history](https://github.com/OpenBMB/MiniCPM-OCR) | Apache 2.0 | [Official Ollama `openbmb/minicpm-ocr1.0:q8_0`](https://ollama.com/openbmb/minicpm-ocr1.0:q8_0), 1.7 GB including projector; observed digest prefix `9510e25663e9` | First specialist challenger. Recognition and full document parsing are different deployments. |
| Page transcription with region evidence | `lightonai/LightOnOCR-3-0.8B`, 8 October 2026 [author announcement](https://huggingface.co/blog/lightonai/lightonocr-3) | Apache 2.0 | [Official BF16 checkpoint](https://huggingface.co/lightonai/LightOnOCR-3-0.8B), 1,706,030,528 weight bytes; Transformers/PyTorch CUDA | Next challenger if needed. Supports empty/transcription or `grounding` prompts; arbitrary JSON instructions are out of distribution. |

Names are not memory budgets. MiniCPM's vision projector is additional to its
language model; LightOn's weights are additional to activations and KV cache.
Use one concurrent generation and initially one loaded model on an 8 GB GPU.
Fit and speed must be measured on the actual host.

The [MiniCPM guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/ollama_deploy.md)
requires Ollama >= 0.40.12 and supports Windows. Full-page parsing uses the
`minicpm-ocr` SDK plus PP-DocLayoutV3, then the separate recognition service.
Model-only image recognition does not reproduce that complete pipeline.
The optional DSpark draft must match the same release and is a separate
performance trial. Its published speed uses an RTX 5090, not this host.

## Snapshot identity

Observed through the official Hugging Face model API on 8 November. A repository
revision is not an Ollama manifest digest; record both where applicable.

| Repository | Observed revision |
| --- | --- |
| `Qwen/Qwen3.5-4B` | `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` |
| `openbmb/MiniCPM-OCR-1.0` | `b2890ab4ce9d18c7f75b90966b76a972b6c9ac58` |
| `openbmb/MiniCPM-OCR-1.0-GGUF` | `a1f1e1efea7cb7717f5ab16be514aa4b5fd09435` |
| `lightonai/LightOnOCR-3-0.8B` | `36d8636925327c671bd8e479c517a004f7566bd9` |

MiniCPM's official GGUF Q8 main weights are 811,598,432 bytes and its F16 4x
projector is 901,017,536 bytes: 1,712,615,968 bytes combined, excluding tokenizer,
metadata and optional draft. Hash downloaded files; tags can change.

## Alternatives considered

- [PaddleOCR-VL 1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6):
  28 May 2026, Apache 2.0. The [official GGUF pair](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF)
  totals 1,817,539,616 bytes. Retain as a mature specialist comparator; full-page
  layout parsing needs the pipeline rather than standalone element recognition.
- [Xiaomi-OCR-0](https://huggingface.co/xiaomi-research/Xiaomi-OCR-0):
  30 September 2026, Apache 2.0, 1,746,937,856 BF16 weight bytes. Includes schema
  field extraction. Ollama conversion is explicitly experimental; its own card
  warns that conversion quality and preprocessing alignment need verification.
- [GLM-OCR](https://huggingface.co/zai-org/GLM-OCR): MIT model with Apache 2.0
  layout detector. [Official Ollama Q8](https://ollama.com/library/glm-ocr:q8_0)
  is 1.8 GB including projector. Useful baseline; not a newly released November
  checkpoint. The report was published 11 March 2026.
- [Gemma 4 E2B](https://developers.googleblog.com/bring-state-of-the-art-agentic-skills-to-the-edge-with-gemma-4/):
  2 April 2026, Apache 2.0. E2B denotes effective parameters, not total weight
  size. [Official QAT GGUF](https://huggingface.co/google/gemma-4-E2B-it-qat-q4_0-gguf)
  and projector total 4,336,349,920 bytes. Reserve rather than expanding the first
  trial matrix.
- [MiniCPM-OCR Jev](https://github.com/OpenBMB/MiniCPM-OCR#minicpm-ocr-jev):
  2B OCR correctness assessor released 27 October, Apache 2.0. Candidate for
  deciding which regions need review or comparing parsers. Its score requires
  calibration against our reference data; it cannot certify an extraction.

## Local runtime contract

Use the [native Windows standalone ZIP](https://docs.ollama.com/windows), a
configured model directory on the data drive, `OLLAMA_NO_CLOUD=1` and loopback
binding. The [official FAQ](https://docs.ollama.com/faq) documents model storage,
cloud disabling and concurrency controls. No cloud fallback is authorized.

[Structured output](https://docs.ollama.com/capabilities/structured-outputs)
constrains JSON syntax and supported schema structure. Independently validate
the returned values. For OpenAI chat compatibility use
`reasoning_effort: "none"`; native Ollama uses `think: false` when supported.
Inspect `/api/show` thinking metadata before assuming a model can disable
reasoning. The [compatibility guide](https://docs.ollama.com/api/openai-compatibility)
requires a Modelfile `PARAMETER num_ctx` to set context for that interface.

## Trial and promotion gates

`scripts/check_local_model.py` is a bounded capability and repeatability screen.
Its authored synthetic invoice tests typed JSON, absent values, Unicode and
duplicate rows. An optional operator-provided image checks OCR repeatability;
it has no correctness reference and is not scored for quality. The screen never
loads benchmark labels, downloads models or silently retries requests.

Before a product-quality claim, freeze the development and untouched holdout
sources, prompts, schemas, model digests and scorer. Compare scalar and whole-row
quality, unsupported/failed sources, evidence validity, review work, latency and
memory. Record every attempt. Local API spend is zero; energy, hardware and human
review still have a cost. A passing synthetic screen is not a release sign-off.
