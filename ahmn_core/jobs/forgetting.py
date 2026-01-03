import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import DatabasePool

async def forgetting_mechanism():
    """Apply exponential decay to inactive policies and archive low-confidence strategies."""
    print("Starting Forgetting Mechanism Job...")
    
    pool = await DatabasePool.get_pool()
    
    DECAY_RATE = 0.05
    THRESHOLD = 0.4
    INACTIVITY_DAYS = 7

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            print(f"Applying decay to policies inactive for > {INACTIVITY_DAYS} days...")
            
            decay_query = """
                UPDATE ltm_validated_policies
                SET confidence_score = confidence_score * (1.0 - %s)
                WHERE last_promoted_at < NOW() - INTERVAL '%s days'
                RETURNING id, policy_id, confidence_score;
            """
            
            await cur.execute(decay_query, (DECAY_RATE, INACTIVITY_DAYS))
            decayed_rows = await cur.fetchall()
            
            print(f"Decayed {len(decayed_rows)} policies.")
            for row in decayed_rows:
                print(f"  Policy {row[1]} decayed to {row[2]:.4f}")

            print(f"Checking for policies below confidence threshold ({THRESHOLD})...")
            
            archive_query = """
                INSERT INTO mtm_outcomes (advice_id, policy_id_used, document_context, outcome_metrics)
                SELECT 
                    gen_random_uuid(), 
                    policy_id, 
                    jsonb_build_object('reason', 'archived_due_to_forgetting', 'original_context_hash', context_hash),
                    jsonb_build_object('final_confidence', confidence_score, 'archived_at', NOW())
                FROM ltm_validated_policies
                WHERE confidence_score < %s
            """
            
            await cur.execute(archive_query, (THRESHOLD,))
            
            delete_query = """
                DELETE FROM ltm_validated_policies
                WHERE confidence_score < %s
                RETURNING policy_id;
            """
            
            await cur.execute(delete_query, (THRESHOLD,))
            deleted_rows = await cur.fetchall()
            
            print(f"Archived and removed {len(deleted_rows)} forgotten policies.")
            for row in deleted_rows:
                print(f"  Forgot: {row[0]}")

            await conn.commit()
            print("Forgetting job completed.")

    await DatabasePool.close_pool()

if __name__ == "__main__":
    # Fix for Windows: psycopg async requires SelectorEventLoop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(forgetting_mechanism())
