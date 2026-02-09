"""
Dashboard router — stats, memory data, system overview for admin UI.
"""

import json
from fastapi import APIRouter, Depends
from psycopg import AsyncConnection
from redis.asyncio import Redis

from ..deps import get_db, get_redis_client, get_current_user
from ..schemas.dashboard import StatsResponse, LTMEntry, ExperimentEntry

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncConnection = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
    user: dict = Depends(get_current_user),
):
    """Aggregate statistics for the overview page."""
    async with db.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM mtm_outcomes")
        total_outcomes = (await cur.fetchone())[0]  # type: ignore

        await cur.execute("SELECT COUNT(*) FROM ltm_validated_policies")
        total_ltm = (await cur.fetchone())[0]  # type: ignore

        await cur.execute("SELECT COUNT(*) FROM experiment_runs")
        total_experiments = (await cur.fetchone())[0]  # type: ignore

        await cur.execute("SELECT COUNT(*) FROM users")
        total_users = (await cur.fetchone())[0]  # type: ignore

    # Count STM keys in Redis (advice:*)
    stm_keys = []
    async for key in redis.scan_iter("advice:*"):
        stm_keys.append(key)
    total_advice = len(stm_keys)

    return StatsResponse(
        total_advice=total_advice,
        total_outcomes=total_outcomes,
        total_ltm_policies=total_ltm,
        total_experiments=total_experiments,
        total_users=total_users,
    )


@router.get("/memory/stm")
async def get_stm(
    redis: Redis = Depends(get_redis_client),
    user: dict = Depends(get_current_user),
):
    """Active STM entries from Redis."""
    entries = []
    async for key in redis.scan_iter("advice:*"):
        ttl = await redis.ttl(key)
        val = await redis.get(key)
        entries.append({
            "key": key,
            "ttl_seconds": ttl,
            "data": json.loads(val) if val else None,
        })
    return entries


@router.get("/memory/mtm")
async def get_mtm(
    limit: int = 50,
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Recent MTM outcomes."""
    async with db.cursor() as cur:
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


@router.get("/memory/ltm", response_model=list[LTMEntry])
async def get_ltm(
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """LTM validated policies with bandit parameters."""
    async with db.cursor() as cur:
        await cur.execute(
            """SELECT id, context_hash, policy_id, alpha, beta,
                      confidence_score, last_promoted_at
               FROM ltm_validated_policies ORDER BY last_promoted_at DESC"""
        )
        rows = await cur.fetchall()
    return [
        LTMEntry(
            id=str(r[0]),
            context_hash=r[1],
            policy_id=r[2],
            alpha=r[3],
            beta=r[4],
            confidence_score=r[5],
            last_promoted_at=r[6].isoformat() if r[6] else "",
        )
        for r in rows
    ]


@router.get("/memory/ltm/chart")
async def ltm_chart_data(
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """LTM data formatted for charts — policy distribution, alpha/beta."""
    async with db.cursor() as cur:
        await cur.execute(
            """SELECT policy_id,
                      AVG(alpha / (alpha + beta)) as avg_mean,
                      COUNT(*) as count,
                      AVG(alpha + beta) as avg_strength
               FROM ltm_validated_policies
               GROUP BY policy_id"""
        )
        rows = await cur.fetchall()
    return [
        {"policy_id": r[0], "avg_mean": round(r[1], 4), "count": r[2], "avg_strength": round(r[3], 2)}
        for r in rows
    ]


@router.get("/activity")
async def recent_activity(
    limit: int = 20,
    db: AsyncConnection = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Recent system activity for timeline / feed."""
    async with db.cursor() as cur:
        await cur.execute(
            """SELECT 'outcome' as type, policy_id_used as detail,
                      outcome_metrics->>'f1_score' as metric, created_at
               FROM mtm_outcomes
               ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        rows = await cur.fetchall()
    return [
        {"type": r[0], "detail": r[1], "metric": r[2], "created_at": r[3].isoformat() if r[3] else None}
        for r in rows
    ]
