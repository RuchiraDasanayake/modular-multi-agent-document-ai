# PP-StructureV3 CPU preparation for the fixed ad-buy table diagnostic

**Prepared 12 October 2026. No model weights or heavy dependencies have been downloaded or installed; no inference has run.** Run the setup and pilot only after the CORD 60-document diagnostic and v8 2,000-document gate finish and the evaluation owner authorizes it. The [fixed comparison protocol](PPSTRUCTURE_V3_ADBUY12_PROTOCOL_20261012.md) defines the 12 public PDFs, 219 gold rows, failure denominator, scorer, and guard.

## Source and configuration lock

The committed [PaddleX v3.7.0 default YAML](../../product_eval/fixtures/PP-StructureV3-v3.7.0.yaml) is copied byte-for-byte from the [official tag](https://raw.githubusercontent.com/PaddlePaddle/PaddleX/v3.7.0/paddlex/configs/pipelines/PP-StructureV3.yaml), SHA-256 `79aa30099f2b910457fd6855e06b9190a1bb5d985f3144c9185f3c0e90616c61`. Its default `use_formula_recognition: True` **must become `False`** for this fixed CPU profile. Document preprocessing, seal, chart, and formula modules are off; region, layout, OCR, and table modules remain on. The [offline config builder](../../product_eval/prepare_ppstructure_config.py) makes exactly those changes, fills all active `model_dir` fields, verifies the source-pinned local model files, and refuses to overwrite an existing config. It never accesses the network.

The [model manifest](../../product_eval/fixtures/ppstructure_v3_3.7.0_models.json) records each official `PaddlePaddle` Hugging Face repository's full commit, six-file inventory, byte count, and Git blob SHA-1 or LFS SHA-256. A pinned revision is the download source; the builder checks the downloaded bytes. The diagnostic then generates its separate SHA-256 lock over *every* local model file, YAML, and its pinned package set before inference. The official model cards report Apache-2.0. Respect their license/notice files if redistributing the weights. [PaddleX license](https://github.com/PaddlePaddle/PaddleX/blob/v3.7.0/LICENSE), [PaddleOCR license](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE), [Hugging Face revision downloads](https://huggingface.co/docs/huggingface_hub/guides/download).

| Active unique model | Official repository revision | Repo bytes |
| --- | --- | ---: |
| [`PP-DocLayout_plus-L`](https://huggingface.co/PaddlePaddle/PP-DocLayout_plus-L/tree/aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d) | `aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d` | 130,406,207 |
| [`PP-DocBlockLayout`](https://huggingface.co/PaddlePaddle/PP-DocBlockLayout/tree/f270657da59d956ab69ffc2c4722fe1f557bf17b) | `f270657da59d956ab69ffc2c4722fe1f557bf17b` | 129,934,982 |
| [`PP-OCRv5_server_det`](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_det/tree/ca867c897ecbca8873081573a802ad70d499cb94) | `ca867c897ecbca8873081573a802ad70d499cb94` | 88,356,628 |
| [`PP-LCNet_x1_0_textline_ori`](https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_textline_ori/tree/cd237a44b0e359d4fe38310a416203cf7403faa5) | `cd237a44b0e359d4fe38310a416203cf7403faa5` | 6,856,668 |
| [`PP-OCRv5_server_rec`](https://huggingface.co/PaddlePaddle/PP-OCRv5_server_rec/tree/b26c3587fda8da3c8ec0ce357214b4d661ff1558) | `b26c3587fda8da3c8ec0ce357214b4d661ff1558` | 85,233,386 |
| [`PP-LCNet_x1_0_table_cls`](https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_table_cls/tree/2fa6323e7dab88fa883081db1460995f46af2922) | `2fa6323e7dab88fa883081db1460995f46af2922` | 6,864,864 |
| [`SLANeXt_wired`](https://huggingface.co/PaddlePaddle/SLANeXt_wired/tree/763069fcda6a065f2171753205a32bf899a88d15) | `763069fcda6a065f2171753205a32bf899a88d15` | 365,752,316 |
| [`SLANet_plus`](https://huggingface.co/PaddlePaddle/SLANet_plus/tree/bae6e5f8c3c4e7da0c0b7639fdf3228fe76184e2) | `bae6e5f8c3c4e7da0c0b7639fdf3228fe76184e2` | 8,006,029 |
| [`RT-DETR-L_wired_table_cell_det`](https://huggingface.co/PaddlePaddle/RT-DETR-L_wired_table_cell_det/tree/e2bd53c06b3a815d86acbf5c6779dada58819cfe) | `e2bd53c06b3a815d86acbf5c6779dada58819cfe` | 129,945,728 |
| [`RT-DETR-L_wireless_table_cell_det`](https://huggingface.co/PaddlePaddle/RT-DETR-L_wireless_table_cell_det/tree/25ca86356a601c877476bb0dcc5fd09153d9d64d) | `25ca86356a601c877476bb0dcc5fd09153d9d64d` | 129,946,466 |
| [`PP-LCNet_x1_0_doc_ori`](https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_doc_ori/tree/d3b95a6dff5fe8a94f2748e12b61cb26818a0df8) | `d3b95a6dff5fe8a94f2748e12b61cb26818a0df8` | 6,870,359 |

**Total reported repository files:** 1,088,173,633 bytes (1.013 GiB), before package wheels, caches, and output. `PP-OCRv5_server_det`, `PP-OCRv5_server_rec`, and `PP-LCNet_x1_0_textline_ori` occur twice in the YAML but require only one local copy each. The table-orientation model `PP-LCNet_x1_0_doc_ori` remains active even though the outer document-preprocessor pipeline is disabled. Do not substitute `SLANeXt_wireless` for the `SLANet_plus` named by this pinned template. Avoid the generic model download links in the live guide: at least one current table-classifier link resolves to a different archive than its row label. [Official PP-StructureV3 guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PP-StructureV3.en.md).

## Python and host capacity

`py -3.11` is present. PyPI has a [PaddlePaddle 3.2.1](https://pypi.org/project/paddlepaddle/3.2.1/) `cp311-cp311-win_amd64` CPU wheel (101,697,653 bytes). [PaddleOCR 3.7.0](https://pypi.org/project/paddleocr/3.7.0/) requires `paddlex[ocr-core]>=3.7,<3.8`; [PaddleX 3.7.0](https://pypi.org/project/paddlex/3.7.0/) supports Python >=3.8. The pinned pypdfium2, lxml, PyYAML, and psutil releases have Windows x64 wheels compatible with Python 3.11. These metadata checks do **not** establish that the full transitive install or runtime works on this host; verify in an isolated environment only after the gate. The official [Windows installation guide](https://www.paddlepaddle.org.cn/documentation/docs/install/pip/windows-pip_en.html) lists x64 Python 3.9–3.13 support.

Read-only host check during v8: E: free **15,325,011,968 bytes (14.27 GiB)**; RAM total **25,675,464,704 bytes (23.91 GiB)** and available **10,476,638,208 bytes (9.76 GiB)**. The [official benchmark](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-StructureV3/PP-StructureV3.en.md) reports **15.5–17.7 GB** peak CPU RAM for a no-formula configuration on Xeon hosts. Those are upstream figures, not a local forecast. The diagnostic child is killed above **18 GiB process-tree RSS** or below **2 GiB available host memory**.

**Go/no-go:** no CPU inference while v8 is running or while available RAM is under 20 GiB. After the gate, recheck capacity. A single-document smoke is reasonable if available RAM is at least **21 GiB**, E: has at least **5 GiB free after setup**, and the 18/2 GiB guard remains enabled. Run all 12 only if the smoke completes with process-tree peak below **16 GiB** and minimum host-available memory above **3 GiB**. If these conditions fail, use a larger-memory CPU host or redesign a separately locked lightweight profile; do not loosen the guard to force a result.

## Reproducible setup after the gate

These commands are a preparation recipe, **not actions performed in this session**. Run them in PowerShell from the repository root only after authorization. Keep the environment, models, config, lock, and raw outputs outside Git. The commands download the 11 model repos at the exact revisions in the manifest; no source PDF or private document is sent to Hugging Face. [Hub `snapshot_download` revision/local_dir behavior](https://huggingface.co/docs/huggingface_hub/guides/download).

```powershell
$work = 'E:\DocAI-Benchmarks\ppstructure-v3-3.7.0'
$venv = Join-Path $work 'venv'
$models = Join-Path $work 'models'
py -3.11 -m venv $venv
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --no-cache-dir --only-binary=:all: paddlepaddle==3.2.1
& $python -m pip install --no-cache-dir paddleocr==3.7.0 'paddlex[ocr-core]==3.7.0' pypdfium2==5.14.0 lxml==6.1.1 PyYAML==6.0.3 psutil==7.2.2 huggingface-hub
& $python -m pip check

$manifest = Get-Content 'product_eval\fixtures\ppstructure_v3_3.7.0_models.json' -Raw | ConvertFrom-Json
$hf = Join-Path $venv 'Scripts\hf.exe'
foreach ($model in $manifest.models) {
    $localDir = Join-Path $models $model.model_name
    & $hf download $model.repo_id --revision $model.revision --local-dir $localDir
    if ($LASTEXITCODE -ne 0) { throw "Model download failed: $($model.model_name)" }
}
$config = Join-Path $work 'PP-StructureV3-local.yaml'
& $python -m product_eval.prepare_ppstructure_config --model-root $models --output $config
$lock = Join-Path $work 'ppstructure-model-lock.json'
& $python -m product_eval.ppstructure_table_diagnostic --make-lock --config $config --model-lock $lock
```

The config builder hashes all six pinned files for every model and rejects missing/mismatched weights and symlinks. The runner's `--check` further verifies source files, packages, local config, and model lock. `HF_HUB_OFFLINE=1` alone is insufficient proof of no network egress from all PaddleX download backends; isolate or block outbound network for the smoke/run after models are local. Use the exact [protocol commands](PPSTRUCTURE_V3_ADBUY12_PROTOCOL_20261012.md) for `--check` and `--run`.
