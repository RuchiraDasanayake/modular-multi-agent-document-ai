"""
Drift-Aware Adaptive Forgetting (DAAF) Job.

Replaces fixed-rate memory decay with an adaptive mechanism that estimates
drift from recent rewards and computes optimal forgetting rate γ* = √(σ²/ln(t)).
Achieves O(√(σ²·T·ln T)) regret under bounded drift.
"""

import asyncio
import logging
import sys
import os
import math
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg_pool import AsyncConnectionPool
from ahmn_core.services.drift_forgetting import (
    DriftEstimator, 
    AdaptiveForgettingBandit,
    create_adaptive_forgetting_bandit
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

POSTGRES_URI = os.getenv(
    "POSTGRES_URI", "postgresql://user:password@localhost:5432/ahmn_db"
)

class DAAFForgettingJob:
    """
    Drift-Aware Adaptive Forgetting (DAAF) job.
    
    This replaces fixed-rate forgetting with an adaptive mechanism that:
    1. Estimates drift from recent reward signals
    2. Computes optimal forgetting rate γ* = √(σ²/ln(t))
    3. Applies context-aware decay based on environment volatility
    
    Theoretical Contribution:
    - Adapts to non-stationary environments automatically
    - Proven regret bound: O(√(σ²·T·ln T)) under bounded drift
    """
    
    def __init__(
        self,
        use_daaf: bool = True,
        base_decay_rate: float = 0.05,
        threshold: float = 0.4,
        inactivity_days: int = 7,
        drift_window: int = 50
    ):
        self.use_daaf = use_daaf
        self.base_decay_rate = base_decay_rate
        self.threshold = threshold
        self.inactivity_days = inactivity_days
        
        if use_daaf:
            self.daaf = create_adaptive_forgetting_bandit(
                window_size=drift_window,
                sensitivity=1.0
            )
            self.drift_estimator = DriftEstimator(window_size=drift_window)
        else:
            self.daaf = None
            self.drift_estimator = None
    
    async def get_recent_rewards(self, conn, days: int = 7) -> dict[str, list[float]]:
        """Fetch recent rewards per context for drift estimation."""
        query = """
            SELECT 
                document_context->>'doc_type' as doc_type,
                document_context->>'vendor' as vendor,
                outcome_metrics->>'f1_score' as f1_score,
                created_at
            FROM mtm_outcomes
            WHERE created_at > NOW() - %s::interval
            ORDER BY created_at ASC;
        """
        
        rewards_by_context: dict[str, list[float]] = {}
        
        async with conn.cursor() as cur:
            await cur.execute(query, (timedelta(days=days),))
            rows = await cur.fetchall()
            
            for row in rows:
                doc_type, vendor, f1_str, _ = row
                context_key = f"{doc_type}:{vendor}" if vendor else doc_type
                
                if f1_str:
                    try:
                        f1 = float(f1_str)
                        if context_key not in rewards_by_context:
                            rewards_by_context[context_key] = []
                        rewards_by_context[context_key].append(f1)
                    except ValueError:
                        pass
        
        return rewards_by_context
    
    async def compute_adaptive_decay_rates(
        self, 
        conn, 
        global_timestep: int
    ) -> dict[str, float]:
        """
        Compute per-context adaptive decay rates using DAAF.
        
        Returns:
            Dict mapping context_key -> optimal_gamma
        """
        if not self.use_daaf:
            return {}
        
        # Get recent rewards for drift estimation
        rewards_by_context = await self.get_recent_rewards(conn)
        
        decay_rates: dict[str, float] = {}
        
        for context_key, rewards in rewards_by_context.items():
            if len(rewards) >= 5:  # Need minimum samples for drift estimation
                # Create fresh estimator for this context
                window = self.drift_estimator.window_size if self.drift_estimator else 50
                context_estimator = DriftEstimator(window_size=window)
                
                # Update drift estimator with recent rewards
                drift_metrics = None
                for r in rewards:
                    drift_metrics = context_estimator.update(r)
                
                # Get optimal gamma from the last update
                if drift_metrics:
                    gamma_star = drift_metrics.optimal_gamma
                    decay_rates[context_key] = gamma_star
        
        return decay_rates
    
    async def run(self):
        """Execute the DAAF forgetting mechanism."""
        logger.info(
            "Starting DAAF job: mode=%s base_decay=%.3f threshold=%.2f",
            "DAAF" if self.use_daaf else "fixed", self.base_decay_rate, self.threshold,
        )
        
        pool = AsyncConnectionPool(conninfo=POSTGRES_URI, open=False, min_size=1, max_size=5)
        await pool.open()
        
        try:
            async with pool.connection() as conn:
                # Get global timestep (total interactions)
                async with conn.cursor() as cur:
                    await cur.execute("SELECT COUNT(*) FROM mtm_outcomes")
                    result = await cur.fetchone()
                    global_timestep = (result[0] if result else 0) or 1

                logger.info("Global timestep: %d", global_timestep)

                # Compute adaptive decay rates if DAAF enabled
                if self.use_daaf:
                    adaptive_rates = await self.compute_adaptive_decay_rates(
                        conn, global_timestep
                    )
                    logger.info("Adaptive decay rates computed for %d contexts", len(adaptive_rates))
                    for ctx, gamma in list(adaptive_rates.items())[:5]:
                        logger.debug("  %s: γ* = %.6f", ctx, gamma)
                else:
                    adaptive_rates = {}

                async with conn.cursor() as cur:
                    # Apply decay - adaptive or fixed
                    logger.info("Applying decay to policies inactive for > %d days", self.inactivity_days)

                    # First, get policies that need decay
                    fetch_query = """
                        SELECT id, policy_id, context_hash, confidence_score,
                               (SELECT document_context->>'doc_type'
                                FROM mtm_outcomes mo
                                WHERE mo.policy_id_used = ltm.policy_id
                                LIMIT 1) as doc_type,
                               (SELECT document_context->>'vendor'
                                FROM mtm_outcomes mo
                                WHERE mo.policy_id_used = ltm.policy_id
                                LIMIT 1) as vendor
                        FROM ltm_validated_policies ltm
                        WHERE last_promoted_at < NOW() - %s::interval
                    """

                    await cur.execute(fetch_query, (timedelta(days=self.inactivity_days),))
                    policies_to_decay = await cur.fetchall()

                    decayed_count = 0
                    daaf_applied = 0

                    for row in policies_to_decay:
                        policy_id_db, policy_id, context_hash, conf_score, doc_type, vendor = row

                        # Determine decay rate
                        if self.use_daaf and doc_type:
                            context_key = f"{doc_type}:{vendor}" if vendor else doc_type
                            decay_rate = adaptive_rates.get(context_key, self.base_decay_rate)
                            if context_key in adaptive_rates:
                                daaf_applied += 1
                        else:
                            decay_rate = self.base_decay_rate

                        # Apply decay
                        new_conf = conf_score * (1.0 - decay_rate)

                        update_query = """
                            UPDATE ltm_validated_policies
                            SET confidence_score = %s
                            WHERE id = %s
                        """
                        await cur.execute(update_query, (new_conf, policy_id_db))
                        decayed_count += 1

                        logger.debug("%s: %.4f -> %.4f (γ=%.4f)", policy_id, conf_score, new_conf, decay_rate)

                    logger.info("Decayed %d policies (%d with DAAF adaptive rates)", decayed_count, daaf_applied)

                    # Archive and remove low-confidence policies
                    logger.info("Checking for policies below confidence threshold (%.2f)", self.threshold)

                    archive_query = """
                        INSERT INTO mtm_outcomes (advice_id, policy_id_used, document_context, outcome_metrics)
                        SELECT
                            gen_random_uuid(),
                            policy_id,
                            jsonb_build_object(
                                'reason', 'archived_due_to_forgetting',
                                'original_context_hash', context_hash,
                                'daaf_enabled', %s
                            ),
                            jsonb_build_object(
                                'final_confidence', confidence_score,
                                'archived_at', NOW(),
                                'forgetting_mode', %s
                            )
                        FROM ltm_validated_policies
                        WHERE confidence_score < %s
                    """

                    mode = 'DAAF_adaptive' if self.use_daaf else 'fixed_rate'
                    await cur.execute(archive_query, (self.use_daaf, mode, self.threshold))

                    delete_query = """
                        DELETE FROM ltm_validated_policies
                        WHERE confidence_score < %s
                        RETURNING policy_id;
                    """

                    await cur.execute(delete_query, (self.threshold,))
                    deleted_rows = await cur.fetchall()

                    logger.info("Archived and removed %d forgotten policies", len(deleted_rows))
                    for row in deleted_rows:
                        logger.debug("Forgot: %s", row[0])

                    await conn.commit()

            logger.info("DAAF forgetting job completed")
        finally:
            await pool.close()

async def forgetting_mechanism():
    """
    Legacy function for backward compatibility.
    Now uses DAAF by default.
    """
    job = DAAFForgettingJob(use_daaf=True)
    await job.run()

async def fixed_rate_forgetting():
    """Run forgetting with fixed decay rate (no DAAF)."""
    job = DAAFForgettingJob(use_daaf=False)
    await job.run()

if __name__ == "__main__":
    # Fix for Windows: psycopg async requires SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # Check for --no-daaf flag
    use_daaf = "--no-daaf" not in sys.argv
    
    job = DAAFForgettingJob(use_daaf=use_daaf)
    asyncio.run(job.run())
