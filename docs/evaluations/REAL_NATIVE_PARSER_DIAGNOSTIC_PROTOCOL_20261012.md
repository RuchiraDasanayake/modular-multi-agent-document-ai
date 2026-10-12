# Frozen real-source native parser diagnostic — 2026-10-12

**Purpose:** test parser feasibility on the ten [frozen real public development files](NATIVE_REAL_PUBLIC_DEV_CORPUS_20261012.md), exactly two each in DOCX, XLSX, PPTX, HTML, and EML. This is a `research_evidence` addition with the primary action **keep**. It does not call an extraction model, derive a schema, score fields or linked rows, or use gold labels. Its outcomes must not be called extraction accuracy.

**Freeze boundary:** commit this protocol and [`product_eval/real_native_parser_diagnostic.py`](../../product_eval/real_native_parser_diagnostic.py) before invoking the `evaluate` command. Record the commit, script SHA-256, and manifest SHA-256 with the result. Do not change parser code, the manifest, sample rule, or resource limits after observing outcomes; a change is a new arm.

## Inputs and rights

- The [manifest](NATIVE_REAL_PUBLIC_DEV_MANIFEST_20261012.json) pins exact bytes and source URLs. The diagnostic refuses any changed, missing, or extra corpus file, and verifies the two EML derivatives against their raw archive responses. It reads no ExtractBench holdout or personal user document.
- The ASF `.eml` messages are **local research only**. The command requires `--include-eml-local-only`; neither source content nor message headers are written to the report. Do not transfer them to ICORE or another cloud provider, publish the bytes, or use them for training without a further rights review. The [ASF archive policy](https://www.apache.org/foundation/public-archives.html) and [research guidance](https://apache.org/research/) support public-archive research, while an explicit licence for the message authors' content remains unverified.
- GOV.UK's [reuse terms](https://www.gov.uk/help/terms-conditions) describe OGL v3 coverage with exceptions. Embedded third-party material in the Office files has not been individually audited; keep source files outside Git.

## Frozen execution

From the repository root, after the shared 2,000-document gate and TableMagic acquisition have stopped, set the local paths outside Git and run one sequential local process at a time:

```powershell
python -m product_eval.real_native_parser_diagnostic evaluate `
  --corpus-dir $env:NATIVE_DEV_CORPUS_DIR `
  --output $env:NATIVE_DEV_REPORT_PATH `
  --include-eml-local-only `
  --timeout-seconds 120 `
  --max-rss-mib 1024 `
  --min-available-mib 3072
```

The script performs all hash checks before importing the product parser. Each source then enters a fresh Python worker running `parse_native_document(path, source_hash)`. Workers are sequential, have a 120-second per-file timeout, and are killed if the parent's sampled worker RSS exceeds 1,024 MiB. The run skips later files if available RAM drops below 3,072 MiB. These are sampled safeguards, **not a guaranteed OS memory ceiling**; short spikes and third-party allocator memory may escape sampling. The ten input files total 1.61 MB; the source parser additionally bounds OOXML expansion at 64 MiB, source text at 250,000 characters, table cells at 10,000, and HTML at 2 MiB. Actual run time and peak RSS remain unknown until execution. At worst, the timeout budget is 20 minutes for ten sources, plus process startup and validation. No GPU, model download, API call, or network request is part of this command.

The result JSON contains source IDs/hashes, parser identity and version, status, timing, sampled RSS, source-unit count and text length, table/cell counts, locator coverage, text-span integrity, and a deterministic source-locator sample. It contains no extracted text, email headers, or raw source bytes. If a worker fails or times out, its per-file status records that fact and the remaining workers proceed when memory permits. `NativeLimitError` is `unsupported`; other parser exceptions are `failed`.

## Evidence checks and interpretation

For every successfully parsed file, compare product pages to `ParsedDocument.units`, inspect every table cell's JSON native locator and text span, and require nonempty cell text to equal its source-unit span and quote. Then sample up to 16 cells evenly across **all** cells, including the first and last. Reopen the original with a separate native reader and resolve each sampled DOCX block/cell, XLSX sheet/address, PPTX slide/shape/cell, or HTML/EML DOM path back to text. A cell with no locator is counted as a sample failure. Empty tables give `sampled_cells=0`, which supplies no locator evidence. No pixel boxes are expected or invented for these formats.

A `parsed` status means those structural consistency checks passed on that file. It does **not** mean important information was captured, a schema was right, a row was linked, or a field value was semantically correct. `parsed_with_integrity_mismatch`, `unsupported`, `failed`, `timeout`, `sampled_rss_limit`, or `not_run_low_memory` block parser promotion pending diagnosis. Report per-format counts and failures; do not average away unsupported sources. This set is small, geographically concentrated, and has no independent labels. The existing product 2,000-source PDF gate is a separate requirement and cannot substitute for native-format quality evaluation.
