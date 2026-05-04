# AHMN Test Plan

> Required by IT4010 Lecture 10: *"Test the system (unit wise, module wise, …) well and get the accuracy rate"*

This document covers the formal test plan for the **AHMN (Adaptive Hierarchical Memory Network)** policy-routing component of the Modular Multi-Agent Document AI system. Tests are organised into four levels: unit, module, integration, and acceptance.

---

## 1. Test Strategy

| Level | Purpose | Tools | Pass Criteria |
|---|---|---|---|
| **Unit** | Verify Beta-Bernoulli math, RABI prior blending, embedding helpers in isolation | `pytest` | 100% of unit tests pass |
| **Module** | Verify the `/advice`, `/dashboard/*`, `/scheduler/*` endpoints | FastAPI TestClient | All endpoint tests pass |
| **Integration** | Verify cross-service flows (gateway → AHMN → Postgres) | Live docker-compose | End-to-end advice call returns valid policy |
| **Acceptance / Research** | Measure routing accuracy on labelled benchmark | `ahmn_research/benchmark.py` | ≥ 60% overall accuracy after seed-rebalancing fix |

---

## 2. Unit Tests

Located in `ahmn_core/tests/`.

| Test ID | Component | What It Verifies | Pass Criteria |
|---|---|---|---|
| U-AHMN-01 | `RABIPrior.confidence` | Confidence increases with sample count | Monotonic increasing |
| U-AHMN-02 | `RABIInitializer.initialize_prior` | Returns flat prior (α=1, β=1) when no neighbours | Asserted exact values |
| U-AHMN-03 | `RABIInitializer.initialize_prior` | Returns weighted blend when neighbours present | Weighted sum matches manual calc |
| U-AHMN-04 | `RABIThompsonSampling.sample` | Sampled value lies in [0, 1] | Range assertion over 100 samples |
| U-AHMN-05 | `EmbeddingService.create_context_string` | Format matches `"doc_type: X, vendor: Y"` | String contains both keys |
| U-AHMN-06 | `EmbeddingService.generate_embedding` | Returns 384-dim vector for any input | `len(vec) == 384` |
| U-AHMN-07 | LTM seed loader | All 12 seeds insert without conflict | Postgres row count = 12 |

**How to run:**
```bash
docker compose exec ahmn python -m pytest ahmn_core/tests/ -v
```

---

## 3. Module Tests

### 3.1 AHMN Service (port 8001)

| Test ID | Endpoint | Input | Expected Response |
|---|---|---|---|
| M-AHMN-01 | `GET /health` | — | 200 OK, `{"status": "healthy"}` |
| M-AHMN-02 | `POST /advice` | seeded doc_type | Returns matching policy_id, rabi_used=true, confidence ≥ 0.5 |
| M-AHMN-03 | `POST /advice?explore=true` | any context | Thompson Sampling enabled (different draws on repeated call) |
| M-AHMN-04 | `POST /advice/log` | valid OutcomeMetrics | Persists to MTM table |
| M-AHMN-05 | `POST /advice/feedback` | valid FeedbackRequest | Updates Beta-Bernoulli posteriors |
| M-AHMN-06 | `GET /dashboard/memory/ltm` | — | Returns ≥ 12 LTM entries after reseed |
| M-AHMN-07 | `POST /scheduler/promote` | — | Promotes high-confidence MTM rows to LTM |
| M-AHMN-08 | `POST /scheduler/forget` | — | Decays old MTM entries |

### 3.2 Gateway Routing (port 8000)

| Test ID | Endpoint | Verifies |
|---|---|---|
| M-GW-01 | `POST /api/advice` proxy | Routes to AHMN, identical response |
| M-GW-02 | Auth required | 401 without JWT, 200 with valid token |

---

## 4. Integration Tests

| Test ID | Scenario | Pass Criteria |
|---|---|---|
| I-01 | Reseed → query → verify | After `reset_and_seed_db.py`, querying a seeded doc_type returns the seeded policy |
| I-02 | Log feedback → verify learning | Submit 5× successful outcomes for an MTM entry; the corresponding alpha increases |
| I-03 | Cold-start → safe fallback | Submit `doc_type="unknown_xyz_123"`; system returns *some* policy without erroring |
| I-04 | Determinism across restarts | Restart the AHMN container; the same input still returns the same policy |
| I-05 | RABI vector search | Query with a near-neighbour doc_type; `rabi_used=true` and `n_neighbors > 0` |

---

## 5. Research / Acceptance Test (Benchmark)

The acceptance test is the formal benchmark in `ahmn_research/benchmark.py`. See [RESULTS.md](RESULTS.md) for the experimental design.

**Pass criteria** (current iteration):
- Overall routing accuracy ≥ **60%** on the 30-case test set (current: **40%**, with documented fixes that would lift to ~80%)
- Determinism rate = **100%**
- RABI activation rate ≥ **90%**
- Confidence calibration ≥ **80%**
- Average per-call latency ≤ **2 seconds**

**Execution:**
```bash
docker compose exec ahmn python /app/scripts/reset_and_seed_db.py
python3 ahmn_research/benchmark.py --gateway http://localhost:8000
```

Raw per-case results are written to `ahmn_research/results.json`.

---

## 6. Defect Tracking

Defects discovered during testing are tracked in GitHub Issues with the label `ahmn`. Each defect must include:
- Test ID that surfaced it (e.g. M-AHMN-02)
- Reproduction steps
- Expected vs actual behaviour
- Logs snippet from `docker compose logs ahmn`

### Open defects discovered through this benchmark

| ID | Severity | Description | Test that surfaced it |
|---|---|---|---|
| AHMN-D01 | High | Cold-start contexts route to a specialist instead of `default` despite low confidence | benchmark `cold_start` regime |
| AHMN-D02 | Medium | Dense-cluster bias — `table_heavy` over-attracts due to LTM seed imbalance | benchmark `near_neighbor` regime |

Both are documented with proposed fixes in [RESULTS.md §4](RESULTS.md).

---

## 7. Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Author | (AHMN team member name) | 2026-05-04 | _________ |
| Supervisor | _____________ | __________ | _________ |
| Co-supervisor | _____________ | __________ | _________ |

---

## Appendix A. Software Standards Compliance

- ✅ **Design diagrams**: AHMN architecture in `docs/ARCHITECTURE_DEEP_DIVE.md`
- ✅ **Code conventions**: Python PEP 8 (enforced via `ruff`), strict typing (`mypy`)
- ✅ **Input validation**: Pydantic schemas (`DocumentContext`, `OutcomeMetrics`)
- ✅ **Logging**: Structured JSON logs at INFO level
- ✅ **Containerisation**: AHMN runs as non-root `appuser` in Docker
- ✅ **Health checks**: `/health` endpoint with Docker `HEALTHCHECK` directive
- ✅ **Resource limits**: CPU and memory limits in `docker-compose.yml`
- ✅ **Database migrations**: `scripts/init.sql` is idempotent; `reset_and_seed_db.py` is reproducible
