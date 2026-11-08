# DocAI

A local Windows workspace for turning supported documents into reviewed structured
records. Add files, describe the fields you need, confirm their meaning on a
sample, review the extracted values against the source, and export JSON or JSONL.

## Run locally

The active installation uses a data-drive checkout, local PostgreSQL, a gateway,
one extraction worker, a Next.js frontend and a loopback model server. Docker,
public hosting and cloud API credentials are not required for this local path.

Use the configured **Start DocAI** shortcut, or from the repository:

```powershell
.\scripts\start_local_product.ps1 -ConfigPath 'I:\DocAI\config\local-product.json' -OpenBrowser
.\scripts\stop_local_product.ps1 -ConfigPath 'I:\DocAI\config\local-product.json'
```

The path is an installation example; configuration is private and not committed.
Read the [local setup](scripts/local_product.md) and [native prerequisites](scripts/native_product.md).
The launcher requires an installed model with the configured full digest, verifies
owned processes, and fails visibly on missing resources. It does not download a
model during startup. Keep the model registry unchanged while jobs are running.

## Extract documents

1. Sign in and create an extraction job.
2. Upload files and describe the output. Enter fields or request suggestions.
3. Confirm field meanings, types and repeating groups using representative samples.
4. Run a sample preview and inspect source evidence. Correct or reject proposals.
5. Process the remaining files with the pinned schema, then download reviewed data.

Completed setup and secondary diagnostic information collapse so the current
stage stays clear. Unsaved changes, stale samples and failures remain visible.
The [operator guide](docs/PRODUCT_QUICKSTART.md) explains the review and export gates.

Supported inputs include PDF, single-frame images, UTF-8 text, document-text JSON,
DOCX, XLSX, PPTX, local HTML and email bodies. Each reader has explicit limits;
embedded images in Office files, nested tables and email attachments are not
universally covered. Files are bounded to 20 MiB and PDFs to 50 pages, with further
model budgets. See the [system contract](docs/SYSTEM_CONTRACT.md). Every admitted
source must produce a result or an explicit failure/unsupported state.

## Local models and reproducibility

The [8 November model research](docs/LOCAL_MODEL_RESEARCH_20261108.md) selects
Qwen3.5 4B as the first compact extraction baseline and the recently released
MiniCPM-OCR 1.0 as a specialist trial. LightOnOCR-3 is a later grounded-page
challenger. These selections are hypotheses, not measured accuracy improvements.

New local queue admissions pin explicit sampling/reasoning settings. Run receipts
record those settings and provider fingerprints when supplied. Startup separately
attests the local model manifest digest, model parameters and executable hash.
Fixed settings do not guarantee identical GPU outputs or correct values.

```powershell
python scripts/check_local_model.py --model docai-extract:v1 --repeat 3 --output path\to\new-screen
```

This authored capability screen checks Unicode, duplicate rows and absent fields.
It is not a quality benchmark. The [local product plan](docs/LOCAL_PRODUCT_PLAN.md)
requires held-out comparisons, failure accounting, whole-row metrics, evidence,
latency, memory and review burden before a stronger claim. Local inference has no
per-request provider bill; hardware, electricity and human review still cost money.

## Architecture and evidence

The product path is browser -> authenticated job API -> durable PostgreSQL queue
-> bounded parser/OCR and extraction worker -> revisioned source review -> export.
Filesystem storage is shared on one host. This is not a demonstrated high
availability or distributed deployment.

The adaptive-policy simulator and legacy research services are separate from the
product path. RABI and DAAF do not currently control product document extraction.
Approved recipe reuse currently reuses a reviewed schema; it does not train model
weights or establish a learned routing benefit. Do not promote disconnected
services as active product features.

- [Project direction](docs/PROJECT_DIRECTION.md)
- [Local consolidation and release gates](docs/LOCAL_PRODUCT_PLAN.md)
- [Paired 240-document results](docs/evaluations/QUALITY240_RESULTS_20261014.md)
- [Verified 2,000-original operational study](docs/evaluations/MODEL2000_VERIFIED_OPERATIONAL_20261013.md)
- [Source-only reconstruction](docs/evaluations/quality240_20261014/README.md)
- [Conference submission record](docs/CONFERENCE_HANDOFF_20261017.md)

The submitted studies used a different provider/model. Their results do not
validate the new local installation. Both primary paired macro difference
intervals included zero; the operational gate did not pass. Preserve those
results and evaluate the local product as a new candidate.

## Development

Use an isolated Python environment and the frontend lockfile. Read [AGENTS.md](AGENTS.md)
and [CONTRIBUTING.md](CONTRIBUTING.md) before changes. Keep private documents,
credentials, model weights and runtime output outside Git.

```powershell
python -m pytest idpo/tests/test_product_local_generation.py idpo/tests/test_product_auto_provider_format.py -q
cd frontend
npm run test:server
npx tsc --noEmit
```

MIT license for this repository. Model and dataset licenses are separate and must
be checked before redistribution.
