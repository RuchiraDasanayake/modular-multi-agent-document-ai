"""
AHMN Microservice — Adaptive Hierarchical Memory Network

Exposes policy recommendation (advice), dashboard analytics, and experiment
demo endpoints as a standalone FastAPI service.

Component Owner: Dasanayake D.R.L.
"""

import asyncio
import os
import json
import uuid
import random
import hashlib
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from psycopg_pool import AsyncConnectionPool

from .schemas import (
    DocumentContext,
    PolicyResponse,
    OutcomeMetrics,
    LogRequest,
    FeedbackRequest,
    ReviewFeedbackRequest,
)
from .seeds import LTM_SEEDS
from .services.embedding import EmbeddingService
from .services.rabi import (
    RABIInitializer,
    NeighborInfo,
    create_rabi_for_production,
)
from .services.drift_forgetting import DriftEstimator, DriftType
from .services.scheduler import AHMNScheduler

# psycopg async connections on Windows require Selector event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def _blended_reward(metrics: OutcomeMetrics) -> float:
    """Blend the F1 proxy with policy-independent quality signals.

    The base F1 is computed against a canonical doc-type schema (reward.py),
    so it is already less circular than policy.explicit_entities. We further
    rebalance by weighting grounding_coverage (independent of policy) more
    heavily, and penalising hallucinations (extractions outside the canonical
    or policy-declared target set) harder.

    Weights rationale:
      - base F1:              contributes 0..1 directly (primary quality signal)
      - grounding bonus:      up to +0.15 — values must be locatable in source
      - schema_valid bonus:   +0.05 — all required fields present, no hallucinations
      - missing penalty:      up to −0.15 — stronger than before to punish under-extraction
      - hallucination penalty: up to −0.25 — stronger than before to punish over-extraction
      - defer/latency:        small negative shapers, unchanged
    """
    base = float(metrics.f1_score)
    reward = base
    if metrics.schema_valid:
        reward += 0.05
    reward -= min(float(metrics.missing_required_count or 0) * 0.05, 0.15)
    reward -= min(float(metrics.hallucinated_field_count or 0) * 0.06, 0.25)
    reward += min(float(metrics.grounding_coverage or 0.0) * 0.15, 0.15)
    if metrics.defer_status == "requested":
        reward -= 0.10
    elif metrics.defer_status == "blocked":
        reward -= 0.15
    latency_penalty = max(float(metrics.processing_time_ms or 0.0) - 2500.0, 0.0)
    reward -= min(latency_penalty / 10000.0, 0.08)
    return max(0.0, min(1.0, reward))


def _build_context_string(document_context: dict[str, Any]) -> str:
    return _embedding_service.create_context_string(
        document_context.get("doc_type", "unknown"),
        document_context.get("vendor"),
        document_context.get("content_profile"),
        document_context.get("extra_context")
        if isinstance(document_context.get("extra_context"), dict)
        else document_context,
    )


def _context_hash_for(policy_id: str, document_context: dict[str, Any]) -> str:
    ctx_str = _build_context_string(document_context)
    return hashlib.sha256(f"{ctx_str}:{policy_id}".encode()).hexdigest()

# ─── Configuration ───────────────────────────────────────────────────────────

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
SEED_MODE = os.getenv("AHMN_SEED_MODE", "seeded").strip().lower() or "seeded"
ADVICE_SELECTION_MODE = (
    os.getenv("AHMN_ADVICE_SELECTION_MODE", "thompson").strip().lower() or "thompson"
)
RABI_TRANSFER_DECAY_RATE = min(
    1.0,
    max(0.0, float(os.getenv("AHMN_RABI_TRANSFER_DECAY_RATE", "0.05"))),
)

# ─── Globals ─────────────────────────────────────────────────────────────────

_pool: AsyncConnectionPool | None = None
_redis: aioredis.Redis | None = None

_embedding_service = EmbeddingService()
_rabi = create_rabi_for_production(k=5, similarity_threshold=0.4, temperature=0.5)
_drift_estimators: dict[str, DriftEstimator] = {}
_scheduler: AHMNScheduler | None = None
_RESULTS_DIR = Path(__file__).resolve().parent / "output"
_VALID_SELECTION_MODES = {"thompson", "deterministic"}


def _normalize_selection_mode(raw: str | None, default: str = "thompson") -> str:
    mode = (raw or default).strip().lower()
    return mode if mode in _VALID_SELECTION_MODES else default


def _resolve_selection_mode(request: Request) -> str:
    mode = request.query_params.get("mode")
    if mode:
        return _normalize_selection_mode(mode, default=ADVICE_SELECTION_MODE)

    explore = request.query_params.get("explore")
    if explore is not None:
        return "thompson" if explore.lower() == "true" else "deterministic"

    return _normalize_selection_mode(ADVICE_SELECTION_MODE)


def _policy_score(
    alpha: float,
    beta: float,
    selection_mode: str,
    rng: random.Random | None = None,
) -> float:
    if selection_mode == "deterministic":
        return alpha / (alpha + beta)
    _rng = rng if rng is not None else random
    return _rng.betavariate(alpha, beta)


def _as_metrics_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_rabi_transfer_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    base_alpha = max(0.0, float(value.get("base_alpha", 0.0) or 0.0))
    base_beta = max(0.0, float(value.get("base_beta", 0.0) or 0.0))
    observed_count = max(0, int(value.get("observed_count", 0) or 0))
    if base_alpha <= 0.0 and base_beta <= 0.0:
        return None
    return {
        "base_alpha": base_alpha,
        "base_beta": base_beta,
        "observed_count": observed_count,
    }


def _transfer_retention(observed_count: int) -> float:
    return (1.0 - RABI_TRANSFER_DECAY_RATE) ** max(0, observed_count)


def _effective_transfer(state: dict[str, Any], observed_count: int | None = None) -> tuple[float, float]:
    count = state["observed_count"] if observed_count is None else observed_count
    retention = _transfer_retention(count)
    return (
        state["base_alpha"] * retention,
        state["base_beta"] * retention,
    )


def _build_rabi_transfer_state(
    base_alpha: float,
    base_beta: float,
    observed_count: int,
) -> dict[str, Any] | None:
    state = _normalize_rabi_transfer_state(
        {
            "base_alpha": base_alpha,
            "base_beta": base_beta,
            "observed_count": observed_count,
        }
    )
    if not state:
        return None
    effective_alpha, effective_beta = _effective_transfer(state)
    return {
        **state,
        "decay_rate": RABI_TRANSFER_DECAY_RATE,
        "effective_alpha": round(effective_alpha, 6),
        "effective_beta": round(effective_beta, 6),
    }


def _apply_observation_deltas(
    alpha: float,
    beta: float,
    validation_metrics: Any,
    success_delta: float,
    failure_delta: float,
    gamma: float | None = None,
) -> tuple[float, float, dict[str, Any]]:
    updated_metrics = _as_metrics_dict(validation_metrics)
    base_alpha = float(alpha)
    base_beta = float(beta)

    state = _normalize_rabi_transfer_state(updated_metrics.get("rabi_transfer"))
    if state:
        current_transfer_alpha, current_transfer_beta = _effective_transfer(state)
        own_successes = max(0.0, base_alpha - 1.0 - current_transfer_alpha)
        own_failures = max(0.0, base_beta - 1.0 - current_transfer_beta)
        next_state = _build_rabi_transfer_state(
            state["base_alpha"],
            state["base_beta"],
            state["observed_count"] + 1,
        )
        assert next_state is not None
        next_transfer_alpha = float(next_state["effective_alpha"])
        next_transfer_beta = float(next_state["effective_beta"])
        base_alpha = 1.0 + own_successes + next_transfer_alpha
        base_beta = 1.0 + own_failures + next_transfer_beta
        updated_metrics["rabi_transfer"] = next_state

    if gamma is not None and gamma > 0.001:
        base_alpha = (1.0 + (1.0 - gamma) * (base_alpha - 1.0)) + success_delta
        base_beta = (1.0 + (1.0 - gamma) * (base_beta - 1.0)) + failure_delta
    else:
        base_alpha += success_delta
        base_beta += failure_delta

    return base_alpha, base_beta, updated_metrics


async def _update_ltm_entry(
    cur,
    context_hash: str,
    policy_id: str,
    success_delta: float,
    failure_delta: float,
    *,
    gamma: float | None = None,
    confidence_bump: float = 0.05,
    metrics_patch: dict[str, Any] | None = None,
) -> bool:
    await cur.execute(
        """SELECT id, alpha, beta, validation_metrics
           FROM ltm_validated_policies
           WHERE context_hash = %s AND policy_id = %s""",
        (context_hash, policy_id),
    )
    row = await cur.fetchone()
    if not row:
        return False

    row_id, alpha, beta, validation_metrics = row
    new_alpha, new_beta, merged_metrics = _apply_observation_deltas(
        alpha,
        beta,
        validation_metrics,
        success_delta,
        failure_delta,
        gamma,
    )
    if metrics_patch:
        merged_metrics.update(metrics_patch)

    await cur.execute(
        """UPDATE ltm_validated_policies
           SET alpha = %s,
               beta = %s,
               validation_metrics = %s::jsonb,
               confidence_score = LEAST(1.0, confidence_score + %s),
               last_promoted_at = NOW()
           WHERE id = %s
           RETURNING id""",
        (
            new_alpha,
            new_beta,
            json.dumps(merged_metrics),
            confidence_bump,
            row_id,
        ),
    )
    return await cur.fetchone() is not None

async def _register_vector(conn) -> None:  # type: ignore[override]
    """Register pgvector type on new connections (async callback)."""
    try:
        from pgvector.psycopg import register_vector_async  # type: ignore[import-untyped]

        await register_vector_async(conn)
    except Exception:
        pass

def _db() -> AsyncConnectionPool:
    """Return the connection pool, raising if not yet initialised."""
    assert _pool is not None, "Database pool not initialised"
    return _pool

def _rds() -> aioredis.Redis:
    """Return the Redis client, raising if not yet initialised."""
    assert _redis is not None, "Redis client not initialised"
    return _redis

def _get_drift_estimator(key: str) -> DriftEstimator:
    if key not in _drift_estimators:
        _drift_estimators[key] = DriftEstimator(
            window_size=50,
            min_samples=10,
            drift_threshold=0.05,
            abrupt_threshold=0.15,
        )
    return _drift_estimators[key]

def _load_json(name: str) -> dict | None:
    p = _RESULTS_DIR / name
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None

def _user(request: Request) -> dict:
    """Extract user context from gateway-forwarded headers."""
    return {
        "id": request.headers.get("X-User-Id", "anonymous"),
        "role": request.headers.get("X-User-Role", "viewer"),
    }

# ─── Lifespan ────────────────────────────────────────────────────────────────

# ── LTM Seed Data ─────────────────────────────────────────────────────────
# Seed data is now defined in ahmn_core.seeds module

async def _seed_ltm_if_empty() -> None:
    """Seed LTM with initial policy knowledge so AHMN can give informed advice from day one."""
    if SEED_MODE in {"unseeded", "disabled", "off", "false", "0"}:
        logger.info("AHMN seed mode '%s' - skipping LTM startup seed", SEED_MODE)
        return
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM ltm_validated_policies")
            count = (await cur.fetchone())[0]
            if count > 0:
                logger.info("LTM already has %d entries — skipping seed", count)
                return

            logger.info("LTM is empty — seeding with %d initial policies", len(LTM_SEEDS))
            for seed in LTM_SEEDS:
                context_str = _embedding_service.create_context_string(
                    seed["doc_type"],
                    None,
                    seed.get("content_profile"),
                    seed.get("extra_context"),
                )
                vector = _embedding_service.generate_embedding(context_str)
                context_hash = hashlib.sha256(f"{context_str}:{seed['policy_id']}".encode()).hexdigest()

                await cur.execute(
                    """INSERT INTO ltm_validated_policies
                       (context_hash, context_embedding, policy_id, policy_data,
                        validation_metrics, alpha, beta, confidence_score, last_promoted_at)
                       VALUES (%s, %s::vector, %s, %s::jsonb, %s::jsonb, %s, %s, 0.7, NOW())
                       ON CONFLICT (context_hash) DO NOTHING""",
                    (
                        context_hash,
                        vector,
                        seed["policy_id"],
                        json.dumps(seed["policy_data"]),
                        json.dumps({"origin": "seed", "f1_score": 0.0}),
                        seed["alpha"],
                        seed["beta"],
                    ),
                )
            await conn.commit()
            logger.info("LTM seeded successfully with %d policies", len(LTM_SEEDS))

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _pool, _redis

    _pool = AsyncConnectionPool(
        conninfo=POSTGRES_URI,
        open=False,
        min_size=2,
        max_size=20,
        configure=_register_vector,
    )
    await _pool.open()

    _redis = aioredis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )

    # Seed LTM with initial knowledge so AHMN isn't blind on first run
    try:
        await _seed_ltm_if_empty()
    except Exception as exc:
        logger.warning("LTM seeding failed (non-fatal): %s", exc)

    # Start background scheduler for promotion & forgetting
    global _scheduler
    _scheduler = AHMNScheduler(pool=_pool, embedding_service=_embedding_service)
    _scheduler.start()

    logger.info(
        "AHMN service started — Postgres + Redis + Scheduler connected "
        "(seed_mode=%s, advice_selection_mode=%s, rabi_transfer_decay_rate=%s)",
        SEED_MODE,
        _normalize_selection_mode(ADVICE_SELECTION_MODE),
        RABI_TRANSFER_DECAY_RATE,
    )
    yield

    if _scheduler:
        await _scheduler.stop()
    if _pool:
        await _pool.close()
    if _redis:
        await _redis.close()
    logger.info("AHMN service stopped")

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AHMN Service",
    description=(
        "Adaptive Hierarchical Memory Network — Thompson Sampling, "
        "RABI cold-start, DAAF drift-aware forgetting"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# Internal service — restrict CORS to gateway and local dev only
_allowed_origins = os.getenv(
    "CORS_ORIGINS", "http://localhost:3000,http://gateway:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    """Deep health check — verifies DB pool and Redis connectivity."""
    checks: dict[str, str] = {
        "service": "ahmn",
        "seed_mode": SEED_MODE,
        "advice_selection_mode": _normalize_selection_mode(ADVICE_SELECTION_MODE),
        "rabi_transfer_decay_rate": str(RABI_TRANSFER_DECAY_RATE),
    }
    try:
        if _pool:
            async with _pool.connection() as conn:
                await conn.execute("SELECT 1")
            checks["db"] = "ok"
        else:
            checks["db"] = "pool_not_initialized"
    except Exception as exc:
        checks["db"] = f"error: {exc}"
    try:
        if _redis:
            await _redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "not_initialized"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
    all_ok = checks.get("db") == "ok" and checks.get("redis") == "ok"
    checks["status"] = "healthy" if all_ok else "degraded"
    return checks

# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/scheduler/status")
async def scheduler_status():
    """Return background scheduler status — promotion & forgetting stats."""
    if _scheduler:
        return _scheduler.status()
    return {"running": False, "error": "Scheduler not initialised"}

@app.post("/scheduler/promote")
async def trigger_promotion():
    """Manually trigger a promotion cycle (MTM → LTM)."""
    if not _scheduler:
        raise HTTPException(503, "Scheduler not initialised")
    promoted = await _scheduler._run_promotion()
    return {"status": "completed", "promoted": promoted}

@app.post("/scheduler/forget")
async def trigger_forgetting():
    """Manually trigger a DAAF forgetting cycle."""
    if not _scheduler:
        raise HTTPException(503, "Scheduler not initialised")
    affected = await _scheduler._run_forgetting()
    return {"status": "completed", "affected": affected}

# ═══════════════════════════════════════════════════════════════════════════════
# ADVICE ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/advice", response_model=PolicyResponse)
async def get_advice(context: DocumentContext, request: Request):
    """Policy recommendation using Thompson Sampling by default.

    Deterministic selection is retained as an explicit debug override via
    ``?mode=deterministic`` or ``AHMN_ADVICE_SELECTION_MODE=deterministic``.
    ``explore=true|false`` is still accepted for backward compatibility.
    """
    selection_mode = _resolve_selection_mode(request)

    context_str = _embedding_service.create_context_string(
        context.doc_type,
        context.vendor,
        context.content_profile,
        context.extra_context,
    )
    vector = _embedding_service.generate_embedding(context_str)

    # Seed TS RNG from context so identical inputs produce reproducible draws
    # while still exploring across different document contexts.
    ctx_seed = int(hashlib.sha256(context_str.encode()).hexdigest(), 16) % (2**31)
    ts_rng = random.Random(ctx_seed)

    policy_id = "default"
    policy_data: dict = {"action": "standard_processing"}
    confidence = 0.3
    rabi_used = False
    n_neighbors_used = 0
    selected_row = None

    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT policy_id, policy_data, alpha, beta, context_hash,
                          1 - (context_embedding <=> %s::vector) AS similarity
                   FROM ltm_validated_policies
                   ORDER BY context_embedding <=> %s::vector
                   LIMIT %s""",
                (vector, vector, _rabi.k),
            )
            rows = await cur.fetchall()

    prior = None
    if rows:
        # Decide per-policy: is this a warm start (direct evidence) or cold start (RABI transfer)?
        # Group neighbors by policy_id so each candidate policy gets its own posterior.
        rows_by_policy: dict[str, list] = {}
        for row in rows:
            rows_by_policy.setdefault(row[0], []).append(row)

        warm_threshold = _rabi.similarity_threshold  # treat as direct evidence if ≥ threshold

        best_score = -1.0
        best_policy_is_cold_start = False
        for pid, pid_rows in rows_by_policy.items():
            direct_rows = [r for r in pid_rows if r[5] >= warm_threshold]

            if direct_rows:
                # Warm start: use the (alpha, beta) of the most similar direct row.
                # No RABI blending — that would double-count evidence.
                direct_row = max(direct_rows, key=lambda r: r[5])
                alpha_used = max(0.1, float(direct_row[2]))
                beta_used = max(0.1, float(direct_row[3]))
                score = _policy_score(alpha_used, beta_used, selection_mode, ts_rng)
                representative = direct_row
                is_cold = False
            else:
                # Cold start: no sufficiently similar direct context for this policy.
                # Aggregate the policy's own neighbors via RABI into a single prior.
                policy_neighbors = [
                    NeighborInfo(
                        context_hash=r[4],
                        policy_id=pid,
                        alpha=float(r[2]),
                        beta=float(r[3]),
                        similarity=float(r[5]),
                        n_samples=int(r[2] + r[3] - 2),
                    )
                    for r in pid_rows
                ]
                policy_prior = _rabi.initialize_prior(policy_neighbors)
                if policy_prior.n_neighbors == 0:
                    # No valid neighbors for RABI; skip this policy candidate.
                    continue
                score = _policy_score(policy_prior.alpha, policy_prior.beta, selection_mode, ts_rng)
                representative = max(pid_rows, key=lambda r: r[5])
                is_cold = True
                prior = policy_prior  # last cold-start prior used (for downstream confidence)

            if score > best_score:
                best_score = score
                selected_row = representative
                best_policy_is_cold_start = is_cold
                if is_cold:
                    n_neighbors_used = policy_prior.n_neighbors

        rabi_used = best_policy_is_cold_start

        if selected_row:
            policy_id = selected_row[0]
            policy_data = selected_row[1]
            alpha_sel, beta_sel = float(selected_row[2]), float(selected_row[3])
            similarity_score = float(selected_row[5])

            if best_policy_is_cold_start and prior is not None:
                # Cold-start confidence comes from RABI prior strength + neighbor similarity.
                transferred = max(0.0, (prior.alpha - 1.0) + (prior.beta - 1.0))
                evidence_strength = min(1.0, transferred / 10.0)
                confidence = min(
                    0.95,
                    prior.confidence * 0.4 + similarity_score * 0.3 + evidence_strength * 0.3,
                )
            else:
                # Warm-start confidence comes from direct LTM evidence for this (context, policy).
                evidence_strength = min(1.0, (alpha_sel + beta_sel - 2.0) / 20.0)
                confidence = min(
                    0.95,
                    0.4 + similarity_score * 0.3 + evidence_strength * 0.3,
                )

    advice_id = uuid.uuid4()
    rabi_transfer_state = None
    if rabi_used and prior is not None:
        rabi_transfer_state = _build_rabi_transfer_state(
            max(0.0, prior.alpha - 1.0),
            max(0.0, prior.beta - 1.0),
            0,
        )
    await _rds().setex(
        f"advice:{advice_id}",
        1800,
        json.dumps(
            {
                "context": context.model_dump(),
                "source_hash": selected_row[4] if selected_row else None,
                "rabi_transfer": rabi_transfer_state,
            }
        ),
    )
    return PolicyResponse(
        advice_id=advice_id,
        policy_id=policy_id,
        policy_data=policy_data,
        retrieval_source="LTM" if selected_row else "DEFAULT",
        confidence=round(confidence, 3),
        rabi_used=rabi_used,
        n_neighbors=n_neighbors_used if rabi_used else None,
    )

@app.post("/advice/log")
async def log_outcome(req: LogRequest, request: Request):
    """
    Log processing outcome — triggers DAAF drift detection and inline promotion.

    This is THE key learning endpoint. It:
    1. Records the outcome in MTM (mid-term memory)
    2. Updates existing LTM entries if the policy was already known
    3. PROMOTES new context→policy mappings to LTM if they perform well
       (inline promotion — doesn't wait for batch job)
    """
    redis_data_json = await _rds().get(f"advice:{req.advice_id}")
    if not redis_data_json:
        raise HTTPException(404, "Advice context expired from STM")

    redis_data = json.loads(redis_data_json)
    source_hash = redis_data.get("source_hash")
    source_rabi_transfer = _normalize_rabi_transfer_state(redis_data.get("rabi_transfer"))
    stm_context = redis_data.get("context", {})

    # Prefer the real document context discovered during processing over the
    # stale pre-processing guess stored in STM (which is often "unknown" when
    # the doc_type could only be inferred from the filename).
    if req.document_context:
        context_dict = {**stm_context, **req.document_context}
    else:
        context_dict = stm_context

    # Build a proper context hash for the ACTUAL policy used (not what was recommended)
    ctx_str = _build_context_string(context_dict)
    actual_policy_hash = _context_hash_for(req.policy_id_used, context_dict)

    if not source_hash:
        source_hash = actual_policy_hash

    reward = _blended_reward(req.metrics)

    context_key = (
        f"{context_dict.get('doc_type', 'unknown')}:"
        f"{context_dict.get('vendor', '')}"
    )
    estimator = _get_drift_estimator(context_key)
    drift_metrics = estimator.update(reward)
    gamma = drift_metrics.optimal_gamma

    promoted = False
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            # 1. Log in MTM (always)
            await cur.execute(
                """INSERT INTO mtm_outcomes
                   (advice_id, policy_id_used, document_context, outcome_metrics)
                   VALUES (%s, %s, %s::jsonb, %s::jsonb)""",
                (
                    req.advice_id,
                    req.policy_id_used,
                    json.dumps(context_dict),
                    json.dumps(req.metrics.model_dump()),
                ),
            )

            # 2. Try updating existing LTM entry for this context→policy
            updated = await _update_ltm_entry(
                cur,
                source_hash,
                req.policy_id_used,
                reward,
                1.0 - reward,
                gamma=gamma,
                confidence_bump=0.05,
            )

            # 3. If no existing LTM entry was updated AND the actual policy differs
            #    from what was in LTM, try with the actual policy hash
            if not updated and actual_policy_hash != source_hash:
                updated = await _update_ltm_entry(
                    cur,
                    actual_policy_hash,
                    req.policy_id_used,
                    reward,
                    1.0 - reward,
                    gamma=gamma,
                    confidence_bump=0.05,
                )

            # 4. INLINE PROMOTION: If reward is decent and no existing entry matches,
            #    create a new LTM entry so AHMN learns this context→policy mapping
            if not updated and reward >= 0.4 and req.policy_id_used != "default":
                vector = _embedding_service.generate_embedding(ctx_str)
                initial_alpha = 1.0 + reward * 3.0   # Scale prior by reward quality
                initial_beta = 1.0 + (1.0 - reward) * 3.0
                rabi_transfer_payload = None
                if source_rabi_transfer:
                    rabi_transfer_payload = _build_rabi_transfer_state(
                        source_rabi_transfer["base_alpha"],
                        source_rabi_transfer["base_beta"],
                        1,
                    )
                    if rabi_transfer_payload:
                        initial_alpha = 1.0 + float(rabi_transfer_payload["effective_alpha"]) + reward
                        initial_beta = 1.0 + float(rabi_transfer_payload["effective_beta"]) + (1.0 - reward)
                await cur.execute(
                    """INSERT INTO ltm_validated_policies
                       (context_hash, context_embedding, policy_id, policy_data,
                        validation_metrics, alpha, beta, confidence_score, last_promoted_at)
                       VALUES (%s, %s::vector, %s, %s::jsonb, %s::jsonb, %s, %s, 0.6, NOW())
                       ON CONFLICT (context_hash) DO UPDATE SET
                           alpha = ltm_validated_policies.alpha + %s,
                           beta = ltm_validated_policies.beta + (1 - %s),
                           last_promoted_at = NOW()""",
                    (
                        actual_policy_hash,
                        vector,
                        req.policy_id_used,
                        json.dumps(
                            {
                                "action": req.policy_id_used,
                                "origin": "inline_promotion",
                                "doc_type": context_dict.get("doc_type", "unknown"),
                                "vendor": context_dict.get("vendor"),
                                "content_profile": context_dict.get("content_profile"),
                            }
                        ),
                        json.dumps(
                            {
                                "f1_score": req.metrics.f1_score,
                                "blended_reward": reward,
                                "source": "inline",
                                "document_context": {
                                    "doc_type": context_dict.get("doc_type", "unknown"),
                                    "vendor": context_dict.get("vendor"),
                                    "content_profile": context_dict.get("content_profile"),
                                },
                                "rabi_transfer": rabi_transfer_payload,
                            }
                        ),
                        initial_alpha,
                        initial_beta,
                        reward,
                        reward,
                    ),
                )
                promoted = True
                logger.info(
                    "Inline LTM promotion: %s → %s (reward=%.3f)",
                    context_dict.get("doc_type", "?"), req.policy_id_used, reward,
                )

            await conn.commit()

    return {
        "status": "logged",
        "drift_type": drift_metrics.drift_type.value,
        "gamma": round(gamma, 6),
        "promoted_to_ltm": promoted,
        "reward": round(reward, 4),
    }

@app.post("/advice/feedback")
async def log_feedback(req: FeedbackRequest):
    """Record human-corrected flag and adjust LTM policy evidence."""
    ltm_adjusted = False
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE mtm_outcomes SET human_corrected = %s WHERE advice_id = %s "
                "RETURNING policy_id_used, document_context",
                (req.human_corrected, req.advice_id),
            )
            row = await cur.fetchone()

            if row:
                policy_id_used, document_context = row
                feedback_type = req.feedback_type or ("incorrect" if req.human_corrected else "correct")
                alpha_reward = 0.0
                beta_penalty = 0.0
                if feedback_type == "incorrect":
                    beta_penalty = 2.0
                elif feedback_type == "partially_correct":
                    alpha_reward = 0.5
                    beta_penalty = 0.5
                elif feedback_type == "correct":
                    alpha_reward = 1.0

                if (alpha_reward > 0 or beta_penalty > 0) and isinstance(document_context, dict):
                    context_hash = _context_hash_for(policy_id_used, document_context)
                    ltm_adjusted = await _update_ltm_entry(
                        cur,
                        context_hash,
                        policy_id_used,
                        alpha_reward,
                        beta_penalty,
                        confidence_bump=0.0,
                    )

            await conn.commit()
    return {"status": "feedback_recorded", "ltm_adjusted": ltm_adjusted}


@app.post("/advice/review")
async def log_review_feedback(req: ReviewFeedbackRequest):
    """Record reviewed extraction quality and update the matching LTM arm."""
    context_hash = _context_hash_for(req.policy_id_used, req.document_context)
    alpha_delta = float(req.review_weight) * float(req.f1)
    beta_delta = float(req.review_weight) * (1.0 - float(req.f1))
    metrics_payload = {
        "source": "review_feedback",
        "review_source": req.review_source,
        "review_weight": req.review_weight,
        "tp": req.tp,
        "fp": req.fp,
        "fn": req.fn,
        "precision": req.precision,
        "recall": req.recall,
        "f1_score": req.f1,
        "field_state_counts": req.field_state_counts,
        "job_id": req.job_id,
        "overlay_key": req.overlay_key,
    }

    updated = False
    promoted = False
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO mtm_outcomes
                   (advice_id, policy_id_used, document_context, outcome_metrics)
                   VALUES (%s, %s, %s::jsonb, %s::jsonb)""",
                (
                    req.advice_id,
                    req.policy_id_used,
                    json.dumps(req.document_context),
                    json.dumps(metrics_payload),
                ),
            )

            updated = await _update_ltm_entry(
                cur,
                context_hash,
                req.policy_id_used,
                alpha_delta,
                beta_delta,
                confidence_bump=0.03,
                metrics_patch=metrics_payload,
            )

            if not updated and req.policy_id_used != "default":
                vector = _embedding_service.generate_embedding(_build_context_string(req.document_context))
                await cur.execute(
                    """INSERT INTO ltm_validated_policies
                       (context_hash, context_embedding, policy_id, policy_data,
                        validation_metrics, alpha, beta, confidence_score, last_promoted_at)
                       VALUES (%s, %s::vector, %s, %s::jsonb, %s::jsonb, %s, %s, 0.55, NOW())
                       ON CONFLICT (context_hash) DO UPDATE SET
                           alpha = ltm_validated_policies.alpha + %s,
                           beta = ltm_validated_policies.beta + %s,
                           validation_metrics = %s::jsonb,
                           last_promoted_at = NOW()""",
                    (
                        context_hash,
                        vector,
                        req.policy_id_used,
                        json.dumps(
                            {
                                "action": req.policy_id_used,
                                "origin": "review_feedback",
                                "doc_type": req.document_context.get("doc_type", "unknown"),
                                "vendor": req.document_context.get("vendor"),
                                "content_profile": req.document_context.get("content_profile"),
                            }
                        ),
                        json.dumps(metrics_payload),
                        1.0 + alpha_delta,
                        1.0 + beta_delta,
                        alpha_delta,
                        beta_delta,
                        json.dumps(metrics_payload),
                    ),
                )
                promoted = True

            await conn.commit()

    return {
        "status": "review_recorded",
        "updated_existing_ltm": updated,
        "promoted_to_ltm": promoted,
        "alpha_delta": round(alpha_delta, 4),
        "beta_delta": round(beta_delta, 4),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/dashboard/stats")
async def get_stats():
    """Aggregate statistics for the admin overview."""
    # Single query — fetch all 4 counts in one round-trip
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT
                    (SELECT COUNT(*) FROM mtm_outcomes)      AS total_outcomes,
                    (SELECT COUNT(*) FROM ltm_validated_policies) AS total_ltm,
                    (SELECT COUNT(*) FROM experiment_runs)   AS total_experiments,
                    (SELECT COUNT(*) FROM users)             AS total_users
            """)
            row = await cur.fetchone()
            total_outcomes, total_ltm, total_experiments, total_users = (
                row if row else (0, 0, 0, 0)
            )

    # Count STM keys without blocking Redis (SCAN instead of KEYS)
    redis = _rds()
    stm_count = 0
    async for _ in redis.scan_iter("advice:*", count=500):
        stm_count += 1

    return {
        "total_advice": stm_count,
        "total_outcomes": total_outcomes,
        "total_ltm_policies": total_ltm,
        "total_experiments": total_experiments,
        "total_users": total_users,
    }

@app.get("/dashboard/memory/stm")
async def get_stm():
    """Active STM entries from Redis."""
    entries = []
    redis = _rds()
    async for key in redis.scan_iter("advice:*"):
        ttl = await redis.ttl(key)
        val = await redis.get(key)
        entries.append(
            {"key": key, "ttl_seconds": ttl, "data": json.loads(val) if val else None}
        )
    return entries

@app.get("/dashboard/memory/mtm")
async def get_mtm(limit: int = Query(50, ge=1, le=500)):
    """Recent MTM outcomes."""
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT id, advice_id, policy_id_used, document_context,
                          outcome_metrics, human_corrected, created_at
                   FROM mtm_outcomes ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            rows = await cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "advice_id": str(r[1]),
            "policy_id_used": r[2],
            "document_context": r[3],
            "outcome_metrics": r[4],
            "human_corrected": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]

@app.get("/dashboard/memory/ltm")
async def get_ltm():
    """LTM validated policies with bandit parameters and document context."""
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT id, context_hash, policy_id, policy_data, alpha, beta,
                          confidence_score, last_promoted_at, validation_metrics
                   FROM ltm_validated_policies ORDER BY last_promoted_at DESC"""
            )
            rows = await cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "context_hash": r[1],
            "policy_id": r[2],
            "policy_data": r[3],
            "alpha": r[4],
            "beta": r[5],
            "confidence_score": r[6],
            "last_promoted_at": r[7].isoformat() if r[7] else "",
            "validation_metrics": r[8],
            "doc_type": (
                (r[3] or {}).get("doc_type")
                or ((r[8] or {}).get("document_context") or {}).get("doc_type")
                or "unknown"
            ),
            "vendor": (
                (r[3] or {}).get("vendor")
                or ((r[8] or {}).get("document_context") or {}).get("vendor")
            ),
            "content_profile": (
                (r[3] or {}).get("content_profile")
                or ((r[8] or {}).get("document_context") or {}).get("content_profile")
            ),
        }
        for r in rows
    ]

@app.get("/dashboard/memory/ltm/chart")
async def ltm_chart_data():
    """LTM data formatted for charts."""
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT policy_id,
                          AVG(alpha / (alpha + beta)) AS avg_mean,
                          COUNT(*) AS count,
                          AVG(alpha + beta) AS avg_strength
                   FROM ltm_validated_policies GROUP BY policy_id"""
            )
            rows = await cur.fetchall()
    return [
        {
            "policy_id": r[0],
            "avg_mean": round(r[1], 4),
            "count": r[2],
            "avg_strength": round(r[3], 2),
        }
        for r in rows
    ]

@app.get("/dashboard/activity")
async def recent_activity(limit: int = Query(20, ge=1, le=100)):
    """Recent system activity for the admin feed."""
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT 'outcome' AS type, policy_id_used AS detail,
                          outcome_metrics->>'f1_score' AS metric, created_at
                   FROM mtm_outcomes ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            rows = await cur.fetchall()
    return [
        {
            "type": r[0],
            "detail": r[1],
            "metric": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]

# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIMENT ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/experiments/results")
async def get_results():
    """Return pre-computed experiment results (JSON)."""
    data = _load_json("experiment_results.json")
    if data is None:
        raise HTTPException(404, "Experiment results not found. Run experiments first.")
    return data

@app.get("/experiments/robustness")
async def get_robustness():
    """Return robustness sweep results."""
    data = _load_json("robustness_results.json")
    if data is None:
        raise HTTPException(404, "Robustness results not found.")
    return data

@app.post("/experiments/demo/daaf")
async def run_daaf_demo(params: dict[str, Any]):
    """Run interactive DAAF drift detection demo."""
    pre_mean = params.get("pre_drift_mean", 0.85)
    post_mean = params.get("post_drift_mean", 0.55)
    noise_std = params.get("noise_std", 0.06)
    drift_round = params.get("drift_round", 150)
    window_size = params.get("window_size", 50)
    n_rounds = params.get("n_rounds", 300)

    rng = np.random.RandomState(42)
    rewards: list[float] = []
    for t in range(n_rounds):
        mean = pre_mean if t < drift_round else post_mean
        r = float(np.clip(rng.normal(mean, noise_std), 0.0, 1.0))
        rewards.append(r)

    estimator = DriftEstimator(
        window_size=window_size,
        min_samples=10,
        drift_threshold=0.05,
        abrupt_threshold=0.15,
    )

    drift_magnitudes, gammas, drift_types, recent_means = [], [], [], []
    for reward in rewards:
        metrics = estimator.update(reward)
        drift_magnitudes.append(metrics.drift_magnitude)
        gammas.append(metrics.optimal_gamma)
        drift_types.append(metrics.drift_type.value)
        recent_means.append(
            float(np.mean(list(estimator.recent_window)))
            if estimator.recent_window
            else reward
        )

    detected_at = None
    for t in range(drift_round, n_rounds):
        if drift_types[t] != "none":
            detected_at = t
            break

    return {
        "rewards": rewards,
        "recent_means": recent_means,
        "drift_magnitudes": drift_magnitudes,
        "gammas": gammas,
        "drift_types": drift_types,
        "detection_delay": (detected_at - drift_round) if detected_at else None,
        "peak_gamma": max(gammas[drift_round:]) if drift_round < len(gammas) else 0,
    }

@app.post("/experiments/demo/rabi")
async def run_rabi_demo(params: dict[str, Any]):
    """Run interactive RABI cold-start demo."""
    from .services.rabi import RABIInitializer
    from .seeds import LTM_SEEDS

    temperature = params.get("temperature", 0.5)
    threshold = params.get("threshold", 0.3)
    k = params.get("k", 5)

    rabi = RABIInitializer(k=k, similarity_threshold=threshold, temperature=temperature)

    # Use real LTM seed data for neighbors
    seed_subset = LTM_SEEDS[:k]
    neighbors = [
        NeighborInfo(
            context_hash=seed["doc_type"],
            policy_id=seed["policy_id"],
            alpha=seed["alpha"],
            beta=seed["beta"],
            similarity=round(seed["confidence"] + 0.15 * (1 - i / max(k - 1, 1)), 3),
            n_samples=int(seed["alpha"] + seed["beta"]),
        )
        for i, seed in enumerate(seed_subset)
    ]

    prior = rabi.initialize_prior(neighbors)
    weights = rabi.compute_weights([n.similarity for n in neighbors])

    from scipy.stats import beta as beta_dist

    x = np.linspace(0, 1, 200).tolist()
    flat_pdf = beta_dist.pdf(x, 1, 1).tolist()
    rabi_pdf = beta_dist.pdf(x, prior.alpha, prior.beta).tolist()

    return {
        "prior": {
            "alpha": prior.alpha,
            "beta": prior.beta,
            "mean": prior.mean,
            "confidence": prior.confidence,
            "n_neighbors": prior.n_neighbors,
        },
        "neighbors": [
            {
                "hash": n.context_hash,
                "similarity": n.similarity,
                "alpha": n.alpha,
                "beta": n.beta,
                "mean": n.mean_reward,
            }
            for n in neighbors
        ],
        "weights": weights,
        "distribution": {"x": x, "flat_pdf": flat_pdf, "rabi_pdf": rabi_pdf},
    }

@app.post("/experiments/demo/comparison")
async def run_comparison_demo(params: dict[str, Any]):
    """Run TS vs DAAF comparison under drift."""
    import asyncio

    def _run_comparison(params: dict[str, Any]):
        from .experiments.synthetic_data import (
            VendorProfile,
            PolicyConfig,
            DriftEvent,
            Scenario,
            _make_cluster_embedding,
            POLICY_IDS,
        )
        from .experiments.run_experiments import (
            ThompsonSamplingRunner,
            AHMNDAAFRunner,
            run_single,
        )

        drift_magnitude = params.get("drift_magnitude", 0.20)
        n_seeds = min(params.get("seeds", 10), 20)

        vendors = [
            VendorProfile(
                vendor_id="vendor_drift",
                doc_type="invoice",
                policies={
                    "table_heavy":   PolicyConfig(true_mean=0.88, noise_std=0.04),
                    "forms":         PolicyConfig(true_mean=0.62, noise_std=0.07),
                    "scanned_text":  PolicyConfig(true_mean=0.55, noise_std=0.07),
                    "mixed_content": PolicyConfig(true_mean=0.72, noise_std=0.06),
                    "default":       PolicyConfig(true_mean=0.68, noise_std=0.06),
                },
                embedding=_make_cluster_embedding(1, 0),
                weight=1.0,
            ),
        ]

        # Drift lowers the previously best policy and raises a different one
        post_table = max(0.1, 0.88 - drift_magnitude)
        post_mixed = min(0.98, 0.72 + drift_magnitude)

        scenario = Scenario(
            name="demo_drift",
            description=f"Drift demo Δ={drift_magnitude}",
            vendors=vendors,
            policy_ids=POLICY_IDS,
            n_rounds=800,
            drift_events=[
                DriftEvent(
                    vendor_id="vendor_drift",
                    at_round=400,
                    new_policies={
                        "table_heavy":   PolicyConfig(true_mean=post_table, noise_std=0.05),
                        "forms":         PolicyConfig(true_mean=0.60, noise_std=0.07),
                        "scanned_text":  PolicyConfig(true_mean=0.58, noise_std=0.07),
                        "mixed_content": PolicyConfig(true_mean=post_mixed, noise_std=0.05),
                        "default":       PolicyConfig(true_mean=0.68, noise_std=0.06),
                    },
                )
            ],
        )

        ts_results = [
            run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, s)
            for s in range(n_seeds)
        ]
        daaf_results = [
            run_single(AHMNDAAFRunner(POLICY_IDS), scenario, s)
            for s in range(n_seeds)
        ]

        ts_avg_regret = np.mean(
            [r.cumulative_regret for r in ts_results], axis=0
        ).tolist()
        daaf_avg_regret = np.mean(
            [r.cumulative_regret for r in daaf_results], axis=0
        ).tolist()

        window = 50
        ts_avg_rewards = np.mean([r.rewards for r in ts_results], axis=0)
        daaf_avg_rewards = np.mean([r.rewards for r in daaf_results], axis=0)

        def rolling(arr, w):
            return [float(np.mean(arr[max(0, i - w) : i + 1])) for i in range(len(arr))]

        return {
            "ts_cumulative_regret": ts_avg_regret,
            "daaf_cumulative_regret": daaf_avg_regret,
            "ts_rolling_reward": rolling(ts_avg_rewards, window),
            "daaf_rolling_reward": rolling(daaf_avg_rewards, window),
            "rolling_start": window,
            "total_ts_regret": round(float(ts_avg_regret[-1]), 2),
            "total_daaf_regret": round(float(daaf_avg_regret[-1]), 2),
            "improvement_pct": round(
                (float(ts_avg_regret[-1]) - float(daaf_avg_regret[-1]))
                / max(1, float(ts_avg_regret[-1]))
                * 100,
                1,
            ),
        }

    return await asyncio.to_thread(_run_comparison, params)
