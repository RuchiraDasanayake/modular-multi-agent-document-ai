# AHMN - Adaptive Hierarchical Memory Network

> Intelligent document processing with automatic policy selection using multi-armed bandits.

**Key Features:**
- **RABI** - Solves cold-start by transferring knowledge from similar contexts
- **DAAF** - Adapts to changing document formats with drift-aware forgetting

---

## Quick Start

```bash
cd ahmn_core
pip install -r requirements.txt

# Run presentation demo (no Docker needed)
python demos/demo.py --mode quick
```

**With full backend:**
```bash
docker-compose up -d              # Start PostgreSQL + Redis
uvicorn main:app --reload         # API at http://localhost:8000
```

---

## Demo Modes

| Mode | Command | Time | Description |
|------|---------|------|-------------|
| **quick** | `python demos/demo.py --mode quick` | ~30s | Presentation demo |
| **full** | `python demos/demo.py --mode full` | ~5min | Statistical comparison |
| **experiment** | `python demos/demo.py --mode experiment` | ~15min | Research validation |

```bash
# Examples
python demos/demo.py --mode quick
python demos/demo.py --mode full --iterations 2000 --seeds 20
python demos/demo.py --mode experiment --algorithm rabi
python demos/demo.py --mode experiment --algorithm daaf
```

**Output:** Console results + `output/` folder with figures (PNG/PDF) and `results.json`

---

## API

```bash
# Get policy recommendation
curl -X POST http://localhost:8000/advice \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "invoice", "vendor": "Acme Corp"}'

# Log outcome
curl -X POST http://localhost:8000/log \
  -H "Content-Type: application/json" \
  -d '{"advice_id": "...", "policy_id_used": "...", "metrics": {"success": true}}'
```

---

## Architecture

```
New Document → Embed (384d) → RABI (prior transfer) → Thompson Sampling → Select Policy
                                                              ↓
                                        Execute → Observe Reward → DAAF (adaptive forget) → Update

Memory: STM (Redis, 30min) → MTM (PostgreSQL, 90d) → LTM (pgvector, permanent)
```

---

## Project Structure

```
modular-multi-agent-document-ai/
├── README.md                       # This file
├── FEATURES_AND_NOVELTIES.md       # Detailed research documentation
├── .env                            # Environment variables
├── .gitignore
│
└── ahmn_core/                      # Core AHMN implementation
    ├── main.py                     # FastAPI application & endpoints
    ├── requirements.txt            # Python dependencies
    ├── docker-compose.yml          # PostgreSQL + Redis setup
    ├── init.sql                    # Database initialization script
    │
    ├── app/                        # Application modules
    │   ├── __init__.py
    │   ├── config.py               # Configuration & hyperparameters
    │   ├── database.py             # Database connection management
    │   ├── schemas.py              # Pydantic request/response models
    │   │
    │   └── services/               # Core algorithms
    │       ├── __init__.py
    │       ├── memory.py           # Three-tier memory service (STM/MTM/LTM)
    │       ├── rabi.py             # RABI: Retrieval-Augmented Bandit Init
    │       ├── drift_forgetting.py # DAAF: Drift-Aware Adaptive Forgetting
    │       ├── embedding.py        # Sentence embedding service (384d)
    │       └── selection_strategies.py  # Thompson Sampling, UCB1, ε-Greedy
    │
    ├── demos/                      # Demonstration suite
    │   ├── __init__.py
    │   └── demo.py                 # Unified demo (quick/full/experiment modes)
    │
    ├── jobs/                       # Background tasks
    │   ├── promote.py              # MTM → LTM promotion job
    │   └── forgetting.py           # DAAF decay application job
    │
    └── output/                     # Generated results

```

---

## Research Contributions

### RABI (Retrieval-Augmented Bandit Initialization)

Transfers priors from similar contexts via k-NN in embedding space:
```
α_init = 1 + Σᵢ wᵢ·(αᵢ - 1),  where wᵢ = softmax(similarity / τ)
```
**Result:** Reduces cold-start regret from O(K) to O(L·d_avg)

### DAAF (Drift-Aware Adaptive Forgetting)

Adapts forgetting rate based on detected drift:
```
γ* = √(Δ² / ln(t)),  where Δ = |mean(recent) - mean(older)|
```
**Result:** Achieves O(√(Δ²·T·ln T)) regret under bounded drift

---

## Verified Results

### Bandit Algorithms (1000 iterations × 10 seeds)

| Algorithm | Accuracy | Regret | p-value |
|-----------|----------|--------|---------|
| Thompson Sampling | 98.5%±0.6% | 7.1±2.7 | <0.0001 |
| UCB1 | 92.0%±1.5% | 38.2±7.0 | <0.0001 |
| Epsilon-Greedy | 95.1%±0.6% | 24.3±2.7 | <0.0001 |
| Random (baseline) | 33.4%±1.3% | 334.3±7.8 | — |

### RABI Cold-Start

| Metric | RABI | Flat Prior | Improvement |
|--------|------|------------|-------------|
| First 10 docs | 48% | 32% | **+50%** |
| Final accuracy | 97.6% | 96.1% | +1.5% |
| p-value | 0.028 | — | Significant |

### DAAF Drift Adaptation (non-stationary environment)

| Algorithm | Accuracy | Regret | p-value |
|-----------|----------|--------|---------|
| DAAF | 51.0%±7.1% | 88.7±11.4 | 0.003 |
| Fixed Forgetting | 48.0%±8.4% | 99.6±15.2 | 0.011 |
| Standard TS | 32.3%±15.4% | 134.4±19.1 | — |

**DAAF achieves 34% regret reduction** vs Standard Thompson Sampling.

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| RABI k | 5 | Number of neighbors |
| RABI τ | 0.5 | Softmax temperature |
| RABI δ | 0.4 | Similarity threshold |
| DAAF window | 50 | Drift detection window |
| DAAF γ_min/max | 0.001 / 0.3 | Forgetting rate bounds |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI |
| Database | PostgreSQL + pgvector |
| Cache | Redis |
| Embeddings | SentenceTransformers (all-MiniLM-L6-v2, 384d) |
| Validation | Pydantic v2 |
| Visualization | Matplotlib |
| Statistics | SciPy |

---

## Requirements

- Python 3.10+
- Docker & Docker Compose (for full backend)
- ~500MB disk space (embedding model)

### Python Dependencies (main)
```
fastapi, uvicorn, psycopg[binary], redis
sentence-transformers, numpy, scipy, matplotlib
pydantic, python-dotenv
```

---

## Documentation

See [FEATURES_AND_NOVELTIES.md](FEATURES_AND_NOVELTIES.md) for:
- Detailed mathematical formulations
- Theoretical analysis and proofs
- Complete hyperparameter justifications
- Full experimental framework documentation

---

## License

MIT
