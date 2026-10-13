# Office XML allocation guard — 13 October 2026

Classification: parser code and regression tests are **core / keep**. This receipt is **supporting / keep**.

## Reproduced defect

The product checked XLSX grid dimensions after `openpyxl.load_workbook` returned. The reader allocates merged cells
and hyperlink ranges during that call. A small ZIP member declaring `A1:XFD1048576` therefore reached an allocating
parser before the 50,000-cell grid check. The upstream [worksheet reader](https://openpyxl.readthedocs.io/en/stable/_modules/openpyxl/worksheet/_reader.html)
and the installed source both show these allocations during worksheet binding.

A synthetic regression substituted a failure sentinel for `openpyxl.load_workbook`. Before the fix, the large-merge
case reached that sentinel and failed. The test never attempted the huge allocation on the live machine.

## Change

After ZIP size, path, encryption, duplicate-member and CRC checks, a standard-library streaming XML preflight now:

- checks actual cell coordinates, merged ranges, hyperlink ranges and comment targets before the Office reader;
- enforces the existing 20,000 explicit-cell and 50,000 sheet-grid budgets, plus a 50,000-cell cumulative range-work
  budget across the package to bound repeated or overlapping range expansion;
- counts worksheet cells in decoded XML, including UTF-16, rather than matching raw ASCII bytes;
- follows worksheet relationship targets, workbook sheet IDs and declared XML parts, including non-`.xml` filenames;
- rejects repeated worksheet references or aliased targets that would multiply work, and bounds Word table cells
  and cumulative column spans before `python-docx` expands them;
- rejects DTDs and entity declarations in decoded XML; caps each XML part at 100,000 elements and depth 128;
- retains explicit unsupported/failed outcomes through the existing product exception handling.

Independent review reproduced another bypass: the library processes worksheet child tags under an unexpected XML
root, accepts unexpected child namespaces for some containers, and treats every direct row child as a cell.
The final guard conservatively budgets these local names and row children in spreadsheet packages. It also follows
sheet IDs even when a relationship type is wrong, and rejects duplicate relationship IDs rather than guessing which
target wins. Separate safe probes confirmed comment-range and Word-column-span allocation before the old checks.

Normal small merged sheets and existing DOCX, XLSX, PPTX, HTML and EML fixture extraction still pass. This change
does not evaluate formulas, fetch hyperlinks or add an external parser dependency. Bounds can reject complex valid
Office files; the product must report that limit rather than silently claim extraction succeeded.

## Validation

Commands run with the product Python environment:

```text
python -s -m pytest idpo/tests/test_product_xlsx_preflight.py idpo/tests/test_product_native_formats.py scripts/tests/test_product_runtime.py -q --disable-warnings
75 passed
```

Targeted Ruff checks passed. Cases include large merge/hyperlink/sparse ranges before parser invocation, UTF-16
cell counting and DTD rejection, a worksheet stored under a `.bin` relationship target with an unknown type,
cumulative range work, unexpected worksheet roots/namespaces, repeated sheet references, comment targets, Word
column spans, XML depth/element bounds, and a valid small merge.
No API/model calls or reserved benchmark references were used.

This is a focused allocation fix, not a comprehensive malicious-file audit. The running 2,000-original and frozen
240-original benchmark checkouts are unchanged; this patch does not alter their predictions or measured candidate.
