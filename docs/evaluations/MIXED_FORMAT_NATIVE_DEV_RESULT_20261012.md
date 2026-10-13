# Native parser reuse diagnostic — 12 October 2026

**Decision:** Use source-native parsers as the first benchmark for structured DOCX, XLSX, HTML, EML, and PPTX evidence. This five-file synthetic test recovered every known table cell and resolved each source-specific locator. It does **not** establish production support, extraction accuracy on real files, or a speed advantage over Docling. Keep Docling as a competing normalization candidate and compare both on a diverse holdout before choosing an adapter.

## Frozen inputs and method

The [existing Docling mixed-format fixture manifest](../../product_eval/fixtures/mixed_format_docling_v1/manifest.json) locks the same five source hashes used in the [earlier Docling-slim trial](DOCLING_MIXED_FORMAT_DEV_RESULT_20261012.md). Each synthetic source contains a three-row, nine-cell order table; the multipart EML has a short plain-text part and an HTML alternative containing that table. This run did not generate or add new fixtures. The [native diagnostic](../../product_eval/mixed_format_native_diagnostic.py) checks all source hashes before parsing. A fresh Python process parses each file and independently reopens the source to resolve every cell locator. The [raw result](MIXED_FORMAT_NATIVE_DEV_RESULT_20261012.json) records all cells, locators, timestamps, process memory, and the fixture manifest.

The run used the same isolated Python 3.11.0 Windows environment as the Docling trial: `python-docx==1.2.0`, `openpyxl==3.1.5`, `python-pptx==1.0.2`, `lxml==6.1.3`, and `psutil==7.2.2`. The [resolved package freeze](locks/docling_slim_mixed_2.138.0_py311_windows.txt) covers the environment. The email parser is Python's standard library. No GPU, model download, or paid API was used.

| Source | Exact cells | Cell locators resolving to exact source text | Locator identity | Fresh-process wall | Parse call including imports | Sampled peak RSS |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| DOCX | 9/9 | 9/9 | Top-level block/table/row/column; two paragraph block locators also checked | 0.365 s | 0.087 s | 53.58 MiB |
| XLSX | 9/9 | 9/9 | Sheet `Order Lines`, table `OrderLines`, address `A1:C3` | 0.492 s | 0.290 s | 41.12 MiB |
| HTML | 9/9 | 9/9 | Absolute DOM XPath per `<th>`/`<td>` | 0.201 s | 0.020 s | 23.63 MiB |
| EML | 9/9 | 9/9 | HTML body MIME path `[1]` plus DOM XPath; subject retained | 0.207 s | 0.019 s | 23.83 MiB |
| PPTX | 9/9 | 9/9 | Slide 1, table shape ID, row/column | 0.358 s | 0.138 s | 41.04 MiB |

Totals are **45/45 exact known cells and 45/45 independently resolved cell locators**. Each source yielded exactly nine cells in the expected order; extra cells would fail the fixture match condition. All 45 have structural identities; **none has a validated PDF-style cell bounding box**. The PPTX parser records the enclosing shape rectangle in slide EMUs, but that is a table region, not a verified individual-cell box. An XLSX address is a sheet-grid position, not rendered geometry. DOM XPath and DOCX block/table positions are exact within the unchanged, source-hashed files but may move after edits or HTML parser normalization.

The earlier Docling-slim trial recovered **36/45 cells** and all of those 36 had table-grid indices; its EML conversion returned zero table cells because the nonempty plain-text part took precedence. Python's [`EmailMessage.get_body`](https://docs.python.org/3/library/email.message.html#email.message.EmailMessage.get_body) supports an explicit `('html', 'plain')` preference and excludes parts marked as attachments when selecting a body. On the frozen EML this selects HTML MIME part `[1]` and recovers its nine cells. The selected part path, not just flattened content, is recorded. This is a narrow fix for this multipart shape; it does not prove general EML or attachment handling.

Fresh-process median in the recorded repeat was 0.358 s, with sampled peak RSS from 23.63 to 53.58 MiB. An immediately preceding exploratory pass on the same five files had a 1.058 s process median, showing material run-to-run variation from import and filesystem-cache effects. These walls include nine independent locator resolutions per file and Python startup; the parse column includes library imports. Docling's published walls and converter-call timings use a different verification path. They should **not** be interpreted as a paired throughput or cost comparison. A 10 ms RSS sampler can miss shorter peaks. The source files are tiny, and no concurrency or warm-worker run was measured.

## Reuse boundary

- `openpyxl` exposes workbook sheet names and cell addresses. This diagnostic uses `read_only=False`, `data_only=False`, `keep_links=False`, and `keep_vba=False`; it contains no formulas, so formula/cached-value behavior was **not tested**. The [official loading guide](https://openpyxl.readthedocs.io/en/3.1/tutorial.html#loading-from-a-file) explains formula-cache and optimized-read tradeoffs. A production adapter needs formula/cached-value policy, merged-range handling, hidden-sheet policy, expansion limits, and support for data outside Excel table objects.
- `python-docx` gives ordered top-level paragraphs/tables and table-grid cells. The [official table guide](https://python-docx.readthedocs.io/en/latest/user/tables.html) warns that merged cells repeat across grid positions and tables can nest. This pilot has neither case. DOCX has no trustworthy page number without a rendering step.
- `python-pptx` exposes slide table cells by row/column and the enclosing shape. Its [table guide](https://python-pptx.readthedocs.io/en/latest/user/table.html) distinguishes merge-origin and spanned cells. This pilot has no merges. Slide-relative shape coordinates are not a PDF page box.
- `lxml` provides [absolute structural XPath](https://lxml.de/6.0/xpathxslt.html) and a parser with `no_network=True` and `huge_tree=False` ([API](https://lxml.de/apidoc/lxml.etree.html)). The diagnostic does not fetch linked resources or run scripts. HTML repair, nested tables, dynamic JavaScript content, and sanitized reviewer rendering need separate handling.
- Python's [`BytesParser` with an explicit policy](https://docs.python.org/3/library/email.parser.html) retains MIME structure and reports defects. The diagnostic selects one inline HTML body and does not traverse attachments. Real EML needs per-part and attachment limits, malformed-MIME handling, address/header policy, and a viewer that does not execute HTML.

The worker limits compressed source bytes to 20 MiB only for this diagnostic. That does not protect against OOXML ZIP expansion, deeply nested structures, excessive table cells, or parser resource exhaustion. Source hash plus native locator should be part of a future evidence contract; a user-facing reviewer must be able to open the relevant sheet, slide, Word table, DOM cell, or MIME part. Adding these extensions to the existing product intake before that contract and adversarial preflight would be premature. After any product extraction implementation, run the user's required fresh **2,000 distinct-source extraction gate** and a diverse mixed-format holdout; these five synthetic conversions do not count as extraction results.

Reproduce from the repository root using the isolated environment:

```powershell
E:\DocAI-Benchmarks\venvs\docling-slim-2.138-mixed\Scripts\python.exe -m product_eval.mixed_format_native_diagnostic evaluate product_eval/fixtures/mixed_format_docling_v1 E:\DocAI-Benchmarks\mixed_format_native_v1.json
E:\DocAI-Benchmarks\venvs\docling-slim-2.138-mixed\Scripts\python.exe -m unittest product_eval.tests.test_mixed_format_native_diagnostic -v
```

Three tests passed in that environment, including source-hash tamper rejection, paragraph locations, and EML part/DOM locations. The tests skip when those optional parser dependencies are absent.
