"""
AHMN Microservice — Adaptive Hierarchical Memory Network

Exposes policy recommendation (advice), dashboard analytics, and experiment
demo endpoints as a standalone FastAPI service.

Component Owner: Dasanayake D.R.L.
"""

import os
import json
import uuid
import random
import hashlib
import logging
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

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ─── Configuration ───────────────────────────────────────────────────────────

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# ─── Globals ─────────────────────────────────────────────────────────────────

_pool: AsyncConnectionPool | None = None
_redis: aioredis.Redis | None = None

_embedding_service = EmbeddingService()
_rabi = create_rabi_for_production(k=5, similarity_threshold=0.4, temperature=0.5)
_drift_estimators: dict[str, DriftEstimator] = {}
_scheduler: AHMNScheduler | None = None
_RESULTS_DIR = Path(__file__).resolve().parent / "output"

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
                    seed["doc_type"], None
                )
                # Add content_profile to context string for better semantic differentiation
                if seed.get("content_profile"):
                    context_str += f". Content profile: {seed['content_profile']}"
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

    logger.info("AHMN service started — Postgres + Redis + Scheduler connected")
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
    checks: dict[str, str] = {"service": "ahmn"}
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
    """Policy recommendation with deterministic selection and optional exploration.

    Uses the expected value (mean) of the Beta distribution by default so the
    same input always returns the same policy.  When ``explore=true`` is sent
    as a query-parameter, Thompson Sampling is used instead — but even then
    the random seed is derived from the input context so identical requests
    still produce identical results within the same LTM state.
    """
    explore = (request.query_params.get("explore", "false").lower() == "true")

    context_str = _embedding_service.create_context_string(
        context.doc_type, context.vendor
    )
    # Include content_profile for better semantic matching
    if context.content_profile:
        context_str += f". Content profile: {context.content_profile}"
    vector = _embedding_service.generate_embedding(context_str)

    policy_id = "default_policy"
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

    if rows:
        neighbors = [
            NeighborInfo(
                context_hash=r[4],
                policy_id=r[0],
                alpha=r[2],
                beta=r[3],
                similarity=r[5],
                n_samples=int(r[2] + r[3] - 2),
            )
            for r in rows
        ]
        prior = _rabi.initialize_prior(neighbors)
        rabi_used = True
        n_neighbors_used = prior.n_neighbors

        # Create a deterministic seed from the input context so that
        # identical requests always produce identical Thompson Sampling draws.
        ctx_seed = int(hashlib.sha256(context_str.encode()).hexdigest(), 16) % (2**31)
        ts_rng = random.Random(ctx_seed)

        best_score = -1.0
        for row in rows:
            _pid, _pdata, alpha, beta, _chash, sim = row
            blended_alpha = max(0.1, prior.alpha + (alpha - 1) * sim)
            blended_beta = max(0.1, prior.beta + (beta - 1) * sim)

            if explore:
                # Thompson Sampling (exploratory) — seeded for reproducibility
                score = ts_rng.betavariate(blended_alpha, blended_beta)
            else:
                # Deterministic: use expected value E[θ] = α / (α + β)
                score = blended_alpha / (blended_alpha + blended_beta)

            if score > best_score:
                best_score = score
                selected_row = row

        if selected_row:
            policy_id = selected_row[0]
            policy_data = selected_row[1]
            # Confidence from RABI prior + contextual similarity
            # Higher with more evidence (alpha+beta) and better match (similarity)
            alpha_sel, beta_sel = selected_row[2], selected_row[3]
            evidence_strength = min(1.0, (alpha_sel + beta_sel) / 20.0)  # Saturates at 20 observations
            similarity_score = selected_row[5]
            confidence = min(
                0.95,
                prior.confidence * 0.3 + similarity_score * 0.35 + evidence_strength * 0.35
            )

    advice_id = uuid.uuid4()
    await _rds().setex(
        f"advice:{advice_id}",
        1800,
        json.dumps(
            {
                "context": context.model_dump(),
                "source_hash": selected_row[4] if selected_row else None,
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
    stm_context = redis_data.get("context", {})

    # Prefer the real document context discovered during processing over the
    # stale pre-processing guess stored in STM (which is often "unknown" when
    # the doc_type could only be inferred from the filename).
    if req.document_context:
        context_dict = {**stm_context, **req.document_context}
    else:
        context_dict = stm_context

    # Build a proper context hash for the ACTUAL policy used (not what was recommended)
    ctx_str = _embedding_service.create_context_string(
        context_dict.get("doc_type", "unknown"),
        context_dict.get("vendor"),
    )
    content_profile = context_dict.get("content_profile")
    if content_profile:
        ctx_str += f". Content profile: {content_profile}"

    actual_policy_hash = hashlib.sha256(
        f"{ctx_str}:{req.policy_id_used}".encode()
    ).hexdigest()

    if not source_hash:
        source_hash = actual_policy_hash

    reward = max(0.0, min(1.0, req.metrics.f1_score))

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
            if gamma > 0.001:
                await cur.execute(
                    """UPDATE ltm_validated_policies
                       SET alpha = (1.0 + (1.0 - %s) * (alpha - 1.0)) + %s,
                           beta  = (1.0 + (1.0 - %s) * (beta  - 1.0)) + (1 - %s),
                           confidence_score = LEAST(1.0, confidence_score + 0.05),
                           last_promoted_at = NOW()
                       WHERE context_hash = %s AND policy_id = %s
                       RETURNING id""",
                    (gamma, reward, gamma, reward, source_hash, req.policy_id_used),
                )
            else:
                await cur.execute(
                    """UPDATE ltm_validated_policies
                       SET alpha = alpha + %s, beta = beta + (1 - %s),
                           confidence_score = LEAST(1.0, confidence_score + 0.05),
                           last_promoted_at = NOW()
                       WHERE context_hash = %s AND policy_id = %s
                       RETURNING id""",
                    (reward, reward, source_hash, req.policy_id_used),
                )

            updated = await cur.fetchone()

            # 3. If no existing LTM entry was updated AND the actual policy differs
            #    from what was in LTM, try with the actual policy hash
            if not updated and actual_policy_hash != source_hash:
                await cur.execute(
                    """UPDATE ltm_validated_policies
                       SET alpha = alpha + %s, beta = beta + (1 - %s),
                           confidence_score = LEAST(1.0, confidence_score + 0.05),
                           last_promoted_at = NOW()
                       WHERE context_hash = %s AND policy_id = %s
                       RETURNING id""",
                    (reward, reward, actual_policy_hash, req.policy_id_used),
                )
                updated = await cur.fetchone()

            # 4. INLINE PROMOTION: If reward is decent and no existing entry matches,
            #    create a new LTM entry so AHMN learns this context→policy mapping
            if not updated and reward >= 0.4 and req.policy_id_used != "default_policy":
                vector = _embedding_service.generate_embedding(ctx_str)
                initial_alpha = 1.0 + reward * 3.0   # Scale prior by reward quality
                initial_beta = 1.0 + (1.0 - reward) * 3.0
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
                                "f1_score": reward,
                                "source": "inline",
                                "document_context": {
                                    "doc_type": context_dict.get("doc_type", "unknown"),
                                    "vendor": context_dict.get("vendor"),
                                    "content_profile": context_dict.get("content_profile"),
                                },
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
    """Record human-corrected flag and adjust LTM policy β (failure count)."""
    ltm_adjusted = False
    async with _db().connection() as conn:
        async with conn.cursor() as cur:
            # 1. Mark MTM outcome and retrieve the policy + context used
            await cur.execute(
                "UPDATE mtm_outcomes SET human_corrected = %s WHERE advice_id = %s "
                "RETURNING policy_id_used, document_context",
                (req.human_corrected, req.advice_id),
            )
            row = await cur.fetchone()

            if row:
                policy_id_used, document_context = row

                # 2. Graduated β penalty based on feedback_type
                ft = req.feedback_type or ("incorrect" if req.human_corrected else "correct")
                if ft == "incorrect":
                    beta_penalty = 2.0  # Strong signal: policy was wrong
                elif ft == "partially_correct":
                    beta_penalty = 0.5  # Mild signal: policy was partly right
                else:  # "correct" / "needs_more_context" — no penalty
                    beta_penalty = 0.0

                # 3. Apply penalty to matching LTM entry
                if beta_penalty > 0 and isinstance(document_context, dict):
                    ctx_str = _embedding_service.create_context_string(
                        document_context.get("doc_type", "unknown"),
                        document_context.get("vendor"),
                    )
                    cp = document_context.get("content_profile")
                    if cp:
                        ctx_str += f". Content profile: {cp}"
                    context_hash = hashlib.sha256(
                        f"{ctx_str}:{policy_id_used}".encode()
                    ).hexdigest()

                    await cur.execute(
                        """UPDATE ltm_validated_policies
                           SET beta = beta + %s
                           WHERE context_hash = %s AND policy_id = %s
                           RETURNING id""",
                        (beta_penalty, context_hash, policy_id_used),
                    )
                    ltm_adjusted = await cur.fetchone() is not None

            await conn.commit()
    return {"status": "feedback_recorded", "ltm_adjusted": ltm_adjusted}

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
                    "ocr_tesseract": PolicyConfig(true_mean=0.88, noise_std=0.05),
                    "ocr_easyocr": PolicyConfig(true_mean=0.70, noise_std=0.06),
                    "ocr_azure_cv": PolicyConfig(true_mean=0.75, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(1, 0),
                weight=1.0,
            ),
        ]

        post_tess = max(0.1, 0.88 - drift_magnitude)
        post_azure = min(0.98, 0.75 + drift_magnitude)

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
                        "ocr_tesseract": PolicyConfig(true_mean=post_tess, noise_std=0.05),
                        "ocr_easyocr": PolicyConfig(true_mean=0.70, noise_std=0.06),
                        "ocr_azure_cv": PolicyConfig(true_mean=post_azure, noise_std=0.05),
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
