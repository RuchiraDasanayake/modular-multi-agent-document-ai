# Docling Graph v1.9.1 schema-induction pilot

**Protocol frozen 12 October 2026.** This is a small development feasibility
test of an established schema-induction package. It does not enable a product
extractor, measure value extraction, or revise the accepted paper. The 2,000
distinct-document VRDU gate and 60-receipt CORD no-model run are separate
baselines. This trial uses no ICORE calls or private documents.

## Why this package and exact API

[Docling Graph v1.9.1](https://github.com/docling-project/docling-graph/tree/v1.9.1)
at Git commit `59f40ca2e20f7cdbc8898fcee733fcba947ab762` is MIT licensed.
Its [pinned generator guide](https://github.com/docling-project/docling-graph/blob/v1.9.1/docs/usage/cli/template-command.md)
documents `induce_spec_from_documents`, `DocumentContent`, a provider-injected
`llm_call_fn`, and the `one-shot` strategy. The [pinned induction code](https://github.com/docling-project/docling-graph/blob/v1.9.1/docling_graph/templategen/induce/documents.py)
calls the injected function with `prompt`, `schema_json`, and `context` and
retries a failed pass once. The returned [TemplateSpec](https://github.com/docling-project/docling-graph/blob/v1.9.1/docling_graph/templategen/spec.py)
has root, models, typed fields, list flags, edges, and evidence. The package
merges examples and applies deterministic evidence gates, then renders Python
from a validated SPEC. No model-generated code is executed here.

`product_eval/graph_schema_diagnostic.py` passes existing completed OCR text
as `DocumentContent`. Thus it tests Graph's schema induction and reuse over
the **current OCR surface**, without silently changing PDF/image conversion.
The Graph source is imported only from the verified tag checkout outside this
repo; existing isolated Docling 2.137.0 Python environment imports v1.9.1.
No Graph, Docling, or model dependency is added to the product runtime.

## Frozen materials and leakage boundary

The frozen [selection lock](../../product_eval/fixtures/docling_graph_v1_dev_sources.json)
contains 12 distinct raw source hashes and completed product OCR sidecar
hashes: four VRDU registration forms, four VRDU ad-buy forms, and four CORD
v2 **development** receipts. Each family has the first two source-hash ranked
documents as examples and the next two as scored documents. VRDU selection
comes from the earlier independently source-hash-selected 12-document lock.
CORD selection takes the first four source hashes among the 60 development
receipts whose existing Tesseract OCR text has at least 200 characters. This
favors OCR-readable receipts; all 40 reserved receipts are excluded. The lock
SHA256 is `61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047`.

Full VRDU cohort/gold SHA256s are respectively
`98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`
and `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`.
CORD **development** cohort/gold SHA256s are
`48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a`
and `84a097116eaad75fb66265447d1b831f5a2ffa98792e10e9ad7edb517cb8e318`.
The full 100-receipt hashes differ; the runner rejects those files here.
The `--check` path verifies all four file hashes, every selected raw source,
each OCR sidecar and the Graph Git checkout with **zero model calls**.

The induction function receives only OCR text and a synthetic `doc_id` name.
Gold is loaded only **after** all family and per-document induction completes;
no gold field names, types, values, evidence, or example labels are sent to
the local model. The model's request/response trace and raw SPEC/template
artifacts stay in a new directory outside Git. Output includes a completion
`run.json`; an interrupted run has no completed report. A failed induction
arm is retained as an empty SPEC in the six-source scoring denominator.

## Comparison and scoring

For each family, Graph induces one reusable SPEC from its two example
documents. It independently induces a SPEC for each of the two scored
documents, then the same two scored documents are compared under the reused
and per-document SPECs. This yields six scored sources × two arms. A reusable
template has **no scored-document model calls**. Source hashes are disjoint
between example and scored documents, although this small development test
does not establish vendor, layout, pretraining, or visual-cluster independence.

The [predeclared alias ontology](../../product_eval/fixtures/graph_schema_aliases_v1.json)
SHA256 `24950fd476469d5a433ec3ef423d005eba8ecb703e730b44a8f7f538e306bd03`
was written from creator VRDU entity definitions and the published CORD
positive mapping before any Graph output was inspected. The scorer reports
both exact field-ID matches and this fixed conservative alias mapping. It
never uses an LLM judge. Raw SPECs and generated Python templates are retained
outside Git for human adjudication of unmatched terms and parent-child
meaning; that adjudication cannot retroactively alter this frozen score.

For VRDU, count matched, missed and extra root-reachable leaf fields against
the creator's **narrow annotation ontology**; report reference-ontology
precision/recall/F1. An extra field is out of scope, not proved hallucinated.
For CORD, the eight mapped labels are **positive-only**; report recall for
fields present in each scored receipt and leave precision/F1 undefined. For
both, report raw-string type compatibility, the analyst-declared semantic
type compatibility, scalar versus scalar-list versus repeated-object shape,
and pairwise linked-field co-membership in the **same repeated object**.
An `item_name[]` and `item_price[]` in separate arrays do not form a linked
row. No extracted values, source quotes, row values, or business costs are
scored by this pilot. The derived semantics are not official VRDU/CORD types.

## Local model, budget, and resources

The local model is the existing Qwen3-4B Q4_K_M GGUF, SHA256
`7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`
(2,497,280,256 bytes). The CUDA 12.4 `llama-server.exe` is build 11425,
SHA256 `4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306`.
The runner requires the exact model path, build, a one-slot 12,288-token
server, and loopback HTTP. Graph's one-shot strategy is paired with
`response_format=json_object`; source-locked Graph code warns against using
grammar-constrained decoding with this strategy on small local models.

There are 12 expected one-shot calls (six example units in three family
SPECs, six individual scored units). Graph can retry a failed unit once;
the wrapper hard-caps actual HTTP completions at **24**. Every call has a
3,072-token output cap and 120-second timeout. The actual server chat template
is tokenized via `/apply-template` and `/tokenize`; a prompt above 8,960 tokens
is rejected before inference, leaving 256 tokens of context slack. Source
sampling is capped at 6,000 characters per unit, with at most one window.
Total accounted model tokens are hard-capped at 160,000, including a full
3,072-token reserve for missing usage reports. Thus the worst permitted output
is 73,728 tokens and timeout sum 48 minutes; these are caps, not predictions.
No provider spend occurs. Electricity, amortized GPU and reviewer cost are
unknown. Host free RAM, Python RSS and GPU occupancy are sampled every 2 s
during induction; occupancy is host-wide, not an exact model-process peak.

The local GPU is an RTX 3060 Ti with 8,192 MiB total and roughly 6,991 MiB
free before loading this model. The weight file alone uses about 2.5 GB of
disk; KV cache and compute buffers make actual VRAM higher, so the server
must load and expose `/props` before the run. An OOM or load failure ends the
trial rather than falling back to an API. The Graph Python environment has
Docling 2.137.0, Pydantic 2.14.0, networkx 3.6.1 and psutil 7.2.2. Its
dependency set is experimental; no claim is made that v1.9.1 will be
production-compatible or faster than a simple typed schema route.

## Reproduce after the GPU window is free

From the repository root, with public assets already staged:

```powershell
$graphPython = 'E:\DocAI-Benchmarks\tools\docling-2.137-venv\Scripts\python.exe'
$args = @(
  '--vrdu-cohort', 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl',
  '--vrdu-gold', 'E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl',
  '--cord-cohort', 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\cohort_development.jsonl',
  '--cord-gold', 'E:\DocAI-Benchmarks\cord-v2-test-100-7f0115a\gold_development.jsonl',
  '--runs-root', 'E:\DocAI-Benchmarks\runtime\product_runs',
  '--graph-source', 'E:\DocAI-Benchmarks\tools\docling-graph-v1.9.1-src'
)
& $graphPython -m product_eval.graph_schema_diagnostic @args --check
```

Start one pinned llama.cpp server bound to loopback, with no other GPU model
pilot running. Use a hidden background window when launching from automation:

```powershell
$server = Start-Process -FilePath 'E:\DocAI-Benchmarks\tools\llama-b11425\bin\llama-server.exe' `
  -ArgumentList @('--model', 'E:\DocAI-Benchmarks\models\qwen3-4b-gguf-bc640142\Qwen3-4B-Q4_K_M.gguf',
                  '--alias', 'qwen3-4b-q4km-local', '--host', '127.0.0.1', '--port', '18081',
                  '--ctx-size', '12288', '--n-gpu-layers', '99', '--parallel', '1', '--jinja', '--no-webui') `
  -PassThru -WindowStyle Hidden
```

Then run **once** into a new output directory outside Git:

```powershell
& $graphPython -m product_eval.graph_schema_diagnostic @args `
  --model-file 'E:\DocAI-Benchmarks\models\qwen3-4b-gguf-bc640142\Qwen3-4B-Q4_K_M.gguf' `
  --server-exe 'E:\DocAI-Benchmarks\tools\llama-b11425\bin\llama-server.exe' `
  --model-url 'http://127.0.0.1:18081/v1/chat/completions' `
  --output-dir 'E:\DocAI-Benchmarks\docling-graph-schema-dev-v1' --run
Stop-Process -Id $server.Id
```

Inspect `run.json`, all nine induction `outcomes`, six scored IDs under both arms/modes,
the 24-call cap, token accounting, raw `spec.json`/`template.py`, failures in
`calls.jsonl`, and `resource_samples.jsonl`. If schema meaning and repeated
grouping fail, do not integrate Graph merely because it generates valid code.
If it looks promising, expand to a larger diverse source-disjoint development
set and a reserved holdout, then challenge actual values/evidence and run a
fresh ≥2,000 distinct-document execution gate **after** a product change.
