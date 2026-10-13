# Paired product development: text and bounded visual

Status: completed development comparison, 13 October 2026. This is six previously
used public originals, not the reserved quality240 or the final operational2000.
Surface: `research_evidence`; action: `keep`.

## Verification and task

The run used clean code `d41c833ff495df341cacd9805353e49a7579f7ad`, fresh original
intake and corrected RapidOCR in both arms, the same three frozen family schemas,
Luna 6, strict output, bounded long-document handling, 8,192 output tokens,
180-second requests, no SDK retries and serial counterbalanced execution.
The visual arm added `bounded_visual_v1`; all six actually took its visual route.
Every original remained in each arm's denominator.

Before opening development references, independent verification checked the exact
prediction seal, all **215 sealed files (31,852,989 bytes)**, six original hashes,
12 product/result receipts and recomputed all 12 extraction/coverage summaries.
The seal SHA-256 is
`48ec6bf753272a2b22a556c9494929a7b05f64e69d9cf09cd6b4847385dcb8e7`.
No reserved quality240 document or label was opened.

Offline scoring reused the unchanged `_typed_equal`, `assess_records` and
`linked_row_counts` calculations from `icore-confirmed-schema-dev6-paint-v1/analyze.py`.
The historical ordered-list scalar and ordinal-cell diagnostics remain unchanged.
Primary linked-row recall uses order-independent one-to-one assignment.

## Strict mapped-reference results

Each family has two documents. Counts are matches/reference targets. Cells are
the preserved **ordinal** diagnostic; they are sensitive to row order and are
not an alternative to the one-to-one whole-row metric.

| Family | Text scalar targets | Visual scalar targets | Text whole rows | Visual whole rows | Text ordinal cells | Visual ordinal cells |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Registration | 5/10 | 5/10 | N/A | N/A | N/A | N/A |
| Ad-buy | 5/17 | 11/17 | 0/36 | 24/36 | 9/171 | 81/171 |
| CORD receipts | 4/7 | 4/7 | 0/7 | 5/7 | 13/21 | 19/21 |
| Total | **14/34** | **20/34** | **0/43** | **29/43** | **22/192** | **100/192** |

Of the 34 scalar targets, 32 are strings: text 14/32, visual 20/32. Two ad-buy
targets are creator alternative occurrences represented by the historical adapter
as ordered lists; both arms score 0/2. Their frozen output fields are strings,
so this is a task/metric contract limitation. These targets were not removed or
renormalized to improve scores. This is not an official VRDU result.

CORD has positive-only partial labels. Its extra outputs are unassessed, and its
precision/F1 are unavailable. Ad-buy whole-row precision is 24/34 for visual;
the strict reference groups themselves have documented development defects.
These are mapped-label agreement results, not independently adjudicated visual truth.

| Source index and family | Text scalars | Visual scalars | Text rows | Visual rows |
| --- | ---: | ---: | ---: | ---: |
| 0 registration | 1/4 | 1/4 | N/A | N/A |
| 1 registration | 4/6 | 4/6 | N/A | N/A |
| 2 ad-buy, one page | 5/9 | 5/9 | 0/6 | 0/6 |
| 3 ad-buy, six pages | 0/8 | 6/8 | 0/30 | 24/30 |
| 4 receipt | 2/5 | 2/5 | 0/1 | 0/1 |
| 5 receipt | 2/2 | 2/2 | 0/6 | 5/6 |

All scalar improvement comes from the six-page ad-buy document. All row
improvement comes from that document and the second receipt. This small,
previously explored sample does not support a significance or general accuracy claim.

## Coverage, errors and review

- Text: six real calls, five valid complete extractions. The six-page ad-buy had
  28,442 OCR characters and two planned segments. Its first reply reached the
  8,192-token output limit; zero segments completed. The product correctly failed
  the document without releasing partial values. Its eight scalar and 30 row
  targets remain in the denominator.
- Visual: eight real calls, six valid complete extractions across all 14 source
  pages. The six-page ad-buy used three requests and retained one scalar conflict
  (`property`) for review. Full input coverage does not prove correct values.
- No provider errors, refusals, retries or uncertain attempts were recorded.
- All visual values require review. Text has 12/34 strict matching accepted
  scalar targets; visual has zero accepted targets because of that deliberate
  review policy. This does not mean visual proposal accuracy is zero.
- Thirteen evaluated text quotes exactly match product OCR, but their coordinates
  are incompatible with creator OCR. Cross-OCR support validity is unassessed.
  Authentic OCR quotes can still contain OCR errors or describe the wrong field.

Remaining mismatches include registration date/registrant-role selection and
foreign-principal answer scope, receipt comma/period surfaces, truncated ad-buy
date references, and differing scalar alternative occurrences. The one-page
ad-buy's zero complete rows also reflects already documented creator row-group
defects. No new visual adjudication or prediction-driven relabeling was performed.

## Usage and decision

| Family | Text calls / tokens | Visual calls / tokens | Text provider seconds | Visual provider seconds |
| --- | ---: | ---: | ---: | ---: |
| Registration | 2 / 4,677 | 2 / 37,270 | 8.899 | 29.005 |
| Ad-buy | 2 / 18,291 | 4 / 59,123 | 70.972 | 93.993 |
| Receipts | 2 / 4,255 | 2 / 7,983 | 25.859 | 24.478 |
| Total | **6 / 27,223** | **8 / 104,376** | **105.730** | **147.476** |

Text input/output tokens were 13,266/13,957; visual 91,914/12,462. The entire
serial paired run took 420.775 seconds including local work. Visual used 3.83 times
as many total reported tokens and 1.39 times provider latency. Tokens have
different input/output billing rates; provider charges are unavailable. There is
no supported lower-USD-cost claim.

Neither arm matched every assessed positive target on any document (0/6 each).
That diagnostic is not complete-document accuracy because labels are partial
and contain known defects. **USD per correct document is unavailable**, and
tokens per truly correct document cannot be calculated from these references.

Visual input recovered the long document and substantially improved receipt/
advertising rows in this development sample. Blanket visual is a poor default:
registration showed no strict quality gain despite 7.97 times its text tokens.
The next candidate is the explicitly development-derived selective profile:
eligible images/OCR PDFs use visual only when the confirmed task has row groups
or extracted text exceeds one strict 24,000-character segment. Otherwise it uses
text. This new profile must be implemented, tested and frozen before quality240;
the table above is the measured blanket-v1 comparison, not a measured v2 result.
Retain text as the comparison arm. Do not claim a cost-optimal routing policy or
retune the product after inspecting reserved quality240 results.

## Reproducibility

Private artifacts remain outside Git:

- Run: `I:/DocAI-Benchmarks/paired-product-dev6-v1`.
- Derived results/script: `I:/DocAI-Benchmarks/paired-product-dev6-derived-v1`.
- Scoring receipt SHA-256:
  `740ae3f8091253b4d3c7fb228f97dd933010799277510c2cab9c7d75752bbc21`.
- Quality summary SHA-256:
  `01412d939fccc42b9f51ac3ff2368d5af231425774349db8c62c5f07433a5a46`.
- Analysis script SHA-256:
  `b4fd00fe83678c81c6ba47f871683eb1cff2b2f791f1750a1eb84750985d7e35`.

The scoring receipt binds development reference files, metric modules and derived
outputs. It retains all six documents per arm and records that quality240 stayed
closed. No backend, source schema, historical result or reference was changed.
