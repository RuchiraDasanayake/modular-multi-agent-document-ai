# Granite-Docling source-free API smoke

**Prepared 13 October 2026; no result yet.** This bounded local smoke checks
whether the already staged Granite-Docling 258M assets and Windows CUDA runtime
can parse one self-drawn 2×3 table through the publisher's Transformers and
`docling-core` API. It opens no selected PDF, CORD receipt, or gold. It is not
the [12-PDF parser pilot](UNMEASURED_COMPONENTS_NEXT_PILOT_20261012.md), a
business-schema evaluation, or a product extraction change.

The worker is [`product_eval/granite_source_free_smoke.py`](../../product_eval/granite_source_free_smoke.py).
It requires the staged publisher revision
`982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe`, its 13 acquisition-receipt
assets, and weight SHA-256
`1cdad234deb1cde18ee6a586f849057f19851daf1fedce2e40aff791dbe46f61`.
The staged acquisition receipt SHA-256 is
`142457cfd4d023afd71983dc0afbbad821a4baff78a1f36163ae6d81d949dccc`.
Its fixed Windows runtime versions are PyTorch `2.9.1+cu128`, Transformers
`4.56.1`, `docling-core` `2.101.1`, and Pillow `12.3.0`; the earlier staged
runtime passes `pip check`. It uses local files only, CUDA BF16, SDPA,
deterministic decoding, a 2,048-token output cap, one synthetic image, and a
minimum 512 MiB free GPU-memory floor. Raw DocTags, parsed table cells and
boxes, timings, token count and asset hashes go to a new exclusive directory
outside Git. A timeout or missing source-pixel cell evidence is a failure or
limitation, never a table-quality score.

The staged assets are at
`I:\DocAI-Benchmarks\granite-docling-258m-982fe3b-v2\model`; the staged
acquisition receipt is the sibling `acquisition.json`. The planned fresh
output is `I:\DocAI-Benchmarks\granite-source-free-smoke-v1`. A successful
smoke would permit writing a separately frozen one-PDF gate; it would not
permit scoring the other eleven PDFs or changing `process-auto`.
