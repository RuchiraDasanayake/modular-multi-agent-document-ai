# Qwen3-VL-2B blind linked dev6: source lock

**Chronology:** The [protocol](QWEN3_VL2B_BLIND_LINKED_DEV6_PROTOCOL_20261013.md) was committed first as `d526bae036f3d56965fcfc0634a56f44182267af`. This source-only lock was derived afterward, before any input rendering, model acquisition, prompt finalization, or scored inference. No gold file, OCR text, PDF page text, or model output was opened to select these sources. This is a development diagnostic, not a holdout or accuracy result.

## Selection and exact source manifest

The public [VRDU cohort](https://github.com/google-research-datasets/vrdu) at creator commit `04a4df7ac5cc694e51c48115c03fe428f0e240cc` contains 2,000 rows. Local cohort file SHA-256: `98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90`. Within each `family`, sort metadata rows by `(source_sha256, doc_id)` ascending and select one-based ranks 21–23. Source root is `E:\DocAI-Benchmarks\vrdu-extracted\vrdu-04a4df7ac5cc694e51c48115c03fe428f0e240cc\<family>\main\pdfs\<filename>`, where `source_id` is `<family>/<filename>`. Recompute raw file SHA-256 and byte length and require both to match the cohort metadata. `page_count` was read with local `pypdfium2==5.14.0` `len(PdfDocument(path))`, without rendering or text extraction.

The canonical source-lock SHA-256 is `589a691fb2b6e9f5255689f299bef9e0d6258ad996937b4f3d9b4f827f63db59`. It is SHA-256 of the UTF-8, no trailing newline serialization of the JSON array below, with source order registration ranks 21–23 then ad-buy ranks 21–23, `sort_keys=True`, `separators=(',', ':')`, and `ensure_ascii=False`. The pretty-printed JSON below is for review; recompute the digest from the canonical form. All six raw source hashes and doc IDs are unique. There are **six PDFs and 11 pages**; the six-source denominator is fixed.

```json
[
  {
    "family": "registration-form",
    "rank": 21,
    "doc_id": "1185cd1fede2b34bfb7e222b63797232",
    "source_id": "registration-form/20100514_Hill and Knowlton Strategies, LLC_Kaiser, Christina_Short-Form.pdf",
    "source_sha256": "03bc96745efa7e63bae438bfd31a9a62adcb5b85d85cd16706a8b8a1bea6cc2b",
    "source_size_bytes": 113136,
    "page_count": 2
  },
  {
    "family": "registration-form",
    "rank": 22,
    "doc_id": "71d043beef92ecf84ac0f8b7e6c88a1a",
    "source_id": "registration-form/20150108_Daniel J. Edelman, Inc._Zenatti, Ana Paula_Short-Form.pdf",
    "source_sha256": "04429606694b7aec9925ae93c95f22b4b623022e9fa322c149a2385a438e4dd2",
    "source_size_bytes": 157422,
    "page_count": 2
  },
  {
    "family": "registration-form",
    "rank": 23,
    "doc_id": "97fdc346f0667275021ede8690bf0a84",
    "source_id": "registration-form/20171213_Capitol Counsel, LLC_Amendment_Amendment.pdf",
    "source_sha256": "045c5a20c2465532c1da8268c4608629d9a3d6c3a26797dddfbf92bd6a3c3c34",
    "source_size_bytes": 81783,
    "page_count": 2
  },
  {
    "family": "ad-buy-form",
    "rank": 21,
    "doc_id": "959e515eda4a22679644702aded5e055",
    "source_id": "ad-buy-form/a2350a6d-b7e2-fc75-5345-04402ca7234e.pdf",
    "source_sha256": "07feaa5c37513d3ab784c1f663147cf665231b1c4739ca556d5590db2eb63766",
    "source_size_bytes": 225667,
    "page_count": 2
  },
  {
    "family": "ad-buy-form",
    "rank": 22,
    "doc_id": "0d802bdf961d7d9f06acf0f5d4b53738",
    "source_id": "ad-buy-form/73981638-cc90-0e1e-444b-9186f7c846c9.pdf",
    "source_sha256": "0820425ba3d4f31424e26e85c6e7823143724fed8bb74589d3d8f9239160a441",
    "source_size_bytes": 278651,
    "page_count": 1
  },
  {
    "family": "ad-buy-form",
    "rank": 23,
    "doc_id": "924e564a3ddcaae641ce1960d69fa6d2",
    "source_id": "ad-buy-form/56a8dc3f-5156-8ebc-db71-15e3a9c1b1c1.pdf",
    "source_sha256": "0889c23ecbbcd8d5e4f99d5a46b2d5a8f20528de4a7c09a4d6b7571216fcf50d",
    "source_size_bytes": 18977,
    "page_count": 2
  }
]
```

## Prior-diagnostic exclusion audit

At baseline repository commit `a8434aac4da82e719f3a13ab8f45ad96cc153ed4`, recursively collect `doc_id`, `source_sha256`, and `raw_source_sha256` string values from each of the following frozen files. Compare both the six chosen doc IDs and six raw source hashes. Every intersection is empty. File hashes freeze the exact exclusion audit inputs, not the current repository state forever.

| Exclusion file | File SHA-256 | Selected ID/hash overlap |
| --- | --- | ---: |
| [docling_graph_v1_dev_sources.json](../../product_eval/fixtures/docling_graph_v1_dev_sources.json) | `61bef64cafb35739eba3a087fe5a742c57e68c340834325a8f77e49f63c5b047` | 0 |
| [nuextract3_group_leaf_dev12_sources.json](nuextract3_group_leaf_dev12_sources.json) | `4883ab362d7b6d70c84ac751ed045b3d0c5f65adaa0ab8d3c1a10e22c890b962` | 0 |
| [icore_real_dev_six_sources.json](../../product_eval/fixtures/icore_real_dev_six_sources.json) | `a64f14e737ae7fe2bda3a84458d996385db40b253a78175ec161a6175c82cb15` | 0 |
| [icore_two_public_sources_v1.json](../../product_eval/fixtures/icore_two_public_sources_v1.json) | `77d70cef8e6839e2788a8579d9780174b51a908532d9c131c07bf6218dc93efa` | 0 |
| [adr0005_qwen_twelve_sources.json](../../product_eval/fixtures/adr0005_qwen_twelve_sources.json) | `a97f91f4dd5a4a682109a710d4a091ab344d0f5731080ad7eeddbf08b9f6566b` | 0 |
| [vrdu_ad_buy_table12.jsonl](../../product_eval/fixtures/vrdu_ad_buy_table12.jsonl) | `b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d` | 0 |
| [ICORE_VRDU_SIX_PILOT.json](ICORE_VRDU_SIX_PILOT.json) | `9179576701675bdb56cea652206693bc16ab4486c26625312d7d7be20a8e1ac7` | 0 |

The selected six are source-disjoint from these listed diagnostics only. This does not establish unseen layouts, vendors, public-leaderboard independence, or production generalization. Gold-field/cell/row counts are intentionally undisclosed until all future raw model replies are sealed, per the protocol. No model or checkpoint was downloaded or run for this lock.
