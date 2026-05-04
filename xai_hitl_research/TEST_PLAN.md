# XAI / HITL Test Plan

> Required by IT4010 Lecture 10: *"Test the system (unit wise, module wise, …) well and get the accuracy rate"*

This document covers the formal test plan for the **XAI** and **HITL** components of the Modular Multi-Agent Document AI system, authored by **Pathirana M.M.** Tests are organised into four levels: unit, module, integration, and acceptance.

---

## 1. Test Strategy

| Level | Purpose | Tools | Pass Criteria |
|---|---|---|---|
| **Unit** | Verify individual functions in isolation | `pytest` | 100% of unit tests pass |
| **Module** | Verify each microservice on its own | `pytest` + FastAPI TestClient | All endpoint tests pass; health check returns 200 |
| **Integration** | Verify cross-service flows through gateway | Live docker-compose stack | End-to-end Q&A returns valid response |
| **Acceptance / Research** | Measure accuracy on labelled benchmark | `xai_hitl_research/benchmark.py` | ≥75% overall accuracy on test set |

---

## 2. Unit Tests

Located in `xai_hitl/tests/`.

| Test ID | Component | What It Verifies | Pass Criteria |
|---|---|---|---|
| U-XAI-01 | `XAIEngine._handle_numerical_question` | Detects "how many years/days/rupees" patterns | Returns non-null for matching questions, null otherwise |
| U-XAI-02 | `XAIEngine._detect_legal_yes_no` | Detects prohibition pattern in "No X shall…" sentences | Returns polarity="no" with source sentence as evidence |
| U-XAI-03 | `XAIEngine._detect_legal_yes_no` | Detects permission pattern in "shall appoint" sentences | Returns polarity="yes" with source sentence as evidence |
| U-XAI-04 | `XAIEngine._retrieve_focused_context` | TF-IDF compresses long docs to top-k sentences | Output length < input length when input > 1500 chars |
| U-XAI-05 | `XAIEngine._handle_yes_no_question` | Falls through to BART when no label-value match | Returns None for conceptual yes/no questions |
| U-XAI-06 | `XAIEngine._get_sentence_relevance_scores` | TF-IDF ranks question-relevant sentences higher | Top result contains question keywords |
| U-XAI-07 | `TableReconstructor.detect_label_value_pairs` | Detects flattened table structure in OCR text | Returns ≥3 pairs for structured input |
| U-HITL-01 | `HITLFeedback.to_dict / from_dict` | Round-trip serialisation preserves all fields | Equal objects after dict round-trip |
| U-HITL-02 | `FeedbackType` / `FeedbackPriority` enums | Valid enum values are accepted | Invalid values raise `ValueError` |

**How to run**:
```bash
docker compose exec xai-hitl python -m pytest xai_hitl/tests/ -v
```

---

## 3. Module Tests (per microservice)

### 3.1 XAI Service (port 8003)

| Test ID | Endpoint | Input | Expected Response |
|---|---|---|---|
| M-XAI-01 | `GET /health` | — | 200 OK, `{"status": "healthy"}` |
| M-XAI-02 | `POST /xai/ask` | numerical question | confidence ≥ 0.85, derivation_tree first step contains "Numerical" |
| M-XAI-03 | `POST /xai/ask` | yes/no legal question | answer starts with "Yes" or "No", evidence_sentences populated |
| M-XAI-04 | `POST /xai/ask` (include_xai=true) | any question | response includes shap_explanation and lime_explanation |
| M-XAI-05 | `POST /xai/explain` | answered question | returns SHAP + LIME, no engine timeout |
| M-XAI-06 | `POST /hitl/feedback` | full feedback object | returns feedback_id, persisted to Postgres |
| M-XAI-07 | `GET /hitl/history?limit=20` | — | returns ≤20 most recent feedback entries |
| M-XAI-08 | `POST /xai/ask` | very long paragraph (>10k chars) | TF-IDF retrieval applied; response ≤ 60s |

### 3.2 Gateway (port 8000)

| Test ID | Endpoint | Input | Expected Response |
|---|---|---|---|
| M-GW-01 | `GET /health` | — | 200 OK |
| M-GW-02 | `POST /api/xai/ask` | valid Q&A request | proxied to XAI, identical response |
| M-GW-03 | `POST /api/auth/login` | valid creds | 200 OK, returns access_token |
| M-GW-04 | CORS preflight | `OPTIONS /api/xai/ask` from cross-origin | 200 OK with `Access-Control-Allow-Origin: *` |

### 3.3 Frontend (port 3000)

| Test ID | Component | What to Verify | Method |
|---|---|---|---|
| M-FE-01 | `dashboard/xai/page.tsx` | Chat persists to sessionStorage | Submit question → reload → messages restored |
| M-FE-02 | `dashboard/xai/page.tsx` | "See How Answer Was Derived" hidden when fallback error | Force XAI timeout → button absent |
| M-FE-03 | `dashboard/xai/explanation/page.tsx` | Lazy XAI loads on tab open | Open tab → SHAP/LIME populated within 3 minutes |
| M-FE-04 | Auth flow | JWT expiry triggers redirect | Set expired token → navigate → redirect to /login |

**How to run module tests**:
```bash
# Bring stack up
docker compose up -d

# Run the integration smoke test
python xai_hitl_research/benchmark.py --timeout 120
```

---

## 4. Integration Tests (full stack)

| Test ID | Scenario | Steps | Pass Criteria |
|---|---|---|---|
| I-01 | Document → Q&A flow | (1) Upload PDF via IDPO (2) Ask question on extracted text via XAI (3) View explanation | All 3 steps succeed; explanation page loads |
| I-02 | HITL feedback loop | (1) Get an XAI answer (2) Submit "incorrect" feedback (3) Query history | Feedback appears in /hitl/history with correct rating |
| I-03 | Volume permissions | Fresh `docker compose up -d --build` on a new machine | All containers report healthy without manual chown |
| I-04 | CORS from external origin | Browser at `http://<host>:3000` calls `http://<host>:8000` | No CORS error in browser console |
| I-05 | XAI timeout fallback | Ask a question and disconnect XAI mid-request | Frontend shows fallback error; button hidden |
| I-06 | Persistent chat across navigation | Send question → navigate to /idpo → return | Messages restored from sessionStorage |

---

## 5. Research / Acceptance Test (Benchmark)

The acceptance test is the formal benchmark in `xai_hitl_research/benchmark.py`. See [RESULTS.md](RESULTS.md) for the experimental design and metrics.

**Pass criteria** (research-grade):
- Overall accuracy ≥ **75%** on the 30-question test set
- Numerical category accuracy ≥ **90%**
- Legal Yes/No polarity accuracy ≥ **85%**
- Average per-question latency ≤ **30 seconds** on M2 Mac (5GB / 6 CPUs allocated to XAI)
- Zero answers that contradict the source document on the Yes/No category

**Execution**:
```bash
python xai_hitl_research/benchmark.py --gateway http://localhost:8000
```

The script writes raw per-question results to `xai_hitl_research/results.json` and prints a summary table to stdout.

---

## 6. Defect Tracking

Defects discovered during testing are tracked in the project GitHub Issues with the label `xai-hitl`. Each defect must include:
- Test ID that surfaced it (e.g. M-XAI-04)
- Reproduction steps
- Expected vs actual behaviour
- Logs snippet from `docker compose logs xai-hitl`

---

## 7. Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Author | Pathirana M.M. | 2026-05-04 | _________ |
| Supervisor | _____________ | __________ | _________ |
| Co-supervisor | _____________ | __________ | _________ |

---

## Appendix A. Software Standards Compliance

Per IT4010 Lecture 10 *"The software must comply with the software development standards"*:

- ✅ **Design diagrams**: Architecture diagrams in `docs/ARCHITECTURE_DEEP_DIVE.md` and `docs/SYSTEM_FLOW.md`
- ✅ **Code conventions**: Python PEP 8 (enforced via `ruff`), TypeScript strict mode
- ✅ **Input validation**: Pydantic schemas at every API boundary; JWT authentication on protected routes
- ✅ **Logging**: Structured JSON logs at INFO level for all services; max 50 MB per file with 5-file rotation
- ✅ **Containerisation**: All services run as non-root users in Docker; no host network access
- ✅ **Health checks**: Every container has a Docker `HEALTHCHECK` directive
- ✅ **Resource limits**: Every container has CPU and memory limits in `docker-compose.yml`
