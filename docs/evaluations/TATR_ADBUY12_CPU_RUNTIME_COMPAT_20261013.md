# TATR ad-buy 12: source-free CPU runtime compatibility

**Status: synthetic CPU compatibility PASS; first-PDF inference NO-GO.** This work opened no selected PDF, gold label, or product extractor. It makes no parser accuracy claim and does not change the frozen 219-row denominator or the separate 2,000-source product gate. The owning surface is `product_eval` research evidence; the action is to keep a bounded, reproducible compatibility check outside the product path.

## Asset and rights provenance

[`tatr_cpu_runtime_receipt.py`](../../product_eval/tatr_cpu_runtime_receipt.py) independently rehashed all 14 files in `I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage` against the hardcoded asset preflight, including the safetensors, configs, processor configs, three model cards, Microsoft MIT notice, inference source and postprocessor source. Detection remained **115,317,516 bytes**, SHA-256 `8f1aa73170102c038d40155e2734b343bf07e0fe12594228a8590943b01dccf7`; structure remained **115,437,156 bytes**, SHA-256 `9df416575a3a36ebd0129342d4f597f14d6e5170268f3d52d28584ab4466a501`. The pinned [detection card](https://huggingface.co/microsoft/table-transformer-detection/blob/2357cbe2b5a5d1c03e54f32764f06058933b65ab/README.md), [structure card](https://huggingface.co/microsoft/table-transformer-structure-recognition-v1.1-all/blob/7587a7ef111d9dcbf8ac695f1376ab7014340a0c/README.md), author's card and [Microsoft source license](https://github.com/microsoft/table-transformer/blob/16d124f616109746b7785f03085100f1f6247575/LICENSE) declare MIT. The exact local source notice SHA-256 was `c2cfccb812fe482101a8f04597dfc5a9991a6b2748266c47ac91b6a5aae15383`; the inference and postprocessor source hashes remain those in the [asset-only receipt](TATR_ADBUY12_ASSET_AND_SOURCE_FREE_PREP_20261013.md).

The dedicated Python 3.13 environment is `I:\DocAI-Benchmarks\tatr-cpu-runtime-v1`. It uses `torch 2.10.0+cpu`, `torchvision 0.25.0+cpu`, `timm 1.0.30`, `transformers 4.57.6`, `safetensors 0.7.0`, `numpy 2.4.6`, `Pillow 12.1.0`, `pypdfium2 5.14.0` and `psutil 6.0.0`. The [committed lock](../../product_eval/fixtures/tatr_cpu_runtime_lock_v1.json), SHA-256 `56cb1244518b2ad2013574901c7dac7cea69e1fe0061e81cbfdcdac5f837417b`, lists **all 31 installed distributions**, versions, raw installed wheel `RECORD` hashes, license metadata, and **131 bundled notice files** with their hashes. The check validated **19,489 files** against `RECORD` hashes, hashed the bytes and paths of **8,887** generated `.pyc` files into per-package digests, and inventoried all **28,389** files in `site-packages` with zero unowned files. It rejects duplicate ownership across distributions. The official `torchvision` install has **201** same-file forward/backslash `RECORD` aliases; these alone are allowed, and its wheel payload is independently verified below. The receipt captures the exact installed bytes at audit time; it does not attest to the host Python executable or system DLLs.

The PyTorch CPU `torchvision` wheel left **200 payload files** without `RECORD` hashes. The check compared all **200 installed wheel members** byte-for-byte against the downloaded wheel, SHA-256 `783c8fc580bbfc159bff52f4f72cdd538e42b32956e70dffa42b940db114e151`, matching the [PyTorch CPU wheel index](https://download.pytorch.org/whl/cpu/torchvision/). The `tokenizers 0.22.2` wheel had no bundled license file. Its [version-matched PyPI source archive](https://pypi.org/project/tokenizers/0.22.2/), SHA-256 `473b83b915e547aa366d1eee11806deaf419e17be16310ac0a14077f1e28f917`, supplied `tokenizers/LICENSE` (Apache 2.0), SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`. `pypdfium2` contributed 18 bundled license/third-party notice files. This seals an installed-package notice inventory for this environment; redistribution obligations for a packaged product still need a separate review.

## Synthetic CPU measurement

The check set Hugging Face and Transformers offline flags, disabled remote code, required local safetensors, used a generated RGB grid, and never read a document. Both models ran on **PyTorch CPU eager**, with CUDA unavailable and four CPU threads. `use_pretrained_backbone=False` prevented an extra ResNet download; every required model weight loaded from the pinned safetensors. Detection had zero missing/mismatched weights and exactly three unused `num_batches_tracked` BatchNorm buffers. Structure had zero missing, unexpected or mismatched weights.

| Stage | Input tensor | Logits | Boxes | Forward time | Process peak working set |
| --- | --- | --- | --- | ---: | ---: |
| Detection | `[1, 3, 600, 800]` | `[1, 15, 3]` | `[1, 15, 4]` | 0.51 s | 594.2 MB |
| Structure | `[1, 3, 580, 1000]` | `[1, 125, 7]` | `[1, 125, 4]` | 0.43 s | 686.8 MB |

The pinned structure processor JSON contains only `longest_edge: 800`; calling it without an explicit size raises `ValueError` in Transformers 4.57.6. The compatibility check computes explicit dimensions using the pinned Microsoft `MaxResize` rule: longest edge **800** for detection and **1,000** for structure, then uses Pillow bicubic resampling and the pinned normalization values. For these synthetic inputs, the resulting tensors exactly matched the original resize/ToTensor/Normalize operations (maximum absolute delta **0.0**). Single-image padding did not change their dimensions. All 15 detection and 125 structure query boxes mapped by `adapt_detr_outputs` agreed with Hugging Face `post_process_object_detection(..., threshold=0.0, target_sizes=original_size)` within **0.00003 original-image pixels**. This checks the raw image-box convention; it does not validate a PDF crop-to-page transform or whether predicted cells contain the right text.

The complete inventory took **31.932 seconds**; C: free space remained above **4.647 GiB** and available RAM above **8.942 GiB**. The inventory and forward-pass timing, resource snapshots, and exact model outputs are in `I:\DocAI-Benchmarks\tatr-cpu-runtime-v1\synthetic-smoke-main-004.json`, SHA-256 `c00109e07c5fda0f2be462507415b70143205f163268cf7dfc304dc7547f4ac5`. The earlier `synthetic-smoke-v5.json` and `synthetic-smoke-main-001.json` recorded a normalized-text lock hash that did not equal the bytes written on Windows; they are superseded. The current writer hashes the actual lock file after writing it, and a second invocation checked the new committed lock before model loading. The receipt and lock explicitly set `document_inference_permitted: false`.

## Reproduction and remaining gates

From the repository root, with fresh output filenames:

```powershell
$env:TEMP = 'I:\DocAI-Benchmarks\tatr-temp-v1'
$env:TMP = $env:TEMP
& 'I:\DocAI-Benchmarks\tatr-cpu-runtime-v1\Scripts\python.exe' -m product_eval.tatr_cpu_runtime_receipt `
  --asset-root 'I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage' `
  --cache-root 'I:\DocAI-Benchmarks\tatr-hf-cache-v1' `
  --host-disk-root 'C:\' --data-disk-root 'I:\' `
  --tokenizers-sdist 'I:\DocAI-Benchmarks\tatr-cpu-runtime-v1\tokenizers-0.22.2.tar.gz' `
  --torchvision-wheel 'I:\DocAI-Benchmarks\tatr-cpu-runtime-v1\wheel-provenance\torchvision-0.25.0+cpu-cp313-cp313-win_amd64.whl' `
  --expected-lock 'product_eval\fixtures\tatr_cpu_runtime_lock_v1.json' `
  --lock-out 'I:\DocAI-Benchmarks\tatr-cpu-runtime-v1\runtime-lock-recheck.json' `
  --receipt 'I:\DocAI-Benchmarks\tatr-cpu-runtime-v1\synthetic-smoke-recheck.json'
```

The [separate OCR source-free handoff](TATR_OCR_WORD_SOURCE_FREE_20261013.md) now provides pinned word polygons for upright synthetic input. Independent review found that RapidOCR can attach 180° recognized words to incorrect boxes, so rotated classifier lines must fail closed until corrected or replaced. The first selected PDF still needs a guarded one-PDF-per-subprocess runner with the frozen thresholds and stop rules; verified real crop/rotation/page coordinate overlays; and model-object-to-cell compatibility on source pixels. The separate source-free cell adapter passes synthetic reconstruction, but it found that upstream row/column refinement ignores threshold arguments. Its 0.5 prefilter is an explicit deviation that the runner profile must name and freeze before scoring. No selected PDF or gold record was opened by this runtime compatibility check.
