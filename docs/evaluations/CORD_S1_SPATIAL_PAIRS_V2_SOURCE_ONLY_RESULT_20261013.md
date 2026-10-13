# CORD S1 spatial pairs v2: source-only result

**Status:** research candidate catalog only. The [v2 rule and output contract](CORD_S1_SPATIAL_PAIRS_V2_SOURCE_ONLY_PROTOCOL_20261013.md) were committed before the 60-source pass. The [source-free receipt](CORD_S1_SPATIAL_PAIRS_V2_SOURCE_ONLY_RECEIPT_20261013.json) pins the input, code, output hash, and counts. This result does not change or reinterpret the [v1 result](CORD_S1_SPATIAL_ROWS_SOURCE_ONLY_RESULT_20261013.md).

The runner verified the 60 development PNG byte hashes/dimensions, sealed 120-record line-graph file, all RapidOCR line pointers, and the input parser/rule code locks. It made zero OCR/model or product extraction calls and did not read development gold, creator quadrilaterals, or reserved sources. The full candidate JSONL is outside Git at `I:\DocAI-Benchmarks\cord-s1-spatial-pairs-v2-preflight1\spatial_pairs.jsonl`, SHA-256 `9410d36dbb7ab639b702a1a64add320aff0c4ba97b5a852fad113558ce5234ea`.

| Source-only outcome | Count |
| --- | ---: |
| Verified development sources and output page records | 60 |
| Pages with at least one spatial pair | 59 |
| Pages with no spatial pair | 1 (`cord-v2/test/0013`) |
| Pair hypotheses | 570 |
| Pair hypotheses with at least one pair conflict | 287 |
| Pair hypotheses without pair conflict | 283 |
| Unique prefix-line alternatives | 52 |
| Ambiguous prefix-line sets | 1 |
| Pair hypotheses without a prefix | 517 |
| `shared_line` conflict ledger entries | 345 |
| `crossing_order` conflict ledger entries | 17 |

An independent source-only read confirmed all 60 records and source hashes, every left/right/prefix node ID against its sealed RapidOCR graph, one-based contiguous pair ranks, all conflict pair-ID references, and absence of OCR text in pair records. The only page without a pair, `test/0013`, has original-image right-side amounts visible but RapidOCR line output contains no right-column amount nodes; its Tesseract line sidecar is also visibly noisy. Pairing cannot repair missing OCR.

## Concrete v1 failure modes from the frozen source sample

The sample was chosen from the 52 v1-abstaining pages by source-SHA order at indices `0,7,14,21,28,35,42,49`, before v2 was run. Only original PNGs and RapidOCR line graphs were inspected.

| Source | Original-image and OCR-line observation |
| --- | --- |
| `test/0072` | An apparent purchase line has name and amount regions but no separate third OCR line; other two-column totals dominate the bottom. OCR transcription of the purchase name is degraded. |
| `test/0006` | The first apparent purchase line has separate short prefix/name/amount nodes, but the prefix and name boxes overlap horizontally; the next line merges prefix with name. A fixed three-band rule loses both forms. |
| `test/0075` | Six apparent purchase lines each have a merged prefix/name OCR line and a separate right amount line. Global three-band geometry cannot admit any as three-line triplets. |
| `test/0085` | A dense multirow area mixes separate prefixes with merged prefix/name or name/amount OCR lines. Neighboring row boxes overlap vertically, so connected-component grouping becomes crowded and ambiguous. |
| `test/0044` | One apparent purchase line has a name OCR line and an amount OCR line; the visible short prefix was not a separate RapidOCR node. |
| `test/0066` | A possible name/amount line is followed by multiple totals; two-region geometry is present, but geometry alone cannot distinguish purchase from summary. |
| `test/0054` | An apparent purchase name and amount form two OCR line regions; no separate prefix node. |
| `test/0068` | Name and right amount form two regions, but RapidOCR emits duplicated/corrupted numeric text nearby; a geometry witness does not validate transcription. |

V2 raises *geometric candidate support* from v1's 8/60 pages to 59/60 pages by retaining all qualifying left/right line pairs, including conflicts. This is an upper bound on possible source linkage, **not** row recall: many of the 570 pairs are headers, totals, cross-row associations, or OCR errors. The 362 conflict entries also show that a downstream selector must handle ambiguity explicitly. Copying all candidates into an LLM prompt may add cost; a budgeted ranking/selection policy would need a separate frozen rule and quality test. Typed cell witnesses, semantic correctness, positive recall, precision, reviewer effort, and end-to-end cost remain unmeasured. A later product path would require a fresh evaluation and the user's 2,000-distinct-source end-to-end gate.

Validation before the source pass: 30 focused line-graph, v1, and v2 synthetic tests passed; Ruff and `git diff --check` passed. The tests cover two-region rows, overlapping and ambiguous prefix lines, shared/crossing conflicts, rank stability, exact node pointers, tampering, and explicit no-pair abstention.
