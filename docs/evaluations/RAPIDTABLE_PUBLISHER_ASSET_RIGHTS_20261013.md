# RapidTable SLANet-plus publisher asset receipt

**Date:** 13 October 2026. **Scope:** the exact ONNX asset in the frozen RapidTable 3.0.2 research arm. No selected PDF, gold annotation, product extractor, or 12-source score was opened or changed.

## Decision

**Keep** SHA-256 `d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b` as the source-free RapidTable research candidate. An independent download from the publisher's model repository has the same bytes as the previously held mirror copy. RapidAI's **model repository**, separate from its code repository, currently declares **Apache License 2.0**. This resolves the prior mirror-only provenance concern for a local research trial of these bytes. It does not certify a complete redistributable product.

**Hold** selected-PDF inference and product packaging under the other gates in [the frozen RapidTable protocol](RAPIDTABLE_V3_ADBUY12_PROTOCOL_20261013.md): installed dependency notice/content closure, locked OCR models, table detection, coordinates and source-cell evidence, and the guarded runner. Human review of attribution and upstream conversion provenance remains appropriate before distributing a packaged model. The ModelScope licence label is repository-level current metadata; there was no per-file `LICENSE` in the v2.0.0 file listing. The code licence by itself was never the model licence.

## Publisher evidence and exact bytes

| Evidence | Observation |
| --- | --- |
| [RapidTable v3.0.2 registry](https://github.com/RapidAI/RapidTable/blob/v3.0.2/rapid_table/default_models.yaml) | `slanet_plus` points to RapidAI's ModelScope `v2.0.0/slanet-plus.onnx` and declares SHA-256 `d57a942a…4514b`. |
| [RapidAI ModelScope model repository](https://www.modelscope.cn/models/RapidAI/RapidTable) and [repository API](https://www.modelscope.cn/api/v1/models/RapidAI/RapidTable) | Publisher organization `RapidAI`, creator `liekkas`, current repository licence field `Apache License 2.0`. This is a model-repository declaration, not an inference from the Python package licence. |
| [v2.0.0 file listing API](https://www.modelscope.cn/api/v1/models/RapidAI/RapidTable/repo/files?Revision=v2.0.0&Root=) | `slanet-plus.onnx`, commit `b5e25351fb5367f28ddd69d0ccaa4abe73042102`, 7,758,305 bytes, SHA-256 `d57a942a…4514b`. |
| [Publisher asset](https://www.modelscope.cn/models/RapidAI/RapidTable/resolve/v2.0.0/slanet-plus.onnx) | HTTP HEAD 200 with `X-Linked-Etag` equal to the full SHA-256 above. Fresh 7,758,305-byte download hashed to that value and equals the earlier mirror copy byte for byte. The synthetic test used this publisher download. |
| [PaddlePaddle's upstream SLANet_plus model card](https://huggingface.co/PaddlePaddle/SLANet_plus) | Labels its upstream model `apache-2.0`. Supports the provenance chain; these are distinct Paddle inference files, so the card alone would not license the exact RapidAI ONNX export. |
| [RapidTable v3.0.2 code licence](https://github.com/RapidAI/RapidTable/blob/v3.0.2/LICENSE) | Apache-2.0 code. Separate from the ModelScope model declaration. |

The frozen API bodies and compact provenance receipt are outside Git at `I:\DocAI-Benchmarks\rapidtable-clean-asset-publisher-v1`. Their SHA-256 values are `c2fc1f1b3d21c920eab739ff545cac45337506c332f7c83266dac31237f9325d` (model API), `c277057b4843d2c5e5fca3ded0c52db7ea4ee9204dd560643c337fabb7519642` (file listing API), and `12b80a95763727d2a2878bed5bddf7479a95c067e6d0b673ecbc7e0674d86ee2` (`publisher-provenance-v1.json`). The ONNX file is retained outside Git at `I:\DocAI-Benchmarks\rapidtable-clean-asset-publisher-v1\slanet-plus.onnx`.

The earlier OpenDataLab copy's repository-level AGPL label is **not** used as a licence grant for the independently downloaded RapidAI bytes. The byte comparison establishes identity only; the publisher's own repository declaration supplies the licence evidence.

## Source-free compatibility

The unchanged locked Windows Python 3.11 environment ran `product_eval.rapidtable_adbuy12_preflight` with the **publisher** ONNX and the existing synthetic 900×300, 2×3 table. It returned six exact logical grid cells, six cell boxes, six logic points, and actual `CPUExecutionProvider`. The model stage reported 0.063 seconds for one artificial crop **with supplied OCR text**. That timing excludes PDF rasterization, table detection, OCR inference, startup, review, failures and document throughput. The smoke receipt is `I:\DocAI-Benchmarks\rapidtable-clean-asset-publisher-v1\rapidtable-official-synthetic-20261013-070422-646.json`, SHA-256 `61638d3cc3935e930724fea1dbc391f3f7e7fff3203d35509a902d051dbf8d32`. It records zero selected PDFs and zero gold records opened.

The existing preflight still prints `model_rights: research_only_hold_mirror_agpl_metadata`, a **stale field from the earlier provenance state**. This receipt supersedes that field for the model asset only. No preflight source or frozen protocol was silently edited; its model hash and all score gates remain fixed.

## Resource and integration boundary

The additional official transfer was 7,758,305 bytes, about 7.4 MiB, to the spacious I: drive; no model download to the constrained C: drive was needed. This task made no extraction implementation change, so the separate 2,000-distinct-document product gate was not triggered. The previously proposed `PPSTRUCTURE_EN` alternative (publisher registry SHA-256 `2cae17d16a16f9df7229e21665fe3fbe06f3ca85b2024772ee3e3142e955aa60`) was **not** substituted, downloaded, or scored.
