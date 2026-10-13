# Frozen real native parser diagnostic v1 (12 October 2026)

The [precommitted parser-only protocol](REAL_NATIVE_PARSER_DIAGNOSTIC_PROTOCOL_20261012.md) ran on all ten [frozen real public development files](NATIVE_REAL_PUBLIC_DEV_CORPUS_20261012.md), two per DOCX/XLSX/PPTX/HTML/EML. It used the exact source hashes in the manifest, one sequential subprocess per file, a 120-second timeout, a sampled 1,024-MiB worker RSS limit, and a 3,072-MiB available-memory floor. No model, network request, gold label, schema induction, or field/row extraction was involved.

| Format | Parsed | Unsupported | Failed | Exact source-locator samples |
| --- | ---: | ---: | ---: | ---: |
| DOCX | 2 | 0 | 0 | 32/32 |
| XLSX | 1 | 1 | 0 | 16/16 on parsed file |
| PPTX | 2 | 0 | 0 | 5/5 on the one file with a table |
| HTML | 0 | 0 | 2 | No cells evaluated |
| EML | 2 | 0 | 0 | No tables in these messages |
| **Total** | **7** | **1** | **2** | **53/53 sampled cells** |

The seven parsed files contained 1,673 table cells. Every cell had a JSON native locator and an exact source-unit text span. The independent native-reader sample resolved all 53 selected locators to the original file. These are structural checks, not extraction precision. One PPTX and both EML files had no tables, so their parsed status supplies no table-locator evidence. No pixel boxes are expected for these source-native formats.

The adoption XLSX was rejected by the 10,000-cell cap (`native_cell_limit`). A separate read-only count found 11,460 nonempty cells across four sheets; a controlled in-memory 20,000-cell-cap probe parsed 11,460 cells and 42,914 source-text characters in 0.619 seconds with 63.06 MiB process RSS. That probe is **not** part of the frozen v1 result or a new product limit. Both ordinary GOV.UK HTML pages failed `XMLSyntaxError` under the strict lxml HTML parser. Any cap or HTML-parser change must be a separately identified arm with fresh results and a new 2,000-source product gate.

**Decision:** native parsing is feasible on these seven files, but it is not robust enough across this ten-file slice. The two HTML failures and one XLSX rejection block a broad format-support claim. The set is small, mostly UK government documents, has no independently labeled fields/rows, and does not prove automatic schema creation or useful structured extraction.

## Receipts

- Protocol: `real_native_parser_only_v1`; frozen manifest SHA-256 `045e72f06822a699b37de4c2da81dec2f4eeed21815680bfb76759135794d878`.
- Diagnostic code SHA-256 `6da36a0e851ef2b39e9e77d3a6ec0ec6c801a6f7d42be8a23b15decfaedf6c5f`; result file SHA-256 `68023719a36d7d46b5cef8a81f93f523bccfcc2b855b3f8c92bd93e9a6cdbe63`.
- Local report: `E:\DocAI-Benchmarks\native-real-public-dev-result-20261012.json`. Original source files and ASF mail bytes remain outside Git and are not sent to a cloud provider.
