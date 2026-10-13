# Reproducing the Paper Results

This guide rebuilds the benchmark packs, reruns the static vs `adaptive_safe` comparison, and regenerates every number in
`paper/ieee/main.tex`. The frozen results and the run folders they came from are listed in `paper/FINAL_EVIDENCE.md`.

## Reference platform

| Item | Version used for the paper |
| --- | --- |
| CPU / RAM / GPU | Intel Core i5-12400F, 16 GB RAM, NVIDIA RTX 5060 Ti 16 GB |
| OS | Windows 11 |
| Python | 3.10.10 (PaddlePaddle 2.6.2 does not support newer Python versions) |
| OCR | PaddleOCR 2.9.1 on PaddlePaddle 2.6.2 (CPU); Tesseract 5.4 installed as the fallback engine |
| LLM | Ollama 0.35.1 serving `qwen3.5:9b` (9.7B parameters, Q4_K_M) |

Accuracy in the static condition is deterministic in practice: two separate rounds of runs gave identical numbers on
every pack. Adaptive routing samples from unseeded Beta posteriors with four documents in flight, so policy counts and
adaptive accuracy vary between runs. Latency depends on the hardware.

## 1. Environment

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
ollama pull qwen3.5:9b
```

Install Tesseract 5 and make sure `tesseract` is on `PATH` (see `SETUP.md`).
The historical `scripts/build_hard_docs_pack.py` generator additionally imports PyMuPDF (`fitz`) to create one
synthetic text-layer PDF. It is no longer a default product dependency. Install it separately only if rebuilding
that historical pack, subject to its [AGPL/commercial license](https://artifex.com/blog/pymupdf-acquired-by-artifex).

## 2. Datasets

Neither dataset is committed.

- **CORD v2**: download the parquet files of
  [naver-clova-ix/cord-v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2) into
  `datasets/external/cord-v2/data/`. Only `validation-*.parquet` is needed.
- **FUNSD**: download [FUNSD](https://guillaumejaume.github.io/FUNSD/) and place the test split so that
  `datasets/FUNSD/testing_data/images/` and `datasets/FUNSD/testing_data/annotations/` exist.

## 3. Benchmark packs

The pack files in `datasets/` are tracked; the builders below recreate the images they reference.

```powershell
# CORD images for the development pack (cord_pack_50.json) and the 100-receipt pool used by the holdout
.venv\Scripts\python scripts\build_cord_benchmark_pack.py --split validation --limit 50 --seed 17
.venv\Scripts\python scripts\build_cord_benchmark_pack.py --split validation --limit 100 --seed 17

# Holdout: the 50 validation receipts that are not in the development sample
.venv\Scripts\python scripts\build_cord_holdout_pack.py

# FUNSD-20 (reads datasets/FUNSD/testing_data)
.venv\Scripts\python scripts\build_funsd_pack.py

# HARD-13: six synthetic hard documents plus four CORD receipts and three FUNSD forms
.venv\Scripts\python scripts\build_hard_docs_pack.py
```

`build_hard_docs_pack.py` needs the Windows fonts Arial, Consolas, Times New Roman, Courier New and Segoe Print. On
other systems, point it at a folder that contains them with `--font-dir`. Every random source in it is seeded.

| Pack | Documents | Labelled values | Job scope |
| --- | --- | --- | --- |
| `datasets/cord_pack_50.json` (CORD-dev) | 50 | 160 | one job per condition |
| `datasets/cord_holdout_50.json` (CORD-holdout) | 50 | 180 | one job per condition |
| `datasets/funsd_pack_20.json` (FUNSD-20) | 20 | 47 | one job per condition |
| `datasets/hard_docs_13.json` (HARD-13) | 13 | 51 | one job per document |

## 4. Benchmarks

Run each pack once. Every run processes all documents in both conditions and writes
`<IDPO_DATA_DIR>/runs/benchmarks/benchmark_<id>/paper_evidence.json` (by default `IDPO_DATA_DIR` is the `idpo-data`
folder next to the repository).

```powershell
.venv\Scripts\python scripts\run_idpo_benchmark.py --pack datasets\cord_pack_50.json --config configs\idpo_research_config.json
.venv\Scripts\python scripts\run_idpo_benchmark.py --pack datasets\cord_holdout_50.json --config configs\idpo_research_config.json
.venv\Scripts\python scripts\run_idpo_benchmark.py --pack datasets\funsd_pack_20.json --config configs\idpo_research_config.json
.venv\Scripts\python scripts\run_idpo_benchmark.py --pack datasets\hard_docs_13.json --config configs\idpo_research_config.json
```

On the reference machine the four runs took about 10, 9.5, 5 and 10 minutes. Latency is part of the results, so keep
the machine otherwise idle. Memory is the main operational risk on a 16 GB machine: PaddleOCR holds about 2 GB, and on
Windows Ollama's model runner (`llama-server`) committed about 10 GB of host memory in addition to GPU memory. One early
run failed when the system ran short of committable memory and the model runner stopped responding, so close other
large applications before starting.

## 5. Aggregation

```powershell
$b = "..\idpo-data\runs\benchmarks"
.venv\Scripts\python scripts\aggregate_benchmark_evidence.py --rescore `
  "CORD-dev=$b\benchmark_<dev>\paper_evidence.json" `
  "CORD-holdout=$b\benchmark_<holdout>\paper_evidence.json" `
  "CORD-100=$b\benchmark_<dev>\paper_evidence.json,$b\benchmark_<holdout>\paper_evidence.json" `
  "FUNSD-20=$b\benchmark_<funsd>\paper_evidence.json" `
  "HARD-13=$b\benchmark_<hard>\paper_evidence.json"
```

The script prints micro precision, recall and F1, mean document F1, perfect documents, validation pass rate and mean
latency per condition, then the paired adaptive-minus-static differences with 95% bootstrap intervals (10,000
resamples, seed 17) and the adaptive policy distribution. `--rescore` recomputes every document's counts with the
current scorer from the saved run artifacts. It matters only for evidence written before the date-aware and
repeated-thousands-separator scoring rules were added; fresh runs already use them.

The per-field error breakdown and the comparison of the label-free reward with exact accuracy read the same files:

```powershell
.venv\Scripts\python scripts\analyze_benchmark_errors.py `
  "CORD-100=$b\benchmark_<dev>\paper_evidence.json,$b\benchmark_<holdout>\paper_evidence.json" `
  "FUNSD-20=$b\benchmark_<funsd>\paper_evidence.json" `
  "HARD-13=$b\benchmark_<hard>\paper_evidence.json"
```

For each condition it counts correct, wrong and missed labelled values per field and the values returned for fields
the document does not label, using the current scorer. It then prints the Pearson correlation between the reward and
exact document F1 and how many documents the reward counted as a success despite a wrong or missing value.
`--imperfect` also lists every document with document F1 below 1.

## 6. Policy-learning simulation (RABI and DAAF)

```powershell
.venv\Scripts\python -m ahmn_core.experiments.run_experiments
.venv\Scripts\python -m ahmn_core.experiments.analysis
```

The first command runs 7 methods on 4 synthetic scenarios with 30 seeds each, plus three ablations, and writes
`ahmn_core/output/experiment_results.json` and `experiment_curves.json` (about a minute on the reference machine).
Each seed fixes both the NumPy and the Python random generators, so a re-run reproduces the regret tables exactly.
The second command prints the summary tables. These are simulation results only: RABI and DAAF are not active in the
measured runtime.

## 7. Paper

`paper/ieee/main.tex` is a single IEEEtran file with an inline bibliography, and `paper/ieee/main.pdf` is the compiled
six-page version. Rebuild it with [Tectonic](https://tectonic-typesetting.github.io/) (`tectonic paper\ieee\main.tex`),
with `pdflatex` (run twice), or by uploading the file to Overleaf.

## Smoke test of the deployed demo

`scripts/run_public_demo_smoke.ps1` signs in through the gateway before it calls the job API. Set `SMOKE_PASSWORD` (or
`ADMIN_PASSWORD`) and, if the account is not `admin`, `SMOKE_USERNAME`. See `docs/PUBLIC_DEMO_DEPLOYMENT.md`.
