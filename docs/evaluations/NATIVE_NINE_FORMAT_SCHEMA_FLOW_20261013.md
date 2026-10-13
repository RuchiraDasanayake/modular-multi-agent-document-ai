# Native nine-format schema flow: synthetic API smoke (2026-10-13)

## Scope and protocol

This was an authenticated HTTP smoke of the running native product at `127.0.0.1:3000`, using a new job and nine self-authored, byte-frozen order fixtures: DOCX, XLSX, PNG, PPTX, HTML, EML, TXT, JSON, and PDF. Each fixture printed the same two simple order rows. Source hashes were checked before upload and by downloading the owner-scoped original afterward. The private protocol and sanitized receipts are under `I:\DocAI-Runtime\supported-format-smoke-v3`.

The authorized budget was one Luna 6 schema suggestion plus three preview and six remaining-batch extractions, with no automatic retries. This v3 run reserved exactly ten model calls and verified nine extraction SDK attempts. The earlier v1 failed suggestion and separate v2 diagnostic call are preserved as separate failed attempts; neither was silently replayed as part of v3.

## Observed flow

1. Uploaded nine originals into job `7ff3b4e1ee754cd78d038cb87f815466` and saved an intent-only brief with DOCX, XLSX, and PNG as samples.
2. One strict Luna 6 suggestion returned `item_name`, `quantity`, and `amount` as three typed `array[object]` columns in group `order_lines`. Its descriptions and examples matched the requested meanings and synthetic sample values. The suggestion was inspected, saved unchanged as a draft, and explicitly confirmed at revision 3; confirmed payload SHA-256: `85ddbcc91555050d78e4470d8201dc7ec3e285db2bd97f067c4ee3b7f125e2ef`.
3. Preview run `auto_9b30be577f7b495fa817bc97a239e13c` processed DOCX, XLSX, and PNG with one model attempt per file. The PNG took the visual route. The fixture author compared proposed values against the originals, simulated review, and obtained three reviewed document exports.
4. Batch run `auto_9d8179c47a124a56bb32a4b5d27fd556` processed the remaining six formats with one model attempt per file. All three proposed fields had the two expected row values in all six documents. EML quantity cells lacked accepted machine text evidence. The first simulated review POST incorrectly chose `correct` for them and received HTTP 400; a read-only check found review revision 0, zero audit events, unchanged source SHA-256, and unchanged sealed machine-result SHA-256. The rejected event was preserved privately with receipt SHA-256 `193624d799ac1ea05c1b1d8cc966dde27f2a8af41eebe7a6bf4c3f566afccd3b`.
5. The fixture author inspected the EML source: quantity `2` was at page 1 offsets `[74,75)`, and `1` at `[91,92)`. A **simulated human structured correction** for the quantity column then completed review. The exported quantity provenance is `human_correction`; it is not claimed to be originally machine-grounded. The other fields and documents were reviewed without corrections. All nine per-document reviewed JSON exports succeeded. Reviewed JSONL exports contained exactly three preview and six batch documents in selected order.

## Receipts

| Item | Observed |
| --- | --- |
| Schema suggestion | 1 call; 697 prompt, 212 completion tokens; SHA-256 `58207a09db28a05f8d422d9ac53b281dcd0f4f8613e5b6108efc116ba193e83f` |
| Extraction | 9 calls and 9 SDK attempts; 6,710 prompt, 2,909 completion tokens; all finish reason `stop` |
| Total v3 usage | 10 calls; 7,407 prompt and 3,121 completion tokens |
| Preview reviewed JSONL | 3 lines; SHA-256 `10d4768c17145e01b88146b1fafb8abe2f980a66bb746edcb26543cab37fadb4` |
| Batch reviewed JSONL | 6 lines; SHA-256 `ae4c55e2c4cc285f7fc50b0d17d21a8a9cf50ccaa68bb383e5587cf5111df7b6` |
| Final private receipt | `I:\DocAI-Runtime\supported-format-smoke-v3\api-receipt.json`; SHA-256 `995b735aae4eecaf25a51315a2a2c468ab059134ec40a2f9f7076c8460459548` |

The product review UI disables **Correct** for a linked text column whose cells lack accepted evidence and offers **Correct linked rows**. The rejected EML POST was a flaw in the private smoke driver, not a confirmed UI defect. The server gate correctly prevented an unsupported approval.

This establishes that the stated workflow completed for these nine simple synthetic sources on this native deployment. It does not estimate accuracy on real heterogeneous documents, ordinary-user model permissions, browser usability, throughput, or monetary cost; the provider did not return a verified price. The review was simulated by the fixture author, and no claim of independent human validation is made.
