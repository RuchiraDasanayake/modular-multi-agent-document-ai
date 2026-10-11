# ADR-0005 paired structured-output diagnostic: frozen protocol

**Prepared 12 October 2026; inference not run.** The current 2,000-source v8
volume gate owns the CPU/GPU schedule. This runner is an isolated experiment,
not an enabled product extractor. The [decision record](../architecture/ADR-0005-structured-model-output-candidate.md)
explains the integration criterion. The previous
[12-document Qwen pilot](LOCAL_QWEN_ORACLE_SCHEMA_VRDU_TWELVE_PILOT.json) is
historical evidence, not this paired result.

The frozen [October CORD-100 result](../../paper/FINAL_EVIDENCE.md) used
`qwen3.5:9b` via Ollama and pack-defined fields; its static micro F1 was
0.884. That is a different pipeline and metric contract. The available
Qwen3-4B comparison here tests constrained-output compatibility, not the best
local model or automatic schema discovery. This host currently lacks Ollama
and the 9B model blobs. A separately source-locked 9B product-auto pilot is a
candidate after the volume gate if compute permits.

## Frozen materials and isolation

`product_eval/fixtures/adr0005_qwen_twelve_sources.json` pins the six lowest
raw-source SHA256 registration forms and six lowest ad-buy forms within the
creator-hosted VRDU cohort. It pins each source hash, completed v5 OCR sidecar
hash and run ID, and the prompt hash for eleven eligible documents. The twelfth
document exceeds the 24,000-character auto limit and stays in both score
denominators without a model call. Cohort JSONL SHA256:
`98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`.
Gold JSONL SHA256:
`8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
Both files, the PDFs, and OCR sidecars are outside Git at
`E:\DocAI-Benchmarks`. The runner rejects any changed file, missing sidecar,
incomplete v5 run, changed prompt, or output directory inside Git.

The model is local Qwen3-4B Q4_K_M, GGUF SHA256
`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
The installed CUDA 12.4 `llama-server.exe` reports build 11425, commit
`e117148a4`; executable SHA256
`4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306`.
The runner verifies these hashes, the loopback URL, server build and model
path, 12,288 context tokens and one slot before inference. It then makes one
bounded schema-conformance probe using the actual value-envelope generator;
failure stops the run before scored calls.
The probe is an API compatibility check, not proof that every JSON Schema
feature or extraction value is valid.

## Comparison and limits

Both arms receive the same v5 OCR page text, the same oracle field IDs/types,
the same prompt, seed 42 and sampling settings. Gold values, evidence and gold
OCR page text are unavailable to the call. The only intended change is
`response_format`: plain `json_object` versus a minimal `json_schema` envelope
with known field-ID enum, required `value`, bounded array and no extra keys.
Arm order alternates by source index. The same product `parse_values_reply`
and frozen gold scorer judge both arms; separate Pydantic shape checks expose
structure failures without changing candidate values.

One model call per eligible source and arm means at most 22 scored calls plus
one 64-token conformance probe. There are no retries. A 3,000-token response
cap, 12,288-token context and 120,000-token accounting limit apply **per
arm**. The one over-limit source, model errors, context/budget skips,
truncations, malformed replies and unsupported fields stay in the 12-source
gold denominator. Raw replies, candidates, diagnostics and score reports are
written only under a new directory outside Git; `run.json` is the completion
marker. A crash leaves no completion marker and must not be reported as a
completed comparison.

Score exact typed scalar TP/FP/FN, false accepted values, exact linked cells
and complete rows, runtime OCR-quote grounding, response-shape failures,
latency and tokens, with score breakdowns by family. Record the Pydantic
version used for local shape validation. Gold schema F1 is tautological here and must not
be interpreted as automatic schema discovery. OCR text in the v5 sidecars
differs from frozen gold OCR text, so gold-offset evidence validity has the
same limitation as the historical pilot. Local hardware/electricity and human
review costs are not measured by this runner; cost fields remain unknown.

## Deferred execution

After the v8 gate exits, verify inputs without a model call:

```powershell
python -m product_eval.constrained_output_diagnostic `
  --cohort 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl' `
  --gold 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl' `
  --runs-root 'E:\DocAI-Benchmarks\runtime\product_runs' `
  --check
```

Start the pinned server in a separate terminal, using the absolute model
path. It remains bound to loopback and should be stopped after the trial:

```powershell
& 'E:\DocAI-Benchmarks\tools\llama-b11425\bin\llama-server.exe' `
  --model 'E:\DocAI-Benchmarks\models\qwen3-4b-gguf-bc640142\Qwen3-4B-Q4_K_M.gguf' `
  --alias qwen3-4b-q4km-local --host 127.0.0.1 --port 18081 `
  --ctx-size 12288 --n-gpu-layers 99 --parallel 1 --jinja --no-webui
```

Then run the pair once into a **new empty path**:

```powershell
python -m product_eval.constrained_output_diagnostic `
  --cohort 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl' `
  --gold 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl' `
  --runs-root 'E:\DocAI-Benchmarks\runtime\product_runs' `
  --model-file 'E:\DocAI-Benchmarks\models\qwen3-4b-gguf-bc640142\Qwen3-4B-Q4_K_M.gguf' `
  --server-exe 'E:\DocAI-Benchmarks\tools\llama-b11425\bin\llama-server.exe' `
  --model-url 'http://127.0.0.1:18081/v1/chat/completions' `
  --output-dir 'E:\DocAI-Benchmarks\adr0005-paired-output-v1' `
  --run
```

Before interpreting the results, verify both arms have twelve candidates,
the same twelve source hashes and no missing output, then report per-family
scores and the probe result. A lower malformed-output count alone is not a
promotion gate. Value and linked-row correctness must improve without more
false acceptance or unjustified cost. Any product integration is a separate
change followed by the required fresh 2,000-source gate.
