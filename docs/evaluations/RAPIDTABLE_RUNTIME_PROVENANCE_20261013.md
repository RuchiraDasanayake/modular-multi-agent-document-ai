# RapidTable 3.0.2 runtime and notice audit

**13 October 2026 — source-free runtime HOLD.** This receipt audits the frozen 23-wheel Windows CPython 3.11 RapidTable environment. It opened no selected VRDU PDF or gold annotation, ran no OCR or table model, and made no product extraction change. The existing v1 environment and all earlier receipts were left untouched.

## Installed-byte decision

The [runtime auditor](../../product_eval/rapidtable_runtime_provenance.py) verified the SHA-256 and size of every cached wheel in the [original lock](../../product_eval/fixtures/rapidtable_v3_runtime_lock.json), each wheel's internal `RECORD` hashes and sizes, the installed `RECORD` rows, and the installed bytes of **2,290 wheel payload files**. **22 of 23 distributions matched their pinned wheels.** The remaining distribution, `opencv-python-headless==5.0.0.93`, had three mismatches:

| Shared installed path | Pinned `opencv-python` SHA-256 | Pinned `opencv-python-headless` SHA-256 | Installed owner |
| --- | --- | --- | --- |
| `cv2/cv2.pyd` | `f1e76ab0…195e8f9b0dd` | `eefedf6e…b91d6d48` | regular OpenCV |
| `cv2/typing/__init__.py` | `f8a066f2…cced8d9179` | `93bdb902…af9c3e68e1` | regular OpenCV |
| `cv2/version.py` | `fc17efee…d91957fb` | `35ef3f10…678bf125` | regular OpenCV |

The full digests, installed paths and per-distribution `RECORD` hashes are in the external receipt. The installed `cv2` reports version `5.0.0`, `headless=False`, and binary SHA-256 `f1e76ab01cf4d33af780adf8ada1a26c5eaeecc55d2cbe8a5e288195e8f9b0dd`. The installed `opencv-python-headless` metadata still claims its own, different bytes. `pip check` passes because both distributions are present; it does not detect file ownership conflicts. There are also 1,484 generated `.pyc` `RECORD` entries without hashes beyond the pinned wheel payload. The receipt therefore sets `installed_distribution_contents_verified=false`.

**Independent review correction:** The initial auditor counted but did not hash installed `RECORD` extras with supplied digests, and did not require the `RECORD` self row. The reviewed auditor now verifies both; a regression fixture changes a hashed `INSTALLER` file and another removes the self row. A fresh main-checkout audit at `I:\DocAI-Benchmarks\rapidtable-runtime-provenance-v1\installed-wheel-and-notice-audit-main-v4.json`, SHA-256 `e4b68249cb097da2270985b64a42bde7a5d8b01fb058749f44487d5641a05cef`, found **zero** mismatches among the 33 hashed extras. The same three OpenCV payload mismatches and 1,484 unhashed `.pyc` entries remain, so the HOLD decision is unchanged. The earlier v3 receipt is retained as historical evidence, not a complete installed-byte audit.

This cannot be safely fixed by simply uninstalling either wheel in the existing v1 environment: the `rapid-table==3.0.2` wheel explicitly requires `opencv_python>=4.5.1.48`, while `rapidocr==3.10.0` explicitly requires `opencv-python-headless>=4.5.1.48`. The two pinned OpenCV wheels install different bytes to the same three paths. Reinstalling in a different order selects a different winner and leaves the other distribution's `RECORD` false. Keep the runtime hold until a new isolated design removes the duplicate ownership, for example an upstream dependency correction or separately locked OCR and table processes, followed by a fresh source-free audit and functional test. Do not reinterpret the existing six-cell synthetic smoke as installed-byte closure.

## License and notice evidence

The original lock's `notices=[]` for six wheels meant its inventory missed notice paths outside `.dist-info/licenses`; it did **not** mean those six wheels all lacked notices. The [notice addendum](../../product_eval/fixtures/rapidtable_v3_notice_addendum.json) binds the exact paths, sizes and SHA-256 values below to the original lock without rewriting that frozen fixture.

| Pinned wheel | Exact notice evidence |
| --- | --- |
| `onnxruntime==1.31.0` | Wheel contains `onnxruntime/LICENSE` (SHA-256 `c250d627…2b674`) and `onnxruntime/ThirdPartyNotices.txt` (`c53a7650…1b86622`). |
| `opencv-python==5.0.0.93` | Wheel contains `cv2/LICENSE.txt` (`edef0fac…e26107`) and `cv2/LICENSE-3RD-PARTY.txt` (`c1d60169…e73fadb`), duplicated under its `.dist-info` directory. |
| `opencv-python-headless==5.0.0.93` | Same four notice files and hashes as the regular wheel, including its own `.dist-info` copies. |
| `protobuf==7.36.2` | Wheel contains `protobuf-7.36.2.dist-info/LICENSE` (`6e5e1173…130fea7d`). |
| `six==1.17.0` | Wheel contains `six-1.17.0.dist-info/LICENSE` (`4375ba20…b81fbd0`). |
| `flatbuffers==25.12.19` | Its pinned wheel has **no embedded notice file**. Its wheel `METADATA` declares `License: Apache 2.0` and links to the [official source repository](https://github.com/google/flatbuffers). The [official v25.12.19 tag](https://github.com/google/flatbuffers/releases/tag/v25.12.19) has a [LICENSE](https://github.com/google/flatbuffers/blob/v25.12.19/LICENSE); a fresh copy is 11,358 bytes, SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. |

The auditor rechecks all **12 embedded notice files** and the separately retained tagged FlatBuffers license. This supplies precise source-free notice evidence for the six previously flagged wheels. It does not assemble or approve a product attribution bundle, establish model rights beyond the separate [publisher asset receipt](RAPIDTABLE_PUBLISHER_ASSET_RIGHTS_20261013.md), or clear redistribution. FlatBuffers would need its tagged license shipped with any package containing that wheel.

## Reproduction and retained evidence

Run only in the existing isolated v1 Python environment; provide a new absent receipt path outside Git:

```powershell
I:\DocAI-Benchmarks\rapidtable-adbuy12-runtime-v1\Scripts\python.exe -m product_eval.rapidtable_runtime_provenance `
  --wheel-lock product_eval\fixtures\rapidtable_v3_runtime_lock.json `
  --wheel-dir I:\DocAI-Benchmarks\rapidtable-adbuy12-wheels-v1 `
  --notice-addendum product_eval\fixtures\rapidtable_v3_notice_addendum.json `
  --flatbuffers-license I:\DocAI-Benchmarks\rapidtable-runtime-provenance-v1\flatbuffers-v25.12.19-LICENSE `
  --output I:\DocAI-Benchmarks\rapidtable-runtime-provenance-v1\NEW-absent-receipt.json
```

The reviewed audit receipt is `I:\DocAI-Benchmarks\rapidtable-runtime-provenance-v1\installed-wheel-and-notice-audit-main-v4.json`, SHA-256 `e4b68249cb097da2270985b64a42bde7a5d8b01fb058749f44487d5641a05cef`. The retained tagged FlatBuffers license is at `I:\DocAI-Benchmarks\rapidtable-runtime-provenance-v1\flatbuffers-v25.12.19-LICENSE`. The original 23-wheel lock remains SHA-256 `1264a56da9c666676deb1a442eae8811aff296001340c105d07acd90e3042f4a`; the Windows checkout addendum is SHA-256 `a7924e0ad7130156485d1bfff659c92f485ddb8fe19155900fb07dc9cf51fa01`.

**Next gate:** choose and validate a single-owner OpenCV runtime design, then rerun this audit and the source-free synthetic smoke. The separate OCR model, table localization, page-coordinate and guarded-runner gates in the [RapidTable protocol](RAPIDTABLE_V3_ADBUY12_PROTOCOL_20261013.md) still hold selected-PDF inference.
