import asyncio
import sys
import os
import random
import uuid
import json
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import DatabasePool, get_redis_client
from app.services.memory import MemoryService
from app.schemas import DocumentContext, OutcomeMetrics
from jobs.promote import promote_strategies

# Simulation Constants
VENDOR_NAME = "Acme_Corp"
DOC_TYPE = "invoice"
OPTIMAL_POLICY = "acme_invoice_v2"
DEFAULT_POLICY = "default_policy"

async def run_simulation():
    print(f"--- Starting AHMN Research Simulation ---")
    print(f"Scenario: Processing {DOC_TYPE}s from {VENDOR_NAME}")
    print(f"Goal: System should learn to recommend '{OPTIMAL_POLICY}' instead of '{DEFAULT_POLICY}'")
    
    # Initialize Resources
    pool = await DatabasePool.get_pool()
    redis = await get_redis_client()
    
    # We need a raw connection for MemoryService as per its signature, 
    # but MemoryService takes a connection, not a pool. 
    # However, in main.py it gets a connection from dependency.
    # We will manage a connection manually here.
    
    async with pool.connection() as db_conn:
        memory_service = MemoryService(db_conn, redis)
        
        results = []
        
        # --- PHASE 1: The "Learning" Phase (Data Collection) ---
        print("\n[Phase 1] Simulating Traffic & Data Collection (20 iterations)")
        print("System is currently ignorant. We will simulate manual overrides/corrections.")
        
        for i in range(20):
            # 1. Ask for Advice
            context = DocumentContext(doc_type=DOC_TYPE, vendor=VENDOR_NAME)
            advice = await memory_service.get_advice(context)
            
            # 2. Simulate Execution Outcome
            # In the real world, a human might override the default policy, 
            # or we might run an A/B test.
            # We simulate that 40% of the time, we manually force the "Correct" policy
            # to generate training data.
            
            used_policy = advice.policy_id
            forced_override = False
            
            if random.random() < 0.4: # 40% chance we know better
                used_policy = OPTIMAL_POLICY
                forced_override = True
            
            # Calculate Score based on policy used
            if used_policy == OPTIMAL_POLICY:
                f1 = random.uniform(0.96, 0.99)
                success = True
            else:
                f1 = random.uniform(0.30, 0.60) # Default policy sucks for this vendor
                success = False
                
            # 3. Log the Outcome
            metrics = OutcomeMetrics(
                f1_score=f1,
                cost=0.01,
                processing_time_ms=150,
                success=success
            )
            
            await memory_service.log_outcome(advice.advice_id, used_policy, metrics)
            
            results.append({
                "phase": "learning",
                "iteration": i,
                "recommended": advice.policy_id,
                "used": used_policy,
                "f1": f1,
                "source": advice.retrieval_source
            })
            
            print(f"  Iter {i+1}: Rec={advice.policy_id} | Used={used_policy} ({'Override' if forced_override else 'Auto'}) | F1={f1:.2f}")

        # --- PHASE 2: The "Sleep" Phase (Consolidation) ---
        print("\n[Phase 2] Running Promotion Job (Learning from Experience)...")
        # We need to close the db connection before calling promote because promote creates its own pool
        # Actually promote uses DatabasePool.get_pool() which is a singleton-ish pattern in some impls,
        # but let's just call it. The promote script creates a pool.
        # To avoid conflicts, we'll just call the logic.
        
    # Close our connection so promote can run cleanly
    await DatabasePool.close_pool()
    
    # Run the promotion job
    await promote_strategies()
    
    # Re-open connection for Phase 3
    pool = await DatabasePool.get_pool()
    async with pool.connection() as db_conn:
        memory_service = MemoryService(db_conn, redis)

        # --- PHASE 3: The "Mastery" Phase (Validation) ---
        print("\n[Phase 3] Validating Learned Behavior (10 iterations)")
        print("System should now recommend the optimal policy automatically.")
        
        success_count = 0
        
        for i in range(10):
            context = DocumentContext(doc_type=DOC_TYPE, vendor=VENDOR_NAME)
            advice = await memory_service.get_advice(context)
            
            # Now we just trust the system
            used_policy = advice.policy_id
            
            if used_policy == OPTIMAL_POLICY:
                f1 = random.uniform(0.96, 0.99)
                success_count += 1
            else:
                f1 = random.uniform(0.30, 0.60)
                
            results.append({
                "phase": "validation",
                "iteration": i + 20,
                "recommended": advice.policy_id,
                "used": used_policy,
                "f1": f1,
                "source": advice.retrieval_source
            })
            
            print(f"  Iter {i+1}: Rec={advice.policy_id} | Source={advice.retrieval_source} | F1={f1:.2f}")

    await DatabasePool.close_pool()
    
    # --- REPORTING ---
    print("\n--- Simulation Results ---")
    print(f"Phase 1 (Learning) Optimal Policy Usage: {len([r for r in results if r['phase']=='learning' and r['used']==OPTIMAL_POLICY])}/20")
    print(f"Phase 3 (Validation) Optimal Policy Recommendation: {success_count}/10")
    
    if success_count >= 8:
        print("\nSUCCESS: System successfully learned the optimal strategy!")
    else:
        print("\nFAILURE: System did not learn the strategy. Check thresholds.")

    # Save results for plotting
    with open("simulation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nDetailed results saved to 'simulation_results.json'")

if __name__ == "__main__":
    asyncio.run(run_simulation())
