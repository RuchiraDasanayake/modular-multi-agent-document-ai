# Native HTML recovery and cell-cap development arm (2026-10-12)

This is a parser-only development result, not an extraction-accuracy result. The ten raw files and manifest are the frozen local corpus in `NATIVE_REAL_PUBLIC_DEV_CORPUS_20261012.md`. The diagnostic used no model, gold labels, network calls, or holdout files. The machine report is `E:\DocAI-Benchmarks\native-real-public-dev-html-recover-cap20k-arm-20261012.json` (`protocol=real_native_parser_only_html_recover_cap20k_arm_v1`, `arm_id=html_recover_cap20k_20261012`, `diagnostic_sha256=274f7ca90d3b00966552c5ddb9dcc9b59795f7ad5d2b68ba4d4bd54666b377a7`, report SHA-256 `3196c43753d8b0be36480d1080de667a692306022bf4c1688ee575bdda752384`). The earlier report at `E:\DocAI-Benchmarks\native-real-public-dev-result-20261012.json` remains unchanged.

## Root cause and choice

Both real GOV.UK HTML pages failed under `lxml.etree.HTMLParser(recover=False)` because ordinary HTML5 elements such as `<header>` were logged as invalid by the underlying parser. The failures occurred at lines 177 and 206. With `recover=True`, both pages parsed within the existing 2 MiB byte and 20,000-element bounds. This is [lxml's documented default for HTMLParser](https://lxml.de/apidoc/lxml.etree.html#lxml.etree.HTMLParser). The parser still uses `no_network=True` and `huge_tree=False`.

For comparison, a local research-only install of [html5lib 1.1](https://html5lib.readthedocs.io/en/stable/) parsed the same two pages with its lxml tree builder. Both options found 3/2 tables and 36/18 table cells. On this host, lxml recovery took 2.0/1.8 ms to build the two trees; html5lib took 42.9/32.2 ms. These two pages do not establish general parser equivalence. Keeping lxml avoids a second runtime dependency and preserves the existing XPath locator contract.

The prior HTML text walk inserted newlines around every inline element, splitting `Invoice INV-42 due today.` into fragments. The revised walk preserves spaces within inline phrases and adds line breaks at block boundaries. Script, style, noscript, template, SVG, canvas, `hidden`, `aria-hidden=true`, hidden input, and simple inline `display:none`/`visibility:hidden` subtrees are excluded from prose and cell text. Hidden table sections and rows are excluded as well. External CSS and class-based visibility are not evaluated; GOV.UK navigation and other visible site chrome remain in the parsed text.

The second real-source failure was a 11,460-cell XLSX against the former 10,000-cell cap. Raising the cumulative cap to 20,000 parsed table cells admitted this file. The archive size, compression, per-sheet grid, total text, and other limits still apply. A focused boundary test checks exactly-at-cap success and one-over-cap rejection across sheets.

## Measured result

| Measure | Frozen baseline | New arm |
| --- | ---: | ---: |
| Real files parsed | 7/10 | 10/10 |
| HTML files parsed | 0/2 | 2/2 |
| Large XLSX parsed | 0/1 | 1/1 |
| Sampled source cell locators resolved exactly | 53/53 on baseline parsed files | 101/101 |
| HTML tables/cells, two files | unavailable | 5 tables / 54 cells |
| Large XLSX cells | unsupported | 11,460 |

The new arm's large XLSX parse took 0.5625 s and sampled 69.46 MiB worker RSS; all 11,460 cells had exact generated-text spans. The two HTML parses took 0.0160/0.0161 s in the product parser, with 16/16 sampled source locators resolving exactly on each. Three HTML table cells contain no visible text, so they correctly have no nonempty text span. The diagnostic checks source identity, parser coverage, text spans, and sampled native locators. It does not measure field, row, schema, or document extraction quality.

Validation: 59 relevant Python product and diagnostic tests passed; `git diff --check` passed. Full Ruff on the touched paths still reports the existing `I001` import-format and `TRY004` ValueError-vs-TypeError findings in `native_formats.py`; this arm introduced no new Ruff finding.
