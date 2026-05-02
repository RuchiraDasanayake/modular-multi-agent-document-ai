# Setup Guide

Estimated fresh-machine setup time: **30–60 min** (mostly downloads).

---

## 1. Prerequisites (install once, system-wide)

| Tool | Version | Where |
|------|---------|--------|
| Python | **3.10.x** (not 3.11/3.12/3.13 — PaddleOCR requires 3.10) | python.org |
| Node.js | 18+ | nodejs.org |
| Tesseract OCR | 5.x | UB Mannheim installer (Windows): https://github.com/UB-Mannheim/tesseract/wiki |
| Ollama | latest | ollama.com |
| Git LFS | latest | git-lfs.com (for dataset images) |

---

## 2. Clone and Python env

```bash
git clone <repo-url>
cd IDPO

# Must be Python 3.10 — verify first
python --version   # should print 3.10.x

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

---

## 3. Tesseract path (Windows)

After installing Tesseract, add it to PATH or set in config:

```bash
# Verify it works
tesseract --version
```

Default install path: `C:\Program Files\Tesseract-OCR\tesseract.exe`

---

## 4. Ollama + model

```bash
# Pull the model used in research (~6.6 GB download)
ollama pull qwen3.5:9b

# Verify
ollama list   # should show qwen3.5:9b
```

Ollama must be **running** during benchmarks. Start it with `ollama serve` if not running as a service.

---

## 5. PaddleOCR models (auto-download on first run)

First time `process-inbox` runs a scanned image, PaddleOCR downloads ~80 MB of model weights to `~/.paddleocr/`. No manual step needed — just needs internet on first run.

---

## 6. Frontend

```bash
cd frontend
npm install
npm run dev     # dev server on localhost:3000
```

Data directory defaults to `../../idpo-data/` relative to the frontend folder. Override with env var `IDPO_DATA_DIR`.

---

## 7. Run a benchmark

```bash
# Use the existing persistent CORD job
python scripts/run_idpo_benchmark.py \
  --pack datasets/cord_pack_5.json \
  --config configs/idpo_research_config.json \
  --benchmark-job-id <job-id-from-frontend>
```

---

## Key config files

| File | Purpose |
|------|---------|
| `configs/idpo_research_config.json` | Main research config (OCR engine, AHMN, LLM, policies) |
| `configs/policy_store_research.json` | Policy definitions |
| `configs/config.json` | Default pipeline config |

---

## What runs where

- **LLM**: Ollama local (qwen3.5:9b) — must be running
- **OCR**: PaddleOCR 2.9.1 (CPU) → Tesseract fallback
- **AHMN**: In-process Thompson Sampling (no server needed)
- **Frontend**: Next.js dev server on :3000
- **Backend API**: None — frontend reads/writes files directly

---

## Troubleshooting

**PaddleOCR crashes or won't import**: Must use Python 3.10. Python 3.11+ breaks paddlepaddle.

**`tesseract not found`**: Add Tesseract install dir to PATH, or set `TESSDATA_PREFIX` env var.

**`ollama: connection refused`**: Run `ollama serve` in a separate terminal.

**Benchmark shows Tesseract in results**: The benchmark subprocess auto-resolves to `.venv/Scripts/python.exe`. If PaddleOCR still not used, check `ocr_engine` in `configs/idpo_research_config.json` — should be `"paddle"`.
