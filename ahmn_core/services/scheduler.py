"""
AHMN Background Scheduler
==========================
Runs promotion (MTM → LTM) and DAAF forgetting as periodic background tasks
inside the AHMN service. This ensures the brain evolves automatically without
manual intervention — critical for production deployment.

Schedule:
  - Promotion:  Every 30 minutes (promotes good strategies to long-term memory)
  - Forgetting:  Every 6 hours  (decays stale policies, removes forgotten ones)
"""

import asyncio
import hashlib
import json
import logging
import math
from datetime import timedelta
from typing import Any

from psycopg_pool import AsyncConnectionPool

from ..services.embedding import EmbeddingService
from ..services.drift_forgetting import DriftEstimator, create_adaptive_forgetting_bandit

logger = logging.getLogger("ahmn.scheduler")

# ── Configurable intervals (seconds) ─────────────────────────────────────────
PROMOTE_INTERVAL_S = int(30 * 60)        # 30 minutes
FORGETTING_INTERVAL_S = int(6 * 60 * 60) # 6 hours
INITIAL_DELAY_S = 60                      # Wait 60s after startup before first run

class AHMNScheduler:
    """Background scheduler for AHMN memory management jobs."""

    def __init__(
        self,
        pool: AsyncConnectionPool,
        embedding_service: EmbeddingService,
        promote_interval: int = PROMOTE_INTERVAL_S,
        forgetting_interval: int = FORGETTING_INTERVAL_S,
    ):
        self.pool = pool
        self.embedding = embedding_service
        self.promote_interval = promote_interval
        self.forgetting_interval = forgetting_interval
        self._tasks: list[asyncio.Task] = []
        self._running = False

        # Forgetting config
        self.base_decay_rate = 0.05
        self.confidence_threshold = 0.35    # Remove policies below this
        self.inactivity_days = 7            # Only decay policies inactive this long
        self.drift_window = 50

        # Stats (exposed via /scheduler/status endpoint)
        self.last_promote_at: str | None = None
        self.last_forget_at: str | None = None
        self.promote_count = 0
        self.forget_count = 0
        self.total_promoted = 0
        self.total_forgotten = 0

    def start(self) -> None:
        """Launch background tasks. Call from lifespan startup."""
        if self._running:
            return
        self._running = True
        self._tasks.append(asyncio.create_task(self._promote_loop()))
        self._tasks.append(asyncio.create_task(self._forgetting_loop()))
        logger.info(
            "Scheduler started — promotion every %ds, forgetting every %ds",
            self.promote_interval, self.forgetting_interval,
        )

    async def stop(self) -> None:
        """Cancel background tasks. Call from lifespan shutdown."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Scheduler stopped")

    def status(self) -> dict:
        """Return scheduler status for the dashboard/API."""
        return {
            "running": self._running,
            "promote_interval_s": self.promote_interval,
            "forgetting_interval_s": self.forgetting_interval,
            "last_promote_at": self.last_promote_at,
            "last_forget_at": self.last_forget_at,
            "promote_runs": self.promote_count,
            "forget_runs": self.forget_count,
            "total_promoted": self.total_promoted,
            "total_forgotten": self.total_forgotten,
        }

    # ── Promotion Loop ────────────────────────────────────────────────────────

    async def _promote_loop(self) -> None:
        """Periodically promote successful MTM strategies to LTM."""
        await asyncio.sleep(INITIAL_DELAY_S)
        while self._running:
            try:
                promoted = await self._run_promotion()
                self.promote_count += 1
                self.total_promoted += promoted
                from datetime import datetime
                self.last_promote_at = datetime.utcnow().isoformat()
                logger.info("Promotion run #%d: %d strategies promoted", self.promote_count, promoted)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("Promotion job failed: %s", exc, exc_info=True)
            await asyncio.sleep(self.promote_interval)

    async def _run_promotion(self) -> int:
        """
        Promote successful strategies from MTM to LTM.

        Criteria:
          - F1 > 0.40
          - Not 'default_policy' (only named policies are worth promoting)
          - At least 2 observations
        """
        promoted = 0
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT
                        document_context,
                        policy_id_used,
                        COUNT(*) as usage_count,
                        AVG((outcome_metrics->>'f1_score')::float) as avg_f1
                    FROM mtm_outcomes
                    WHERE (outcome_metrics->>'f1_score')::float > 0.40
                      AND policy_id_used != 'default_policy'
                    GROUP BY document_context, policy_id_used
                    HAVING COUNT(*) >= 2
                """)
                rows = await cur.fetchall()

                for row in rows:
                    doc_context_json, policy_id, count, avg_f1 = row

                    if isinstance(doc_context_json, str):
                        context_dict = json.loads(doc_context_json)
                    else:
                        context_dict = doc_context_json or {}

                    doc_type = context_dict.get("doc_type", "unknown")
                    vendor = context_dict.get("vendor")
                    content_profile = context_dict.get("content_profile")

                    context_str = self.embedding.create_context_string(doc_type, vendor)
                    if content_profile:
                        context_str += f". Content profile: {content_profile}"
                    vector = self.embedding.generate_embedding(context_str)

                    context_hash = hashlib.sha256(
                        f"{context_str}:{policy_id}".encode()
                    ).hexdigest()

                    alpha_init = 1.0 + avg_f1 * count
                    beta_init = 1.0 + (1.0 - avg_f1) * count
                    confidence = min(1.0, 0.5 + avg_f1 * 0.3 + min(count / 10.0, 0.2))

                    await cur.execute(
                        """INSERT INTO ltm_validated_policies
                           (context_hash, context_embedding, policy_id, policy_data,
                            validation_metrics, alpha, beta, confidence_score, last_promoted_at)
                           VALUES (%s, %s::vector, %s, %s::jsonb, %s::jsonb, %s, %s, %s, NOW())
                           ON CONFLICT (context_hash)
                           DO UPDATE SET
                               validation_metrics = EXCLUDED.validation_metrics,
                               alpha = ltm_validated_policies.alpha + EXCLUDED.alpha - 1.0,
                               beta = ltm_validated_policies.beta + EXCLUDED.beta - 1.0,
                               confidence_score = LEAST(1.0, ltm_validated_policies.confidence_score + 0.1),
                               last_promoted_at = NOW()""",
                        (
                            context_hash, vector, policy_id,
                            json.dumps({"origin": "promoted_from_mtm", "avg_f1": avg_f1}),
                            json.dumps({"f1_score": avg_f1, "sample_size": count}),
                            alpha_init, beta_init, confidence,
                        ),
                    )
                    promoted += 1

                await conn.commit()
        return promoted

    # ── Forgetting Loop ───────────────────────────────────────────────────────

    async def _forgetting_loop(self) -> None:
        """Periodically run DAAF-based forgetting on stale LTM entries."""
        await asyncio.sleep(INITIAL_DELAY_S + 30)  # Offset from promotion
        while self._running:
            try:
                forgotten = await self._run_forgetting()
                self.forget_count += 1
                self.total_forgotten += forgotten
                from datetime import datetime
                self.last_forget_at = datetime.utcnow().isoformat()
                logger.info("Forgetting run #%d: %d policies decayed/removed", self.forget_count, forgotten)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("Forgetting job failed: %s", exc, exc_info=True)
            await asyncio.sleep(self.forgetting_interval)

    async def _run_forgetting(self) -> int:
        """
        DAAF-based forgetting: decay inactive policies, remove if below threshold.

        Steps:
          1. Estimate per-context drift from recent MTM rewards
          2. Compute adaptive decay rate γ* per context
          3. Apply decay to policies inactive > inactivity_days
          4. Archive + delete policies below confidence_threshold
        """
        affected = 0
        async with self.pool.connection() as conn:
            # Step 1: Compute per-context adaptive decay rates
            adaptive_rates = await self._compute_drift_rates(conn)

            async with conn.cursor() as cur:
                # Step 2: Get policies that need decay
                await cur.execute(
                    """SELECT id, policy_id, context_hash, confidence_score, alpha, beta,
                              (SELECT document_context->>'doc_type'
                               FROM mtm_outcomes mo
                               WHERE mo.policy_id_used = ltm.policy_id
                               ORDER BY created_at DESC LIMIT 1) as doc_type,
                              (SELECT document_context->>'vendor'
                               FROM mtm_outcomes mo
                               WHERE mo.policy_id_used = ltm.policy_id
                               ORDER BY created_at DESC LIMIT 1) as vendor
                       FROM ltm_validated_policies ltm
                       WHERE last_promoted_at < NOW() - %s::interval""",
                    (timedelta(days=self.inactivity_days),),
                )
                stale_policies = await cur.fetchall()

                for row in stale_policies:
                    pid, policy_id, ctx_hash, conf, alpha, beta, doc_type, vendor = row

                    # Adaptive decay rate
                    context_key = f"{doc_type}:{vendor}" if vendor else (doc_type or "unknown")
                    decay_rate = adaptive_rates.get(context_key, self.base_decay_rate)

                    new_conf = conf * (1.0 - decay_rate)
                    # Also decay alpha/beta slightly to weaken the prior
                    decay_alpha = max(1.0, alpha * (1.0 - decay_rate * 0.5))
                    decay_beta = max(1.0, beta * (1.0 - decay_rate * 0.3))

                    await cur.execute(
                        """UPDATE ltm_validated_policies
                           SET confidence_score = %s, alpha = %s, beta = %s
                           WHERE id = %s""",
                        (new_conf, decay_alpha, decay_beta, pid),
                    )
                    affected += 1

                # Step 3: Archive and remove forgotten policies
                await cur.execute(
                    """INSERT INTO mtm_outcomes
                       (advice_id, policy_id_used, document_context, outcome_metrics)
                       SELECT gen_random_uuid(), policy_id,
                              jsonb_build_object(
                                  'reason', 'archived_due_to_forgetting',
                                  'original_context_hash', context_hash
                              ),
                              jsonb_build_object(
                                  'final_confidence', confidence_score,
                                  'archived_at', NOW()::text,
                                  'forgetting_mode', 'DAAF_adaptive'
                              )
                       FROM ltm_validated_policies
                       WHERE confidence_score < %s""",
                    (self.confidence_threshold,),
                )

                await cur.execute(
                    """DELETE FROM ltm_validated_policies
                       WHERE confidence_score < %s
                       RETURNING policy_id""",
                    (self.confidence_threshold,),
                )
                deleted = await cur.fetchall()
                if deleted:
                    logger.info(
                        "Forgot %d policies: %s",
                        len(deleted), [r[0] for r in deleted],
                    )

                await conn.commit()
        return affected

    async def _compute_drift_rates(self, conn) -> dict[str, float]:
        """Estimate drift per context from recent MTM rewards."""
        rates: dict[str, float] = {}
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT document_context->>'doc_type' as doc_type,
                          document_context->>'vendor' as vendor,
                          (outcome_metrics->>'f1_score')::float as f1
                   FROM mtm_outcomes
                   WHERE created_at > NOW() - interval '7 days'
                   ORDER BY created_at ASC""",
            )
            rows = await cur.fetchall()

        # Group by context
        rewards_by_ctx: dict[str, list[float]] = {}
        for doc_type, vendor, f1 in rows:
            if f1 is None:
                continue
            key = f"{doc_type}:{vendor}" if vendor else (doc_type or "unknown")
            rewards_by_ctx.setdefault(key, []).append(f1)

        for ctx_key, rewards in rewards_by_ctx.items():
            if len(rewards) >= 5:
                estimator = DriftEstimator(window_size=self.drift_window)
                drift_metrics = None
                for r in rewards:
                    drift_metrics = estimator.update(r)
                if drift_metrics:
                    rates[ctx_key] = drift_metrics.optimal_gamma

        return rates
