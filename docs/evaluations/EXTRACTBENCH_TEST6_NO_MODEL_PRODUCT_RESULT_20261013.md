# ExtractBench test6: no-model product intake result

**Development diagnostic, 13 October 2026.** This executes the [frozen six-source protocol](EXTRACTBENCH_TEST6_NO_MODEL_PRODUCT_PROTOCOL_20261013.md) on the unchanged product extraction implementation. The product commit at protocol freeze was `d75bf8e`; later commits through `35c4e17` changed evaluation documentation only. The publisher's schema, expected-output, and evidence JSONL remained unopened until all candidate outputs and run receipts were sealed. This report does not score field or value accuracy.

## Reproducibility and integrity

- Pinned dataset revision: `1107fe033a94e93cbc47bb44ded14f02e9c61c62`; admission manifest SHA-256: `8a5100657513f421dac651e1bf413dce98a98b907e79af126b9dfbfa41e99590`.
- Stage manifest: `I:\DocAI-Benchmarks\extractbench-test6-product-v1\stage-manifest.json`, SHA-256 `a524e3800c52e3bcc0e5262ffc79888668b74212dd858b3340ab33432abde548`. Six staged PDF hashes match their six run source hashes exactly.
- Run: `I:\DocAI-Benchmarks\extractbench-test6-product-v1\runs\extractbench_test6_nomodel_v1`. `run.json` SHA-256 `2f78e7684f740ea000cc6dcd0ef7e5a572ab7aa243bfb3b849353443eddd5245`; `manifest.jsonl` SHA-256 `f58ddc0bb5de505afc0cebbd416177e908baa57bdefd544b79df78246c44bfa9`; `candidates.jsonl` SHA-256 `4ca1d755e3b0b3f2de542da95a3c261214d7b62efd4c02fc18fa644c809a7358`.
- Independent execution verifier: six unique raw sources, zero repeats, all source hashes verified. Result-receipt verifier: six verified sidecars. No model configured, zero model calls, zero SDK attempts.

## Observed product outcomes

| Source PDF | Pages | Status | Reason | Proposed fields | Linked fields / cells | Time |
| --- | ---: | --- | --- | ---: | ---: | ---: |
| `bianco-2024.pdf` | 10 | Needs review | `too_many_detected_fields` | 24 | 0 / 0 | 236.3 s |
| `real_pueblo_oct_2025.pdf` | 11 | Needs review | `document_exceeds_auto_limit` | 14 | 0 / 0 | 1.0 s |
| `real_sm0801_eco_full.pdf` | 66 raw | Unsupported | `too_many_pages` | 0 | 0 / 0 | 0.01 s |
| `real_wyo_Goshen_2024.pdf` | 10 | Needs review | `unapproved_dynamic_schema` | 5 | 0 / 0 | 0.17 s |
| `veralto_earnings_deck_q4fy25.pdf` | 41 | Needs review | `too_many_detected_fields` | 24 | 0 / 0 | 1.97 s |
| `W14-Atascosa SWD Well No. 4 - W-14 (Updated 01.22.2025).pdf` | 1 | Needs review | `no_fields_discovered` | 0 | 0 / 0 | 0.17 s |

The full denominator is **six distinct original PDFs and 139 raw pages**: five `needs_review`, one `unsupported`, zero `failed`, zero `processed`. The product considered 73 pages after its 50-page intake guard. It proposed 67 scalar fields and no linked fields or linked cells; zero scalar values were accepted. There were zero automatic releases. Wall time was 239.656 s; summed document duration was 239.575 s. The run reports no API or compute price, so monetary cost per document is unknown; zero model calls does not mean zero local compute cost.

The 10-page `bianco-2024.pdf` consumed 236.124 s in OCR. All ten pages used Tesseract at 300 dpi; six attempted reruns and the OCR sidecar records 51 candidate variants in total. This is a concrete latency and resource problem to diagnose. The result does not establish that a replacement OCR system would be more accurate or faster on this source.

## Decision

This batch is **not a quality pass**. Its absence of linked proposals and inability to auto release are consistent with the earlier mixed 2,000-source no-model gate, but no ExtractBench gold field or value accuracy claim is made here. A separate, frozen scorer must map publisher-supplied schemas, values, rows, and evidence into product outputs before measuring extraction quality. Publisher supplied-schema extraction and automatic schema discovery must be reported separately. Candidate components should remain isolated until a blind comparison shows a net improvement in joined extraction quality, latency, memory, and cost. A substantive product extraction change then requires the user's fresh ≥2,000 distinct-document end-to-end gate.
