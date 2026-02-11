"""
Advice router — AHMN core endpoints (/advice, /log, /feedback).
Re-exports the original AHMN API with JWT protection.
"""

import sys
import os
import json
import uuid
import random
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from redis.asyncio import Redis

from ..deps import get_db, get_redis_client, get_current_user

# Ensure ahmn_core is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from ahmn_core.schemas import DocumentContext, PolicyResponse, OutcomeMetrics, LogRequest, FeedbackRequest
from ahmn_core.services.embedding import EmbeddingService
from ahmn_core.services.rabi import RABIInitializer, NeighborInfo, create_rabi_for_production
from ahmn_core.services.drift_forgetting import DriftEstimator, DriftType

router = APIRouter(prefix="/api/advice", tags=["advice"])

# Singleton services
_embedding_service = EmbeddingService()
_rabi = create_rabi_for_production(k=5, similarity_threshold=0.4, temperature=0.5)
_drift_estimators: dict[str, DriftEstimator] = {}


def _get_drift_estimator(context_key: str) -> DriftEstimator:
    if context_key not in _drift_estimators:
        _drift_estimators[context_key] = DriftEstimator(
            window_size=50, min_samples=10, drift_threshold=0.05, abrupt_threshold=0.15
        )
    return _drift_estimators[context_key]


@router.post("", response_model=PolicyResponse)
async def get_advice(
    context: DocumentContext,
    db: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
    user: dict = Depends(get_current_user),
):
    context_str = _embedding_service.create_context_string(context.doc_type, context.vendor)
    vector = _embedding_service.generate_embedding(context_str)

    query = """
        SELECT policy_id, policy_data, alpha, beta, context_hash,
               1 - (context_embedding <=> %s::vector) as similarity
        FROM ltm_validated_policies
        ORDER BY context_embedding <=> %s::vector
        LIMIT %s;
    """

    policy_id = "default_policy"
    policy_data: dict = {"action": "standard_processing"}
    confidence = 0.3
    rabi_used = False
    n_neighbors_used = 0
    selected_row = None

    async with db.cursor() as cur:
        await cur.execute(query, (vector, vector, _rabi.k))
        rows = await cur.fetchall()

        if rows:
            neighbors = [
                NeighborInfo(
                    context_hash=r[4], policy_id=r[0],
                    alpha=r[2], beta=r[3], similarity=r[5],
                    n_samples=int(r[2] + r[3] - 2),
                )
                for r in rows
            ]
            prior = _rabi.initialize_prior(neighbors)
            rabi_used = True
            n_neighbors_used = prior.n_neighbors

            best_sample = -1.0
            for row in rows:
                p_id, p_data, alpha, beta, c_hash, sim = row
                blended_alpha = prior.alpha + (alpha - 1) * sim
                blended_beta = prior.beta + (beta - 1) * sim
                sample = random.betavariate(max(0.1, blended_alpha), max(0.1, blended_beta))
                if sample > best_sample:
                    best_sample = sample
                    selected_row = row

            if selected_row:
                policy_id = selected_row[0]
                policy_data = selected_row[1]
                confidence = min(0.95, prior.confidence * 0.6 + selected_row[5] * 0.4)

    advice_id = uuid.uuid4()
    await redis.setex(
        f"advice:{advice_id}", 1800,
        json.dumps({
            "context": context.model_dump(),
            "source_hash": selected_row[4] if selected_row else None,
        }),
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


@router.post("/log")
async def log_outcome(
    request: LogRequest,
    db: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
    user: dict = Depends(get_current_user),
):
    redis_data_json = await redis.get(f"advice:{request.advice_id}")
    if not redis_data_json:
        raise HTTPException(status_code=404, detail="Advice context expired from STM")

    redis_data = json.loads(redis_data_json)
    source_hash = redis_data.get("source_hash")
    context_dict = redis_data.get("context", {})

    if not source_hash:
        context_str = _embedding_service.create_context_string(
            context_dict.get("doc_type", "unknown"), context_dict.get("vendor")
        )
        source_hash = hashlib.sha256(context_str.encode()).hexdigest()

    reward = max(0.0, min(1.0, request.metrics.f1_score))

    # DAAF online drift detection
    context_key = f"{context_dict.get('doc_type', 'unknown')}:{context_dict.get('vendor', '')}"
    estimator = _get_drift_estimator(context_key)
    drift_metrics = estimator.update(reward)
    gamma = drift_metrics.optimal_gamma

    async with db.cursor() as cur:
        await cur.execute(
            """INSERT INTO mtm_outcomes (advice_id, policy_id_used, document_context, outcome_metrics)
               VALUES (%s, %s, %s::jsonb, %s::jsonb)""",
            (request.advice_id, request.policy_id_used,
             json.dumps(context_dict), json.dumps(request.metrics.model_dump())),
        )

        if gamma > 0.001:
            await cur.execute(
                """UPDATE ltm_validated_policies
                   SET alpha = (1.0 + (1.0 - %s) * (alpha - 1.0)) + %s,
                       beta  = (1.0 + (1.0 - %s) * (beta  - 1.0)) + (1 - %s),
                       confidence_score = 1.0, last_promoted_at = NOW()
                   WHERE context_hash = %s AND policy_id = %s""",
                (gamma, reward, gamma, reward, source_hash, request.policy_id_used),
            )
        else:
            await cur.execute(
                """UPDATE ltm_validated_policies
                   SET alpha = alpha + %s, beta = beta + (1 - %s),
                       confidence_score = 1.0, last_promoted_at = NOW()
                   WHERE context_hash = %s AND policy_id = %s""",
                (reward, reward, source_hash, request.policy_id_used),
            )
        await db.commit()

    return {"status": "logged", "drift_type": drift_metrics.drift_type.value, "gamma": gamma}


@router.post("/feedback")
async def log_feedback(
    request: FeedbackRequest,
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    async with db.cursor() as cur:
        await cur.execute(
            "UPDATE mtm_outcomes SET human_corrected = %s WHERE advice_id = %s",
            (request.human_corrected, request.advice_id),
        )
        await db.commit()
    return {"status": "feedback_recorded"}
