# PP-StructureV3 table parser: fixed 12-document follow-up

**Prepared 12 October 2026.** No model weights were downloaded, no Paddle
dependencies were installed, and no Paddle CPU/GPU inference was run for this
protocol. The pilot waits until the CORD 60-document diagnostic and the current
2,000-document product gate finish. The present parser baseline remains in force.

## Decision

Run **PP-StructureV3, CPU, one PDF at a time** as the first specialist. It is a
better first test for this failure mode than a page VLM because its documented
result has both `pred_html` and `cell_box_list`, alongside OCR text and boxes.
Those outputs at least permit a later cell-to-source alignment test. The
PaddleOCR-VL 1.6 pipeline emits table content and layout-region boxes, but its
documented output does not by itself prove per-HTML-cell geometry. This is an
evidence *opportunity*, not a claim that PP-StructureV3 already produces
correctly mapped cells. [PP-StructureV3 output](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md),
[PaddleOCR-VL output](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html).

The same [frozen public ad-buy slice](VRDU_ADBUY12_TABLE_PARSER_COMPARISON_20261012.md)
has 12 unique source PDFs and 219 linked gold rows. Docling TableFormer
reconstructed 3 exact complete rows; pdfplumber reconstructed 0 with `lines`
and 4 with `text`. That is evidence of a table-linking problem, not of superior
end-to-end extraction by any candidate. The specialist only advances if it
improves complete linked rows with a tolerable wall-time and resource cost.

## Hardware and upstream facts

The local read-only check reported an RTX 3060 Ti, 8,192 MiB VRAM, 6,665 MiB
free at the time, driver 610.88, compute capability 8.6, and Python 3.13.8.
These values do not prove any Paddle GPU configuration fits. The
[official PP-StructureV3 benchmark](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-StructureV3/PP-StructureV3.en.md)
reports 13.97 GB peak device memory for the default T4 profile. A different
V100 configuration with mobile OCR and smaller formula model still reached
8.4 GB. Its CPU `noformula` profile peaked at 15.5–17.7 GB host RAM on Xeon
servers; the reported lightweight CPU profile used 12.96–14.0 GB and took
3.74–4.36 seconds per image. These are upstream measurements on other
hardware and configurations, not local latency or memory forecasts. The
local CPU pilot must record its own process-tree RSS and time.

The [official PP-StructureV3 guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md)
supports CPU inference, disabling unrelated formula/chart/seal/preprocessing
modules, passing an exported PaddleX config with local `model_dir` paths, and
saving structured JSON. The [PaddleX release/3.7 default config](https://raw.githubusercontent.com/PaddlePaddle/PaddleX/release/3.7/paddlex/configs/pipelines/PP-StructureV3.yaml)
shows the full module graph, including layout, region, OCR and table modules.
This protocol keeps these active and disables formula, chart, seal and document
preprocessing. Its fixed runner uses `paddleocr==3.7.0`, `paddlepaddle==3.2.1`,
`pypdfium2==5.14.0`, `lxml==6.1.1`, `PyYAML==6.0.3` and `psutil==7.2.2` in a
separate environment. Package availability and integration with that exact
Paddle/PaddleX combination remain untested locally. The chosen PaddleX
transitive version is captured in the model lock and checked before inference.

PaddleOCR code is [Apache-2.0](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE).
The [official PaddleOCR-VL 1.6 safetensors](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6)
and [GGUF](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF/tree/main)
model pages also list Apache-2.0. This does **not** settle rights for every
PP-StructureV3 component archive; verify each selected weight's source,
license and notice before redistribution. PaddleOCR-VL's [official guide](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
supports a full layout-plus-VLM pipeline with a llama.cpp server on x64 CPU or
NVIDIA GPU, but cautions that serving the 0.9B VLM alone is not the full
pipeline. Its official GGUF pair totals about 1.82 GB of files; loaded memory
and output quality on this 8 GB card are unmeasured. It remains the second
bounded comparator if PP-StructureV3 fails or leaves material rows unresolved.

## Frozen evaluation contract

The runner is [`product_eval/ppstructure_table_diagnostic.py`](../../product_eval/ppstructure_table_diagnostic.py)
and reuses the committed 12-PDF selection, cohort/source SHA-256 verification,
gold SHA-256, and exact one-to-one row scorer from the Docling diagnostic. A
full twelve-document score must retain **219 gold rows**, including failed,
timed-out, malformed and no-table documents. Raw OCR/HTML and rendered pages
stay outside Git. Gold values are read only after conversions finish.

Before inference, create one PaddleX YAML with **absolute local `model_dir`**
paths for every active layout, region, OCR and table model. Set the fixed
table-only flags in the runner. `--make-lock` snapshots SHA-256 and size for
every file in those active model directories and the config itself, then
refuses to overwrite the lock. `--check` verifies source bytes, package pins,
model files and config. The runner rejects a missing active local model path,
so an implicit download is not part of the accepted evaluation. For a fully
offline certification, also block the pilot environment's network egress;
PaddleX's own remote fallback behavior has not been exercised here. Keep the
lock, config, weights and all raw results outside the repository.

```powershell
python -m product_eval.ppstructure_table_diagnostic --make-lock --config E:\path\PP-StructureV3-local.yaml --model-lock E:\path\ppstructure-model-lock.json
python -m product_eval.ppstructure_table_diagnostic --check --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --corpus-root E:\DocAI-Benchmarks\vrdu-extracted\vrdu-04a4df7ac5cc694e51c48115c03fe428f0e240cc --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --output-dir E:\path\ppstructure-ad12 --config E:\path\PP-StructureV3-local.yaml --model-lock E:\path\ppstructure-model-lock.json
python -m product_eval.ppstructure_table_diagnostic --run --cohort E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\cohort.jsonl --corpus-root E:\DocAI-Benchmarks\vrdu-extracted\vrdu-04a4df7ac5cc694e51c48115c03fe428f0e240cc --gold E:\DocAI-Benchmarks\vrdu-cohort-04a4df7\gold.jsonl --output-dir E:\path\ppstructure-ad12 --config E:\path\PP-StructureV3-local.yaml --model-lock E:\path\ppstructure-model-lock.json
```

The run uses PDFium at 144 DPI, at most 20 pages and 2 MB source PDF per
document, 25 million pixels per rendered page, one CPU worker and a 360-second
document deadline. Each child is killed on timeout. It records conversion
status, elapsed time, peak sampled process-tree RSS, page image hashes,
raw page JSON hashes, and package/model/config hashes. A different rendering
resolution from another parser can affect its accuracy; paired source IDs and
the same row scorer make the outcome comparable as a pipeline choice, not a
controlled neural model ablation.

The child is also stopped with `resource_limit` when sampled process-tree RSS
exceeds 18 GiB or available host memory drops below 2 GiB. Sampling every
250 ms cannot prevent every transient allocation peak. A resource-limited
document remains in the 12-document failure denominator.

The first gate is **complete exact linked rows** and exact one-to-one cells on
this 219-row slice. Also inspect scan versus native PDF failures, extra HTML
rows, field/column shifts, source page/table boxes, malformed output,
timeouts, process RSS and wall time. The current gold has no adjudicated page
or cell boxes. Count `cell_box_list` entries for inspection, but do not
describe them as verified evidence or accept values automatically until an
independent alignment/grounding check is built and measured. Any product
adapter then requires a larger source-locked evaluation, the required
2,000-distinct-document gate, and release policy review.
