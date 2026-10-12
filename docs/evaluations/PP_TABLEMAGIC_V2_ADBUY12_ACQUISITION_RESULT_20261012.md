# PP-TableMagic v2 ad-buy challenge: acquisition stopped before inference

**Decision: no score and no product promotion.** The frozen [parser pilot protocol](PP_TABLEMAGIC_V2_ADBUY12_PROTOCOL_20261012.md) required all nine active official model inventories to match pinned sizes and content digests before any PDF processing. The seventeenth of 54 active files failed its sole transfer attempt, so the model gate did not open. There was no TableMagic inference, table HTML, cell-box output, or visual overlay audit.

## Frozen cohort and attempted work

The same 12 public VRDU ad-buy PDFs were rehashed successfully against selection SHA256 `b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d` and cohort SHA256 `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`. The external gold SHA256 was `8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf`. The locked denominator remains **12 PDFs, 28 pages, 219 linked rows, 808 linked cells**. PDFs processed: **0/12**; parser rows scored: **none**. A numeric `0/219` here would describe a missing run, not measured parser accuracy, so it is excluded from quality comparisons.

Acquisition used one Python standard-library `urllib.request.urlopen` attempt per file on the official PaddlePaddle Hugging Face raw `resolve/<pinned revision>/<file>` URL, following normal HTTP redirects. It did **not** use `huggingface_hub` or `hf_xet`. The local acquisition script had no retry or alternate source, a 900-second per-asset deadline, a 5,400-second whole-run deadline, a pinned size/content check, and C: ≥4 GiB, E: ≥2 GiB and available RAM ≥3 GiB continuing floors. Sixteen files verified, totaling **137,110,859 bytes**. The first two model directories completed; the third stopped at `PP-LCNet_x1_0_table_cls/inference.pdiparams` with `ConnectionResetError [WinError 10054]`. That seventeenth file left a zero-byte partial and was not retried. The remaining **37/54** active files were not attempted. No model or pipeline profile was retuned.

| Gate | Preflight | At stop | Outcome |
| --- | ---: | ---: | --- |
| Available host RAM | 8.64 GiB | 8.19 GiB | Above 3 GiB continuing floor |
| Free C: | 9.21 GiB | 9.03 GiB | Above 4 GiB floor |
| Free E: | 3.59 GiB | 3.59 GiB | Above 2 GiB floor |
| Competing GLiNER/Paddle worker | None observed | None observed | No resource contention observed |
| Verified active model files | 0/54 | 16/54 | **Failed transfer gate** |

## Evidence and interpretation

The raw acquisition receipts, verified bytes and failed zero-byte partial are outside Git at `C:\DocAI-TableMagic`. The sealed 20-file acquisition inventory has root digest SHA256 `25f6509e400158ea8260385eda442a7d09c5c219d2caf65bf1f4e69b967360ac`; the `acquisition-seal.json` file SHA256 is `2ea0655eb496b2cb6c4158448131acdab8a5f307fcdacca3b404083ac3eb2364`. The receipt records 16 verified assets and one failed attempt. The source-locked runner never started, so there are no conversion receipts to conceal or reclassify.

The acquisition Python 3.13 environment has `huggingface_hub 0.36.2` and `hf_xet 1.2.0` installed, but neither package is called by this script. The separate Paddle Python 3.11 environment has `huggingface_hub 2.2.0` and `hf_xet 1.7.0`; it was also not used for acquisition. This observed connection reset cannot be attributed to an `hf_xet` code path.

This is a **transfer failure**, not evidence that PP-TableMagic extracts poorly or well. Its promised table HTML, cell coordinates and source alignment remain unmeasured on this host. The prior [PaddleOCR-VL 1.6 result](PADDLEOCR_VL16_ADBUY12_RESULT_20261012.md) remains 14/219 complete exact-cell rows, with extra parser cells allowed, and 0/219 strict exact-multiset rows; it is not replaced by a TableMagic score. A future TableMagic attempt would require a new, separately declared protocol and fresh resource/transfer authorization. The user's 2,000-document extraction gate is untouched.
