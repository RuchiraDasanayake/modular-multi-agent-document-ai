# PP-TableMagic v2 ad-buy pilot without oneDNN: CPU smoke timeout

**Completed 13 October 2026.** The separately frozen [CPU arm](PP_TABLEMAGIC_V2_ADBUY12_NO_ONEDNN_PROTOCOL_20261013.md) verified the same 12 public VRDU ad-buy PDFs, gold/scorer, nine pinned local models and 54 model files as the [original arm](PP_TABLEMAGIC_V2_ADBUY12_XET2_RESULT_20261013.md). The isolated PaddleOCR/PaddleX preflight selected plain `paddle` mode with oneDNN disabled, and all nine models loaded. This removed the original immediate CPU exception. The first three-page PDF then reached the **600-second smoke cap** without emitting a page JSON, raster, table, cell, or worker exception. The runner stopped with `smoke_no_go: ContractError: smoke conversion failed`; the other 11 PDFs were not attempted.

| Frozen outcome | Observation |
| --- | ---: |
| Selected / attempted / converted PDFs | 12 / 1 / 0 |
| Selected pages / first-PDF pages | 28 / 3 |
| Gold linked rows / cells retained in denominator | 219 / 808 |
| Page, table, or cell outputs | 0 |
| First conversion time | 600.331 seconds; stopped by `document_timeout` |
| Peak process-tree RSS | 5,620,199,424 bytes |
| Minimum available host RAM | 3,318,943,744 bytes |

The CPU process remained active and stayed just above the preset 3 GiB host-memory floor. **This is a runtime and latency no-go on this host, not a 0/219 parser-accuracy estimate.** No cell alignment or visual audit was possible. The 600 seconds are local inference time, not a measured monetary cost; model and reviewer costs for a completed extract remain unknown. The product parser was unchanged, so this research arm does not itself trigger the separate 2,000-source product gate.

The immutable raw receipt is `E:\DocAI-Benchmarks\tablemagic-v2-adbuy12-xet2-no-onednn`. SHA-256: `run-lock.json` `e7fd0c1ce67eea2fb7124be392f70f35585fc515220a73bc82dccdf8cd2ab4c4`; `run.json` `b4f029bb54413969a1bdfc9059105d786a24c3d112aaf09c86c0e91ab51b11e0`; `resource-samples.jsonl` `a72c36c46757d18b997b2be297f441c1c91a1f51af265796c20cca4e7e8430ca`; first worker log `367f5bb7ec520e30ee81661d96c21c907d20a3d81e33b63761faaedbd5ce9801`. The first source SHA-256 was `00af9ec9594520a61f852e0ccfd93441f068b38fc120625a0571e04941eb1060`.

**Decision:** do not integrate this CPU configuration into the product or relax the cap after observing the timeout. A different pinned table parser needs its own runtime, cell-text/geometry preflight and the same source-locked exact-row/evidence gate before promotion. A GPU TableMagic arm would be a distinct hardware/cost experiment, not a continuation of this result.
