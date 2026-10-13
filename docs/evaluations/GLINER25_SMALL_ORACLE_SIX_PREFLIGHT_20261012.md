# GLiNER2.5 Small oracle-schema diagnostic: preflight stopped

**Outcome:** No inference ran. All six locked development sources are **unattempted**. Exact scalar, linked-row, span, latency, memory-under-inference, and cost comparisons are unavailable. This report records a model-weight transport failure, not a model-quality result.

## Frozen boundary

The supplied-schema protocol and runner were committed before weight acquisition (`4178912`), followed by a lock for every model/config/tokenizer file (`555edfd`). The [protocol](GLINER25_SMALL_ORACLE_SIX_PROTOCOL_20261012.md) and [six-source manifest](../../product_eval/fixtures/gliner25_small_oracle_six.json) specify two VRDU registration documents, two VRDU ad-buy documents, and two CORD development receipts. Each source and completed OCR text has an individual pinned SHA256. The manifest contains 53 reference field IDs/shapes, including 16 linked field IDs, but no reference values or rows. Its SHA256 is `1871cf55460944e748257c4e5de8832870250a581158126aba8b90f51ca5e77b`; the frozen [runner/scorer](../../product_eval/gliner25_small_oracle_diagnostic.py) SHA256 is `ece6363b8bb51c2480c85ff34d825a0c6e294c0c1a753b1a1b96d1bd1f6ae043`.

The pinned [official model revision](https://huggingface.co/fastino/gliner2.5-small-v1/tree/df5910e44bc4ffdb0d95399a83b0ca4516349aa5) is `df5910e44bc4ffdb0d95399a83b0ca4516349aa5`. Its `model.safetensors` must be **295,567,700 bytes**, SHA256 `4ee982787ace270d4bf15dbcb28ced38e0aa201372347114ceedd6336055de2b`. The four other required files were downloaded from that revision, checked against Hub Git blob IDs, and pinned by SHA256/byte count in the manifest and runner. They do not substitute for the missing valid weight.

## Environment and transport evidence

The isolated CPU environment imported `gliner2==2.1.0`, `torch==2.10.0+cpu` (`torch.version.cuda=None`), and `transformers==4.57.6`. Fresh checks after the failure showed **8.73 GiB free host RAM**, **9.2 GiB free on C:**, and **3.59 GiB free on E:**. These clear the frozen start floors of 4 GiB host RAM and 1 GiB output storage; they do not establish inference resource use. Five protocol unit tests passed.

1. A full GET for the pinned weight ended at **26,699,608 bytes**. Its SHA256 was `702b79269eb6cf180bcde3c88d0c432dfb58a15418bdc357f91f0f0348575650`, so it was rejected and retained outside Git as `model.safetensors.invalid`.
2. The remote HEAD advertised the expected 295,567,700-byte length and byte ranges. A 1 MiB range probe returned HTTP 206 with a matching `Content-Range`.
3. One clean range-assembly attempt, checking each HTTP 206 response's `Content-Range` and byte count, reached **75,497,472 bytes** in `model.safetensors.ranges.part`. The next range failed with remote `WinError 10054` after five retries. No assembled file existed on which to verify the required full SHA256.

Both rejected/partial files remain outside Git at `E:\DocAI-Benchmarks\models\gliner25-small-v1-df5910e\`. The valid `model.safetensors` is absent. The frozen `_model_files` check would reject the incomplete files. Per the stop instruction, acquisition ended after that one range attempt; no alternate transport, model load, inference call, trial tuning, reply seal, or gold scoring followed. This preserves the six-source denominator without inventing failures as extraction results.

**Next gate:** A complete weight matching both pinned byte count and SHA256 is required before the frozen six-source CPU run can begin. Any later run needs a fresh resource check and must use the committed protocol unchanged, or a separately declared new arm.
