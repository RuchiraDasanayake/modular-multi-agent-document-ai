# Product runtime capability preflight

Surface classification: the preflight and tests are **supporting / keep**. They
check the existing product parser paths without changing research extraction.

Run with the exact Python interpreter used by the native worker:

```powershell
& C:\path\to\product-venv\Scripts\python.exe scripts/check_product_runtime.py `
  --native-config C:\private\native-product.json
```

Add `--json` for one machine-readable report. Exit code **0** means all advertised
parser paths passed the synthetic checks and any configured provider has valid
local setup. Exit code **1** means a required path or declared configuration is
unavailable. Run before starting services or accepting files; the script itself
does not change the upload API or extension list.

The native launcher enforces this check before starting services and before
declaring an existing stack ready. It uses a 60-second deadline and saves a
sanitized summary at `runtimeRoot/state/product-capabilities.json`. Failed,
incomplete, inconsistent or timed-out reports block startup. Raw child output is
discarded; the saved report contains only known capability flags, error codes,
timestamp and provider setup state. This receipt records the last startup check;
the launcher's `-Status` option only queries running processes.

The optional `--native-config` reads only the product Python, provider and OCR
settings. It refuses to certify a different interpreter from `pythonPath`.
Without it, the current interpreter and environment are checked. Existing
environment values apply when optional native config fields are absent, matching
the launcher. No API request, package installation, or model download is made.

## What is checked

| Capability | Evidence required |
| --- | --- |
| Product core | Import the actual CLI and product workflow in this interpreter |
| Text and JSON pages | Parse small synthetic inputs through product intake |
| Native PDF text | Read a generated text PDF using `pypdf` and product intake |
| Image OCR | Decode PNG/JPEG/TIFF/BMP and recognize a small English marker using configured Tesseract |
| PDF scan extraction | Working `pypdf`, OCR, and PDFium or the pdf2image/Poppler rasterizer fallback |
| PDF scan schema sampling | Run the actual brief-sampling helper on a generated scan PDF; this path currently requires PDFium |
| DOCX, XLSX, PPTX, HTML, EML | Verify frozen synthetic fixture hashes and parse their nine known table cells through the product native adapter |
| Model client | Construct and close the installed OpenAI-compatible client locally, without sending a request |

The check reuses `find_tesseract_cmd`, `find_poppler_path`, the OCR agent's
Tesseract configuration, and the existing synthetic Office/web/email fixtures.
It does not call the generic research preflight, which checks different optional
engines and may contact Ollama. OCR subprocess probes have explicit timeouts.

The JSON report has `contract_version: 1`, overall `status`, per-check results,
per-capability `ready` flags and `missing_checks`, and a separate `provider` state.
Raw exception messages, configuration values, keys, model names and endpoint URLs
are excluded. Failed checks include a static installation or configuration remedy.

## Optional models and limits

With no model and endpoint configured, provider state is `not_configured`; local
parsing can still pass without the model client. Supplying only one of model or
endpoint fails configuration. Loopback HTTP may be keyless; HTTPS providers require
the configured `ICORE_API_KEY`. A configured provider with a working client is
reported as **`configured_unverified`**, because this check does not verify remote
reachability, credentials, model availability or extraction quality.

Passing tiny synthetic fixtures establishes dependency availability only. Existing
size, page, language, complex-content and image-frame limits still apply. This is
not the 2,000-original-document quality evaluation or a production capacity test.

For a fresh product runtime, install the maintained direct requirements from
`idpo/product_auto/requirements-worker.txt` and install Tesseract with English
language data. Then run `python -m pip check` and this preflight. Missing PDFium
can leave PDF extraction's Poppler fallback working while scanned-PDF schema
sampling remains unavailable; the report keeps those capabilities separate.

Run the source-free regression tests with:

```powershell
python -m pytest scripts/tests/test_product_runtime.py -q
```
