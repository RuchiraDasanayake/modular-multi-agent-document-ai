import asyncio
import sys
import os
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.database import DatabasePool
from ahmn_core.services.drift_forgetting import (
    DriftEstimator, 
    AdaptiveForgettingBandit,
    create_adaptive_forgetting_bandit
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
    
    async def get_recent_rewards(self, conn, days: int = 7) -> Dict[str, List[float]]:
        """Fetch recent rewards per context for drift estimation."""
        query = """
            SELECT 
                document_context->>'doc_type' as doc_type,
                document_context->>'vendor' as vendor,
                outcome_metrics->>'f1_score' as f1_score,
                created_at
            FROM mtm_outcomes
            WHERE created_at > NOW() - INTERVAL '%s days'
            ORDER BY created_at ASC;
        """
        
        rewards_by_context: Dict[str, List[float]] = {}
        
        async with conn.cursor() as cur:
            await cur.execute(query, (days,))
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
    ) -> Dict[str, float]:
        """
        Compute per-context adaptive decay rates using DAAF.
        
        Returns:
            Dict mapping context_key -> optimal_gamma
        """
        if not self.use_daaf:
            return {}
        
        # Get recent rewards for drift estimation
        rewards_by_context = await self.get_recent_rewards(conn)
        
        decay_rates: Dict[str, float] = {}
        
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
        print("=" * 60)
        print("Starting Drift-Aware Adaptive Forgetting (DAAF) Job...")
        print(f"  Mode: {'DAAF (adaptive)' if self.use_daaf else 'Fixed rate'}")
        print(f"  Base decay rate: {self.base_decay_rate}")
        print(f"  Threshold: {self.threshold}")
        print("=" * 60)
        
        pool = await DatabasePool.get_pool()
        
        async with pool.connection() as conn:
            # Get global timestep (total interactions)
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM mtm_outcomes")
                result = await cur.fetchone()
                global_timestep = (result[0] if result else 0) or 1
            
            print(f"\nGlobal timestep: {global_timestep}")
            
            # Compute adaptive decay rates if DAAF enabled
            if self.use_daaf:
                adaptive_rates = await self.compute_adaptive_decay_rates(
                    conn, global_timestep
                )
                print(f"\nAdaptive decay rates computed for {len(adaptive_rates)} contexts:")
                for ctx, gamma in list(adaptive_rates.items())[:5]:
                    print(f"  {ctx}: γ* = {gamma:.6f}")
                if len(adaptive_rates) > 5:
                    print(f"  ... and {len(adaptive_rates) - 5} more")
            else:
                adaptive_rates = {}
            
            async with conn.cursor() as cur:
                # Apply decay - adaptive or fixed
                print(f"\nApplying decay to policies inactive for > {self.inactivity_days} days...")
                
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
                    WHERE last_promoted_at < NOW() - INTERVAL '%s days'
                """
                
                await cur.execute(fetch_query, (self.inactivity_days,))
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
                    
                    print(f"  {policy_id}: {conf_score:.4f} -> {new_conf:.4f} (γ={decay_rate:.4f})")
                
                print(f"\nDecayed {decayed_count} policies ({daaf_applied} with DAAF adaptive rates)")

                # Archive and remove low-confidence policies
                print(f"\nChecking for policies below confidence threshold ({self.threshold})...")
                
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
                
                print(f"Archived and removed {len(deleted_rows)} forgotten policies.")
                for row in deleted_rows:
                    print(f"  Forgot: {row[0]}")

                await conn.commit()
                
        print("\n" + "=" * 60)
        print("DAAF Forgetting job completed.")
        print("=" * 60)
        
        await DatabasePool.close_pool()


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
