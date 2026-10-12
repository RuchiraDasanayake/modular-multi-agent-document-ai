# ExtractBench six-case development admission result

**Admitted for local development, 13 October 2026.** The [pre-admission protocol](EXTRACTBENCH_TEST6_ADMISSION_PROTOCOL_20261013.md) pinned the creator code and the Hugging Face `test-data` revision before any gold inspection. The exact revision `1107fe033a94e93cbc47bb44ded14f02e9c61c62` downloaded to `I:\DocAI-Benchmarks\extractbench-test6-1107fe0` with the cache on I:. All 12 expected repository files are present: six PDFs, three split JSONL files and three metadata files. The six PDFs have distinct raw hashes and total 139 pages. The admission script opened PDFs only to count pages; it did **not** parse schemas, expected values, evidence or PDF text to choose or replace a case.

| Publisher split and PDF | Bytes | Pages | Raw SHA-256 |
| --- | ---: | ---: | --- |
| `long/real_sm0801_eco_full.pdf` | 215,847 | 66 | `e21e6eeb75d5aa1ce519c636de319e20445980e7a1ef28b7aa897d004af89030` |
| `medium/real_pueblo_oct_2025.pdf` | 980,011 | 11 | `aa3548beb298d8de582016b1f4fd9e2b066c983fc7759462901506ef19bca3e8` |
| `medium/veralto_earnings_deck_q4fy25.pdf` | 1,722,236 | 41 | `0b434fe01dc376c8972ede272df0551c30965f58b880dcecdc37bb254de970ce` |
| `short/bianco-2024.pdf` | 593,057 | 10 | `571fe05a74b6c4820906ac9c00e9a8ce141420b7de54d4129f60c61c887c5012` |
| `short/real_wyo_Goshen_2024.pdf` | 304,618 | 10 | `391d65fe5cda94842ac341cf515f947f7a1f554a00f0cc473d14fde6523282a7` |
| `short/W14-Atascosa SWD Well No. 4 - W-14 (Updated 01.22.2025).pdf` | 84,826 | 1 | `628bac93c3ff54210d8c22e42b13367cdf2c832d591b56057746ce027977a2e7` |

The external inventory at `I:\DocAI-Benchmarks\extractbench-test6-admission-v1\manifest.json` records all 12 relative paths, byte counts and SHA-256 values, the pinned creator commit `eb0797020fa22123c42ee4d366963cca321da3ca`, the dataset revision, PDF pages and zero raw-hash overlap with the available mixed VRDU/CORD and full VRDU cohort manifests. Its SHA-256 is `8a5100657513f421dac651e1bf413dce98a98b907e79af126b9dfbfa41e99590`. Raw-hash disjointness does not prove disjoint source organizations, templates or origin filings.

The 66-page case exceeds the product's current 50-page intake limit and must remain in the six-case denominator as unsupported until that limit is intentionally changed and retested. This admission has no model call, extraction output, human review or quality/cost score. The six cases are development data; the default 370-case dataset is reserved as a conditional external comparator after source-rights and overlap review. The dataset card declares Apache-2.0, but underlying document rights and cloud-processing terms are not fully audited, so these files remain local only. [ExtractBench's creator documentation](https://github.com/run-llama/ExtractBench) defines the schema-guided value task; it must not be labeled automatic schema discovery.
