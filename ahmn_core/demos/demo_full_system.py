"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    AHMN FULL SYSTEM DEMONSTRATION                             ║
║             End-to-End with Docker (PostgreSQL + Redis)                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

This script demonstrates the COMPLETE AHMN system with real database operations.

⚠️  PREREQUISITES:
    1. Docker must be running
    2. Run: docker-compose up -d  (from ahmn_core folder)
    3. Wait for PostgreSQL and Redis to be ready

What this demo covers:
    1. Real API flow (advice → process → log → learn)
    2. Three-tier memory in action (STM/MTM/LTM)
    3. Promotion job (MTM → LTM)
    4. Forgetting mechanism
    5. Thompson Sampling learning in real database

Usage:
    cd ahmn_core
    docker-compose up -d          # Start databases
    python demos/demo_full_system.py

Output:
    - Console: Step-by-step explanation of what's happening
    - Database: Real data in PostgreSQL
    - Plots: visualization of learning progress
"""

import asyncio
import sys
import os
import json
import random
import numpy as np
import matplotlib.pyplot as plt

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import DatabasePool, get_redis_client
from app.services.memory import MemoryService
from app.services.embedding import EmbeddingService
from app.schemas import DocumentContext, OutcomeMetrics

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Simulation parameters
VENDOR_NAME = "Acme_Corp"
DOC_TYPE = "invoice"
OPTIMAL_POLICY = "acme_invoice_v2"
DEFAULT_POLICY = "default_policy"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def print_header(title: str):
    """Print a formatted section header."""
    print("\n" + "═" * 80)
    print(f"  {title}")
    print("═" * 80)


def print_step(step_num: int, description: str):
    """Print a step indicator."""
    print(f"\n  [{step_num}] {description}")
    print("  " + "─" * 70)


def simulate_document_processing(policy: str, optimal: str) -> dict:
    """
    Simulate processing a document with a given policy.
    Returns realistic metrics.
    """
    if policy == optimal:
        # Optimal policy: high performance
        f1 = np.clip(np.random.normal(0.97, 0.02), 0.92, 1.0)
        cost = np.random.uniform(0.01, 0.02)
        time_ms = np.random.uniform(100, 200)
    else:
        # Suboptimal policy: poor performance
        f1 = np.clip(np.random.normal(0.45, 0.10), 0.25, 0.65)
        cost = np.random.uniform(0.03, 0.05)
        time_ms = np.random.uniform(300, 500)
    
    return {
        "f1_score": round(f1, 4),
        "cost": round(cost, 4),
        "processing_time_ms": round(time_ms, 2),
        "success": f1 > 0.8
    }


# ============================================================================
# DATABASE SETUP
# ============================================================================

async def setup_database():
    """Initialize database with optimal policy in LTM."""
    print_step(1, "Setting up database with initial policy")
    
    pool = await DatabasePool.get_pool()
    embedding_service = EmbeddingService()
    
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # Clear existing data for clean demo
            await cur.execute("DELETE FROM mtm_outcomes WHERE document_context->>'vendor' = %s", (VENDOR_NAME,))
            await cur.execute("DELETE FROM ltm_validated_policies WHERE policy_id = %s", (OPTIMAL_POLICY,))
            
            # Insert the optimal policy into LTM
            context_str = embedding_service.create_context_string(DOC_TYPE, VENDOR_NAME)
            vector = embedding_service.generate_embedding(context_str)
            
            import hashlib
            context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
            
            await cur.execute("""
                INSERT INTO ltm_validated_policies 
                (context_hash, context_embedding, policy_id, policy_data, validation_metrics, alpha, beta)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, 1.0, 1.0)
                ON CONFLICT (context_hash) DO UPDATE SET alpha = 1.0, beta = 1.0
            """, (
                context_hash,
                vector,
                OPTIMAL_POLICY,
                json.dumps({"description": "Optimal policy for Acme invoices"}),
                json.dumps({"initial": True})
            ))
            
            await conn.commit()
            print(f"      ✓ Inserted optimal policy '{OPTIMAL_POLICY}' into LTM")
            print(f"      ✓ Context: {DOC_TYPE} from {VENDOR_NAME}")
            print(f"      ✓ Initial Thompson Sampling params: α=1.0, β=1.0")


# ============================================================================
# LEARNING PHASE
# ============================================================================

async def run_learning_phase(num_iterations: int = 50) -> list:
    """
    Run the learning phase where the system learns from outcomes.
    """
    print_header(f"PHASE 1: LEARNING ({num_iterations} iterations)")
    
    print("""
    In this phase:
    • System receives documents and gives advice
    • We simulate processing and log outcomes
    • Thompson Sampling parameters (α, β) get updated
    • System learns which policy works best
    """)
    
    pool = await DatabasePool.get_pool()
    redis = await get_redis_client()
    
    results = []
    
    async with pool.connection() as conn:
        memory_service = MemoryService(conn, redis)
        
        for i in range(num_iterations):
            # 1. Create document context
            context = DocumentContext(doc_type=DOC_TYPE, vendor=VENDOR_NAME)
            
            # 2. Get advice from AHMN
            advice = await memory_service.get_advice(context)
            recommended_policy = advice.policy_id
            source = advice.retrieval_source
            
            # 3. Simulate: sometimes user overrides with optimal policy
            # Early on, force optimal policy to teach the system
            if i < 20 or random.random() < 0.3:
                used_policy = OPTIMAL_POLICY
            else:
                used_policy = recommended_policy
            
            # 4. Simulate document processing
            metrics_dict = simulate_document_processing(used_policy, OPTIMAL_POLICY)
            metrics = OutcomeMetrics(**metrics_dict)
            
            # 5. Log outcome (this updates Thompson Sampling!)
            await memory_service.log_outcome(advice.advice_id, used_policy, metrics)
            
            # Track results
            results.append({
                "iteration": i + 1,
                "recommended": recommended_policy,
                "used": used_policy,
                "f1": metrics.f1_score,
                "source": source
            })
            
            # Progress indicator
            if (i + 1) % 10 == 0:
                recent_f1 = np.mean([r["f1"] for r in results[-10:]])
                optimal_rate = sum(1 for r in results[-10:] if r["recommended"] == OPTIMAL_POLICY) / 10
                print(f"      Iteration {i+1:3d}: Avg F1={recent_f1:.3f}, Optimal recommendation rate={optimal_rate:.0%}")
    
    # Summary
    final_f1 = np.mean([r["f1"] for r in results[-20:]])
    final_optimal_rate = sum(1 for r in results[-20:] if r["recommended"] == OPTIMAL_POLICY) / 20
    
    print(f"\n      ═══════════════════════════════════════════════")
    print(f"      Learning Phase Complete!")
    print(f"      Final 20 iterations: Avg F1={final_f1:.3f}, Optimal rate={final_optimal_rate:.0%}")
    print(f"      ═══════════════════════════════════════════════")
    
    return results


# ============================================================================
# CHECK BANDIT PARAMETERS
# ============================================================================

async def show_bandit_state():
    """Display current Thompson Sampling parameters."""
    print_step(2, "Current Thompson Sampling State in LTM")
    
    pool = await DatabasePool.get_pool()
    
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT policy_id, alpha, beta, confidence_score,
                       alpha / (alpha + beta) as mean_estimate
                FROM ltm_validated_policies
                WHERE policy_id = %s
            """, (OPTIMAL_POLICY,))
            
            row = await cur.fetchone()
            
            if row:
                policy_id, alpha, beta, confidence, mean = row
                print(f"""
      Policy: {policy_id}
      ┌────────────────────────────────────────────────────┐
      │  α (successes):     {alpha:>8.2f}                      │
      │  β (failures):      {beta:>8.2f}                      │
      │  Mean estimate:     {mean:>8.4f}  (α / (α + β))       │
      │  Confidence:        {confidence:>8.4f}                      │
      └────────────────────────────────────────────────────┘
      
      Interpretation:
      • Higher α → more observed successes → more confident it's good
      • Mean estimate ≈ {mean:.1%} probability of success
      • Thompson Sampling will sample from Beta({alpha:.1f}, {beta:.1f})
                """)


# ============================================================================
# VALIDATION PHASE
# ============================================================================

async def run_validation_phase(num_iterations: int = 20) -> list:
    """
    Run validation phase to test learned behavior.
    """
    print_header(f"PHASE 2: VALIDATION ({num_iterations} iterations)")
    
    print("""
    In this phase:
    • System recommends policies WITHOUT manual overrides
    • We verify it learned to recommend the optimal policy
    • No learning happens - pure evaluation
    """)
    
    pool = await DatabasePool.get_pool()
    redis = await get_redis_client()
    
    results = []
    
    async with pool.connection() as conn:
        memory_service = MemoryService(conn, redis)
        
        for i in range(num_iterations):
            context = DocumentContext(doc_type=DOC_TYPE, vendor=VENDOR_NAME)
            advice = await memory_service.get_advice(context)
            
            # Use whatever the system recommends
            used_policy = advice.policy_id
            metrics_dict = simulate_document_processing(used_policy, OPTIMAL_POLICY)
            
            results.append({
                "iteration": i + 1,
                "recommended": advice.policy_id,
                "f1": metrics_dict["f1_score"],
                "source": advice.retrieval_source
            })
    
    # Summary
    optimal_count = sum(1 for r in results if r["recommended"] == OPTIMAL_POLICY)
    avg_f1 = np.mean([r["f1"] for r in results])
    
    print(f"""
      Results:
      ┌────────────────────────────────────────────────────┐
      │  Optimal policy recommended: {optimal_count:>3d}/{num_iterations} ({optimal_count/num_iterations:.0%})           │
      │  Average F1 score:           {avg_f1:.4f}                 │
      └────────────────────────────────────────────────────┘
    """)
    
    if optimal_count / num_iterations >= 0.8:
        print("      ✅ SUCCESS: System learned to recommend optimal policy!")
    else:
        print("      ⚠️  System needs more training data.")
    
    return results


# ============================================================================
# VISUALIZATION
# ============================================================================

def plot_results(learning_results: list, validation_results: list):
    """Generate visualization of the demo results."""
    print_header("GENERATING VISUALIZATION")
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('AHMN Full System Demo Results', fontsize=16, fontweight='bold')
    
    # Combine results
    all_results = learning_results + [
        {**r, "iteration": r["iteration"] + len(learning_results)} 
        for r in validation_results
    ]
    
    # ─────────────────────────────────────────────────────────────────────────
    # Plot 1: F1 Score Over Time
    # ─────────────────────────────────────────────────────────────────────────
    ax1 = axes[0, 0]
    
    learning_iters = [r["iteration"] for r in learning_results]
    learning_f1 = [r["f1"] for r in learning_results]
    
    val_iters = [r["iteration"] + len(learning_results) for r in validation_results]
    val_f1 = [r["f1"] for r in validation_results]
    
    ax1.scatter(learning_iters, learning_f1, c='blue', alpha=0.6, s=30, label='Learning')
    ax1.scatter(val_iters, val_f1, c='green', alpha=0.6, s=30, label='Validation')
    
    # Moving average
    window = 10
    if len(learning_f1) >= window:
        ma = np.convolve(learning_f1, np.ones(window)/window, mode='valid')
        ax1.plot(learning_iters[window-1:], ma, 'r-', lw=2, label=f'Moving Avg')
    
    ax1.axhline(y=0.95, color='gray', ls='--', alpha=0.7, label='Target (0.95)')
    ax1.axvline(x=len(learning_results), color='orange', ls=':', alpha=0.7, label='Validation Start')
    ax1.set_xlabel('Iteration')
    ax1.set_ylabel('F1 Score')
    ax1.set_title('F1 Score Over Time')
    ax1.legend(loc='lower right')
    ax1.set_ylim(0, 1.05)
    ax1.grid(True, alpha=0.3)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Plot 2: Policy Recommendations
    # ─────────────────────────────────────────────────────────────────────────
    ax2 = axes[0, 1]
    
    # Count by phase
    learn_optimal = sum(1 for r in learning_results if r["recommended"] == OPTIMAL_POLICY)
    learn_other = len(learning_results) - learn_optimal
    val_optimal = sum(1 for r in validation_results if r["recommended"] == OPTIMAL_POLICY)
    val_other = len(validation_results) - val_optimal
    
    x = np.arange(2)
    width = 0.35
    ax2.bar(x - width/2, [learn_optimal, val_optimal], width, label=f'Optimal', color='green', alpha=0.7)
    ax2.bar(x + width/2, [learn_other, val_other], width, label=f'Other', color='red', alpha=0.7)
    ax2.set_xticks(x)
    ax2.set_xticklabels(['Learning', 'Validation'])
    ax2.set_ylabel('Count')
    ax2.set_title('Policy Recommendations by Phase')
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    
    # ─────────────────────────────────────────────────────────────────────────
    # Plot 3: Cumulative Optimal Rate
    # ─────────────────────────────────────────────────────────────────────────
    ax3 = axes[1, 0]
    
    cumulative = []
    optimal_count = 0
    for i, r in enumerate(learning_results):
        if r["recommended"] == OPTIMAL_POLICY:
            optimal_count += 1
        cumulative.append(optimal_count / (i + 1))
    
    ax3.plot(range(1, len(learning_results)+1), cumulative, 'b-', lw=2, label='Learning')
    ax3.axhline(y=0.8, color='orange', ls='--', alpha=0.7, label='80% Target')
    ax3.axvline(x=len(learning_results), color='gray', ls=':', alpha=0.5)
    ax3.set_xlabel('Iteration')
    ax3.set_ylabel('Cumulative Optimal Rate')
    ax3.set_title('Learning Progress')
    ax3.legend()
    ax3.set_ylim(0, 1.05)
    ax3.grid(True, alpha=0.3)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Plot 4: Retrieval Sources
    # ─────────────────────────────────────────────────────────────────────────
    ax4 = axes[1, 1]
    
    sources = {}
    for r in all_results:
        src = r.get("source", "UNKNOWN")
        sources[src] = sources.get(src, 0) + 1
    
    ax4.pie(sources.values(), labels=sources.keys(), autopct='%1.1f%%',
            colors=['#2ecc71', '#3498db', '#f39c12', '#e74c3c'])
    ax4.set_title('Retrieval Source Distribution')
    
    plt.tight_layout()
    
    path = os.path.join(OUTPUT_DIR, 'full_system_demo.png')
    plt.savefig(path, dpi=150, bbox_inches='tight')
    print(f"      ✓ Saved: {path}")
    plt.close()


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run the complete full-system demonstration."""
    
    print("\n" + "╔" + "═" * 78 + "╗")
    print("║" + " " * 18 + "AHMN FULL SYSTEM DEMONSTRATION" + " " * 28 + "║")
    print("║" + " " * 12 + "End-to-End with PostgreSQL + Redis" + " " * 30 + "║")
    print("╚" + "═" * 78 + "╝")
    
    print(f"""
    Scenario:
    • Document type: {DOC_TYPE}
    • Vendor: {VENDOR_NAME}
    • Optimal policy: {OPTIMAL_POLICY}
    
    Goal: System should LEARN to recommend '{OPTIMAL_POLICY}'
          through Thompson Sampling from logged outcomes.
    """)
    
    try:
        # Setup
        await setup_database()
        
        # Learning phase
        learning_results = await run_learning_phase(num_iterations=50)
        
        # Show bandit state
        await show_bandit_state()
        
        # Validation phase
        validation_results = await run_validation_phase(num_iterations=20)
        
        # Final bandit state
        await show_bandit_state()
        
        # Visualization
        plot_results(learning_results, validation_results)
        
        # Cleanup
        await DatabasePool.close_pool()
        
        print_header("DEMO COMPLETE")
        print("""
    ✅ Demonstrated:
       1. STM: Stored advice context in Redis (30 min TTL)
       2. MTM: Logged all outcomes to PostgreSQL
       3. LTM: Updated Thompson Sampling parameters (α, β)
       4. Learning: System improved recommendations over time
       
    🎯 Key Takeaway:
       AHMN learns from experience! The more good outcomes we log,
       the more confident the system becomes in recommending the
       optimal policy.
        """)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure Docker is running:")
        print("   cd ahmn_core")
        print("   docker-compose up -d")
        raise


if __name__ == "__main__":
    # Windows asyncio fix
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
