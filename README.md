# IDPO: Multi-Agent Document AI Research Prototype

This repository implements a production-grade research prototype for a domain-agnostic Document AI system. It is fully auditable, multi-agent, preprocessing-aware, and end-to-end from ingestion to provenance export.

## Quick Start

```powershell
python -m pip install -e .
```

### Ingest
```powershell
idpo ingest --input data/synthetic/docs --out runs/ingested.json
```

### Process + Index
```powershell
idpo process --input data/synthetic/docs --run-dir runs/demo
```

To inject domain-specific extraction rules and policy routing, provide a config file via `--config` (see `PipelineConfig.structuring.extraction_rules` and `PipelineConfig.knowledge`). A sample config is in `configs/sample_config.json`.

### Simple Output Layout
```powershell
idpo process-simple --input data/demo_inputs --config configs/sample_config.json
```

This writes all outputs to `data/demo_inputs/output/`, including `entities.xlsx` (or CSV fallback), raw categorized files, and `text_extracted/` per file.

### Query
```powershell
idpo query --run-dir runs/demo --question "What is the total charge?" --doc-id doc_001
```

### Evaluate
```powershell
idpo evaluate --input data/synthetic/docs/synthetic_documents.json --run-dir runs/eval
```

### Export Provenance
```powershell
idpo export-provenance --run-dir runs/demo --out runs/demo/provenance_export.json
```

### Scanned Documents (OCR)

To process scanned images or PDF pages, install OCR extras:

```powershell
python -m pip install -e ".[ocr]"
```

You also need the Tesseract OCR binary installed and available on PATH. PDF OCR via Pillow may require a PDF renderer (e.g., Ghostscript/Poppler).

For best PDF OCR reliability, install Poppler and `pdf2image` (included in `.[ocr]`) so pages can be rasterized before OCR.

## Excel Export (Optional)

```powershell
python -m pip install -e ".[excel]"
```

This enables the multi-sheet `entities.xlsx` export. If the Excel extras are not installed, the pipeline writes three CSV files instead.

## Outputs

- `runs/<run-id>/artifacts/` contains raw and cleaned artifacts.
- `runs/<run-id>/provenance.jsonl` is the append-only audit log.
- `runs/<run-id>/index/` contains vector + lexical indexes.
- `runs/<run-id>/results.json` stores per-document structured outputs.
- `runs/<run-id>/entities.xlsx` stores explicit entities, default entities, and extraction metadata (CSV fallback if Excel extras are not installed).
- `runs/<run-id>/evaluation.json` stores evaluation metrics (when run).

## Documentation

- `docs/architecture.md` for the pipeline, agents, and data flow.
- `data/synthetic/docs/` includes optional example documents; the core pipeline is domain-agnostic and driven by config.
