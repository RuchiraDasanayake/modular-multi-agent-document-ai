# CORD S1 spatial row v1: source-only result

**Status:** research candidate arm, not an extraction result or S1 quality gate. The [rule and future scorer convention](CORD_S1_SPATIAL_ROWS_SOURCE_ONLY_PROTOCOL_20261013.md) were committed before this run. The [source-free receipt](CORD_S1_SPATIAL_ROWS_SOURCE_ONLY_RECEIPT_20261013.json) locks the implementation, input, output, and counts.

The runner verified all 60 sealed development PNG byte hashes and dimensions, the prior 120-record line-graph file hash, and all 60 RapidOCR graphs and exact line pointers. It made zero OCR/model or product extraction calls, and did not read development gold, creator quadrilaterals, or reserved sources. The source-only candidate JSONL lives outside Git at `I:\DocAI-Benchmarks\cord-s1-spatial-rows-preflight1\spatial_rows.jsonl`, SHA-256 `0ab4886430c835399afbb18c90f51ce16dcc4e4dd88a1a15a759cf17e38432c2`.

| Source-only outcome | Count |
| --- | ---: |
| Verified development PNGs and output page records | 60 |
| Pages with at least one generic spatial triplet | 8 |
| Pages without a generic spatial triplet | 52 |
| Admitted three-line triplets | 14 |
| RapidOCR line nodes partitioned into admitted triplets or abstained lanes | 974 |

The 447 **lane** abstentions are component counts, not document counts: `incomplete_lane` 394; `crowded_lane` 26; `duplicate_or_missing_band` 18; `transitive_overlap_ambiguous` 6; `horizontal_overlap` 2; `wide_line` 1. A separate source-only read confirmed each of the 974 line node IDs appears exactly once in an admitted triplet or an abstained lane, with no ID in both.

Fourteen triplets on eight pages show that the conservative geometry witness is usable as a narrow candidate source but has low coverage. It cannot capture many two-column, merged-OCR-line, or vertically overlapping layouts. Nor do these counts show that any admitted triplet is an item row: headings, totals, and unrelated text can satisfy geometry. The fixed later exact-text scorer has **not** been run against gold. Positive recall, precision, OCR correctness, semantic role accuracy, reviewer effort, and end-to-end cost remain unknown. The rule should stay sealed as v1; any broader layout strategy needs a separately versioned rule and evidence.

Validation before the source pass: 24 focused spatial/line-graph tests passed, Ruff passed, and `git diff --check` passed. The tests include synthetic duplicate text with distinct source pointers, isolated and ambiguous components, tampering, one-to-one exact-text scoring, and missing-source denominator rejection. This remains a research-only branch; integrating into the product would require separate quality evidence and the user's 2,000-distinct-source end-to-end gate.
