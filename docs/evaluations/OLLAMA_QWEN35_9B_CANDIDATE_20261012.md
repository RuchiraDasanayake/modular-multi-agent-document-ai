# Qwen3.5 9B as a product-auto candidate: readiness record (2026-10-12)

**Decision:** Keep this as a bounded local candidate, not a promoted extractor. The
October paper's CORD-100 static F1 of 0.884 measured extraction with five known
receipt field IDs, PaddleOCR, and the research scorer. It did not measure automatic
schema discovery, linked menu rows, exact source spans, or release after human
review. The current product path has different prompts, parsing, OCR, and scoring.
No 9B weights were downloaded and no 9B inference was run for this record.

## Reuse and reproducibility

The [frozen paper evidence](../../paper/FINAL_EVIDENCE.md) records Ollama 0.35.1,
`qwen3.5:9b` Q4_K_M, temperature 0, top_p 0.8, top_k 20, context 8192,
reasoning off, and JSON-schema-constrained replies. The [reproduction guide](../REPRODUCING_RESULTS.md)
reports about 10 GB of Windows runner host-memory commitment in addition to GPU
memory and one early memory-related failure on the original 16 GB GPU host. The
paper records a tag, not a model manifest or weight hash. Its exact October model
bytes therefore cannot be proven identical to today's registry bytes.
The reproduction guide calls the old tag 9.7B parameters while the current
Ollama page says 8.95B; this is another reason to compare by artifact digest,
not by model name or displayed parameter count.

Current official [Ollama tag](https://ollama.com/library/qwen3.5:9b-q4_K_M)
identifies a 6.6 GB, 8.95B Q4_K_M text model plus a BF16 vision projector and
Apache-2.0 license. A read-only request to the [official registry manifest](https://registry.ollama.ai/v2/library/qwen3.5/manifests/9b-q4_K_M)
on 2026-10-12 yielded manifest SHA-256
`56671c2ab9385f9cfcb404638e32cd62d88e3501d44822208363c010179a3c90`,
model layer `02d45dc1cf451ba2475ac33b301c2dd8f985abe4c182ce04a1f2f5bf0260278d`
(5,629,109,120 bytes), and projector layer
`f836f08f921193f4d6b6a6952dba0a6fb116759d26a757bcb395d570d73976ca`
(921,704,832 bytes). The combined large layers are **6,550,813,952 bytes
(6.10 GiB)**. The upstream [Qwen model card](https://huggingface.co/Qwen/Qwen3.5-9B)
also labels the model Apache-2.0. Tags are mutable; require these hashes at
download time. [Ollama 0.35.1](https://github.com/ollama/ollama/releases/tag/v0.35.1)
is an available upstream release, not presently installed on this host.

The current host has a GeForce RTX 3060 Ti (8,192 MiB VRAM, 1,258 MiB already
used at this check), 23.9 GiB installed RAM (9.8 GiB free), and 15.3 GB free
on E:. The 9B download would consume at least 6.55 GB, leaving about 8.76 GB
on E: before runtime caches and run artifacts. Existing local Qwen3 4B Q4_K_M
GGUF from the [official Qwen repository](https://huggingface.co/Qwen/Qwen3-4B-GGUF)
weighs 2,497,280,256 bytes (2.33 GiB), SHA-256
`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`;
its previous local pilots fit the 8 GB GPU. The 9B model plus projector, KV
cache, and runtime may exceed free VRAM. CPU offload and latency must be
measured before any scaled run; the paper's 16 GB GPU latency cannot be carried
over. Ollama was not found on PATH or in the usual local install locations; the
existing E: Ollama store has `phi3:mini`, not this model.

Ollama's current [structured-output API](https://docs.ollama.com/capabilities/structured-outputs)
accepts a JSON Schema, and its [OpenAI-compatible API](https://docs.ollama.com/api/openai-compatibility)
offers `/v1/chat/completions`. Product-auto can point its existing adapter to
`http://localhost:11434/v1` with `--model qwen3.5:9b-q4_K_M`; loopback uses a
local placeholder key. The current adapter sends JSON instructions in the
prompt but **does not send `response_format` or Ollama `format`**, so merely
changing the model does not reproduce the paper's constrained-output setting.
Verify version-specific compatibility before a constrained-output comparison.

## What the paper score actually tested

- The CORD-100 static result was precision 0.907, recall 0.862, F1 0.884,
  59/100 perfect, 0.83 validation pass, and mean 9.0 s/document, on a
  50-document development and 50-document holdout drawn from CORD validation.
  It is a historical research result, not a product acceptance threshold.
- The executed benchmark packs use `single_run_per_condition` and a shared
  five-field receipt configuration for all documents. The pack builder also
  stores per-case fields derived from expected values, but the batch runner
  passes the shared field list, so the frozen batch did **not** receive a
  per-document field-presence oracle. It did receive a fixed global schema.
- The research scorer normalizes numerics and permits fuzzy text matches;
  product evaluation uses strict typed values, explicit schema proposals,
  exact evidence spans, and separate linked-row scoring. The paper notes
  development prompt/policy exposure and routing by case-ID prefix; static
  routing was off, but the task was still known-schema CORD.
- Current CORD v2 development receipts below come from the creator's **test**
  parquet, not the October paper's validation corpus. They form a separate
  diagnostic and cannot reproduce its reported score.

## Locked 12-source development pilot, to run only after resource approval

Selection was fixed without inspecting gold: the three lowest source SHA-256
values in each VRDU family from the [v5 2,000-source cohort](VRDU_2000_NO_MODEL_V5.md),
plus the six lowest in the [CORD development cohort](CORD_SECONDARY_SLICE.md).
The cohort JSONL hashes are respectively
`98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`
and `48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a`.
These 12 original source bytes were rehashed and match the frozen rows. All
original filenames are distinct, and all 12 saved no-model sidecars have text,
matching source hashes, and completed run markers. Selection and evaluation
must retain every item below, including sparse OCR and any model failures.

| Family | Source SHA-256 | Product doc ID | Saved OCR chars |
| --- | --- | --- | ---: |
| registration | `00159e1d37fc2665b6ffaf6223ff69187e51decdb00e0fe4cd501643b069c5d5` | `2e8f9a5f9657c1f854527313071dc9d3` | 3,095 |
| registration | `004e5f2397d3f69bcb2be14dc935df72caf8387d9958aa57b80e0294566307d7` | `aea6ed014a29facb39de15eaaef1a963` | 4,818 |
| registration | `008a35460c861cc80105e4b795cc774ad6766670894108e3cfb0900e99eaba03` | `1a9efac5c954664cf9992d1ab452fb5b` | 3,876 |
| ad-buy | `00af9ec9594520a61f852e0ccfd93441f068b38fc120625a0571e04941eb1060` | `c960338957dfa60346aac9863edd4c27` | 7,885 |
| ad-buy | `00d6bafddf012448e9ada179b9cebcf52a15eb6fb9e7d8c6549cf773a7ef56ff` | `e2e3a1f8d204396dbd270eb9392e5454` | 2,605 |
| ad-buy | `0112d54415d968cd438207ddbd423fb64b636354f29c72f0c6defe3cef14729a` | `1bf0c61dbd517c9d5c1d2684c2788497` | 1,750 |
| receipt | `0000fb66d5cf4154d84d87f00c363cbdb62f805418aedbaca6e6fbc7cb8c32e8` | `a198e580042974f6ad76724799e68913` | 1,311 |
| receipt | `027f8ee65ccc34bad7908f1b5624b5128014e3a799499053fbf0d7f95fdfae16` | `21e713a7daf2fc3fb64be694d10b27d9` | 116 |
| receipt | `0411c4d9beb9be65165fdb70c2b60f8bbf9035cc9661be2b8d4c73bbfcff7972` | `c1712f6344d2ee731ba6459a5d3e36dd` | 84 |
| receipt | `07ae62e2d56b156014acc0f4e0b701b8d0890b36b4a7a934852429418f743d7b` | `042b397e44973f3660933b06b5123000` | 79 |
| receipt | `0b63b666b54ea615d1d05733ee2c6fc24f20e1a6c77b333872fa80fff28b2c48` | `6e1b9cb18ed19c2ef2d3fccd1736a8aa` | 116 |
| receipt | `0f6a25eb66f3aac732d270cb3bfc6e89c4d435eccd9a343d380b1c7799253886` | `16c34d5194f931e1b89b41b16f625067` | 1,429 |

The CORD split already segregates 40 reserved receipts; this pilot uses only
the 60 development pool. Four selected receipt OCR sidecars have fewer than
120 characters. A text-only model may be unable to recover values missing
from those transcripts. Preserve them as failures and report OCR text coverage
separately; a vision comparison is a distinct experiment.

After the active gate and CORD crop OCR work finish, first verify the pinned
Ollama manifest and disk/headroom, then cold-load one synthetic text request
while measuring peak GPU/host memory and token latency. If stable, stage the
12 original files under their original basenames, run one no-model baseline
and one opt-in product-auto model run with the same pinned OCR and parser,
maximum two model calls/document (24 total), no retries, a fixed output-token
cap, and no prompt changes between documents. Keep raw artifacts outside Git.
Use product_eval's strict schema/value and linked-row scorers and report
12/12 statuses, exact grounding, proposed and accepted values, JSON validity,
token and wall time, GPU/host memory, review load, and local compute cost
assumptions. Compare against the same-source no-model baseline; do not compare
its strict F1 directly with the October paper's 0.884. The saved OCR sidecars
can support a later model-only ablation, but product-auto currently redoes OCR.
