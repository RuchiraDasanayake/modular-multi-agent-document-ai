# Native visual review workflow: synthetic API smoke (2026-10-13)

## Scope and protocol

This was one end-to-end exercise of the native Windows product through authenticated loopback HTTP, using two
self-authored, single-page PNG invoices. The images visibly said `SYNTHETIC TEST INVOICE - NOT A REAL TRANSACTION`.
No production data or database fixtures were injected. The extraction brief was **manually specified** with four
typed fields: `invoice_number`, linked `item_name` and `quantity`, and `amount_due`. The sample was confirmed at
brief revision 2, previewed, reviewed, and then the same confirmed schema was applied to the remaining image.
The review decisions were **simulated by a script using known fixture truth** through the ordinary admin API;
this was not a human-subject study or a browser UI walkthrough. The script reserved at most two Luna 6 calls,
with no automatic retry or Sonnet use.

The test exercised job creation, binary upload, brief draft/confirmation, PostgreSQL queue admission, actual
RapidOCR plus visual worker execution, preview review gating, owner-authenticated original-source download,
field review/correction, human-added scalar and linked-cell page references, individual reviewed JSON export,
reviewed batch JSONL export, and the visual recipe exclusion. It did not call the AI schema-suggestion action.

## Sealed receipts and observed results

Job `eb6bebff34814fddbd9c928372553112` confirmed brief payload SHA-256
`1aea33213a717956dc56b49a2dbe072c336d795886c944a277ae16fed195c195`.
The authenticated source endpoint returned bytes matching each uploaded image's SHA-256.

| Phase | Preview | Remaining batch |
| --- | --- | --- |
| Run ID | `auto_110131b5015f472cbdcc8fa3edc48785` | `auto_9af5f4acaa29429db9426134a01da6f9` |
| Document ID | `008c8a700f5ef5a6ed6248d1380033e8` | `f71750ef3438f4d3291e8da86c8cb998` |
| Source SHA-256 | `1daf57ad9690ff5a96706a32bb3dba38e8bcc58900afd70eef36d829d5292838` | `398133550f37afce507ce49e447a897698a811da31bb1d4cfeabc6ab3b5b483a` |
| Machine result SHA-256 | `195359c2851e4c47923d8776216b69a107bbf39d37eed4c29e39382ef24f8f24` | `5c2509c9cf539cf9935c200e7bea712a5c696e737b6f9c13a806f6426246b6d0` |
| Reviewed JSON response SHA-256 | `4f0cae8a9ff5c7376fd07ae0aa431d571bf35fcb3f9ce6573a9d3948f665d0b8` | `a326b1674a4a4794bf5fccab24c985562896eaa9abed3525fc2029c2637e10dd` |
| Luna 6 SDK attempts | 1 | 1 |
| Prompt / completion tokens | 3,879 / 356 | 3,882 / 306 |

Both sealed runs used `bounded_visual_selective_v2`, `rapidocr`, and effective
`strict_visual_confirmed_values_v1`. The selective route reason was `selective_repeated_fields`. Each run
recorded one planned, attempted, and valid visual request; page 1 was fully covered. Each completed with
`needs_review`, as image-derived proposals require. The model's four confirmed-schema values matched the
separately specified truth on both clear fixtures (8/8 field matches). The script then completed review revision 1,
added `tax` as a scalar and `sku` as a linked cell with `human_observed_page: 1`, and verified that exported values
had `provenance: human_added` and `visual_grounding_verified: false` without fabricated OCR evidence.
Individual reviewed JSON exports returned HTTP 200. An attempted reusable recipe draft returned HTTP 409 for
each visual result. The remaining run's reviewed JSONL export returned HTTP 200 with exactly one line, SHA-256
`e9b4da6bb0d10b587e392dcede43339919a7b2370f6b52ea18752eea29f0cd1a`.

Total observed model calls: **2**, with **2 SDK attempts**, **7,761 prompt tokens**, and **662 completion tokens**.
Provider cost was `null` in both run receipts, so this run does not establish a dollar cost. The private
sanitized receipt is `I:\DocAI-Runtime\visual-hitl-smoke-v1\receipt.json` (SHA-256
`8d25b6c52be2d150871023f90de3fe980c62decf8df71f3aa9944c7b5331134c`); the resumable private
script and two synthetic images are in the same folder. No credentials or provider responses are in this document.

## Limits

Two large-font, one-row synthetic invoices cannot establish accuracy on varied documents, handwriting,
tables, low-quality scans, or the intended 2,000-document evaluation. The schema was manually confirmed;
AI schema drafting was outside this two-call budget. Review decisions came from fixture truth through the API,
so browser rendering, actual human judgment, accessibility, and multiuser behavior were not observed here.
The run also cannot demonstrate throughput or latency under sustained load. These claims must remain separate
from conference paper results and from the larger benchmark currently in progress.
