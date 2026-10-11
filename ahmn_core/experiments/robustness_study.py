"""
AHMN Robustness Study — Honest evaluation of when AHMN helps and when it doesn't.

Instead of hand-crafted favorable scenarios, this sweeps across the parameters
that determine whether RABI and DAAF are useful:

  Sweep 1: Neighbor similarity (0.1→0.95)  — controls RABI effectiveness
  Sweep 2: Drift magnitude (0.0→0.35)      — controls DAAF effectiveness
  Sweep 3: Cold-start fraction (0%→80%)    — controls RABI relevance
  Sweep 4: Vendor count (2→20)             — controls DAAF sample density

For each sweep, we compare AHMN vs plain Thompson Sampling and measure the
RELATIVE improvement (positive = AHMN wins, negative = AHMN hurts).

This answers the critical question: under what conditions does AHMN actually help?

Usage (from the repository root):
    python -m ahmn_core.experiments.robustness_study
"""

import sys
import os
import json
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ahmn_core.experiments.synthetic_data import (
    Scenario, VendorProfile, DriftEvent, PolicyConfig,
    cosine_similarity, _make_cluster_embedding, POLICY_IDS,
)
from ahmn_core.experiments.run_experiments import (
    ThompsonSamplingRunner, AHMNRABIRunner, AHMNDAAFRunner, AHMNFullRunner,
    run_single, RunResult,
)

N_SEEDS = 20  # Enough for statistical comparison; keeps total runtime < 2 min

def _measure_improvement(
    baseline_results: list[RunResult],
    variant_results: list[RunResult],
    metric: str = "regret",
) -> dict:
    """
    Compute relative improvement of variant over baseline.
    
    Returns dict with mean values, relative improvement %, and raw data
    for downstream statistical testing.
    
    For regret: improvement = (baseline - variant) / baseline * 100  (positive = variant is better)
    For accuracy: improvement = (variant - baseline) / baseline * 100  (positive = variant is better)
    """
    if metric == "regret":
        base_vals = [r.total_regret for r in baseline_results]
        var_vals = [r.total_regret for r in variant_results]
        base_mean = float(np.mean(base_vals))
        var_mean = float(np.mean(var_vals))
        if base_mean > 0:
            improvement_pct = (base_mean - var_mean) / base_mean * 100
        else:
            improvement_pct = 0.0
    elif metric == "accuracy":
        base_vals = [r.policy_accuracy for r in baseline_results]
        var_vals = [r.policy_accuracy for r in variant_results]
        base_mean = float(np.mean(base_vals))
        var_mean = float(np.mean(var_vals))
        if base_mean > 0:
            improvement_pct = (var_mean - base_mean) / base_mean * 100
        else:
            improvement_pct = 0.0
    else:
        raise ValueError(f"Unknown metric: {metric}")

    return {
        "baseline_mean": round(base_mean, 3),
        "baseline_std": round(float(np.std(base_vals)), 3),
        "variant_mean": round(var_mean, 3),
        "variant_std": round(float(np.std(var_vals)), 3),
        "improvement_pct": round(improvement_pct, 2),
    }

# ═══════════════════════════════════════════════════════════════════════════════
# SWEEP 1: Neighbor Similarity → RABI Effectiveness
# ═══════════════════════════════════════════════════════════════════════════════

def sweep_neighbor_similarity(verbose: bool = True) -> dict:
    """
    Question: How similar must a new vendor be to existing ones for RABI to help?
    
    Method: Create 3 established vendors + 3 new vendors.
    Control the cosine similarity between established and new vendor embeddings
    by varying the embedding spread parameter.
    
    At high similarity (spread→0): RABI can transfer accurate priors
    At low similarity (spread→large): RABI transfers from dissimilar contexts = noise
    """
    if verbose:
        print(f"\n{'='*70}")
        print("SWEEP 1: Neighbor Similarity → RABI Effectiveness")
        print(f"{'='*70}")
        print(f"  {'Spread':>8s} {'Cos-Sim':>8s} {'TS Regret':>10s} {'RABI Regret':>12s} {'Improvement':>12s}")
        print(f"  {'-'*8} {'-'*8} {'-'*10} {'-'*12} {'-'*12}")

    # Spread values: small = high similarity, large = low similarity
    spread_values = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1.2, 2.0]
    results = {}

    for spread in spread_values:
        # Build scenario: 3 established + 3 new vendors, same cluster
        established = []
        for i in range(3):
            established.append(VendorProfile(
                vendor_id=f"est_{i}", doc_type="invoice",
                policies={
                    "table_heavy": PolicyConfig(true_mean=0.88, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=0.78, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(1, i, spread=spread),
                weight=1.0,
            ))

        new_vendors = []
        for i in range(3):
            new_vendors.append(VendorProfile(
                vendor_id=f"new_{i}", doc_type="invoice",
                policies={
                    # Similar reward structure — RABI SHOULD help if embeddings are close
                    "table_heavy": PolicyConfig(true_mean=0.86, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.72, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=0.80, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(1, 3 + i, spread=spread),
                appears_at_round=300 + i * 200,
                weight=3.0,
            ))

        scenario = Scenario(
            name=f"cold_start_spread_{spread}",
            description=f"Cold-start with embedding spread={spread}",
            vendors=established + new_vendors,
            policy_ids=POLICY_IDS,
            n_rounds=1200,
        )

        # Measure actual cosine similarity between established and new
        sims = []
        for e in established:
            for n in new_vendors:
                sims.append(cosine_similarity(e.embedding, n.embedding))
        avg_sim = float(np.mean(sims))

        # Run TS baseline vs AHMN-RABI
        ts_results = [run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, s)
                      for s in range(N_SEEDS)]
        rabi_results = [run_single(AHMNRABIRunner(POLICY_IDS), scenario, s)
                        for s in range(N_SEEDS)]

        stats = _measure_improvement(ts_results, rabi_results, "regret")
        stats["avg_similarity"] = round(avg_sim, 4)
        stats["spread"] = spread
        results[str(spread)] = stats

        if verbose:
            sign = "+" if stats["improvement_pct"] > 0 else ""
            print(f"  {spread:8.2f} {avg_sim:8.4f} "
                  f"{stats['baseline_mean']:10.1f} {stats['variant_mean']:12.1f} "
                  f"{sign}{stats['improvement_pct']:11.1f}%")

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# SWEEP 2: Drift Magnitude → DAAF Effectiveness
# ═══════════════════════════════════════════════════════════════════════════════

def sweep_drift_magnitude(verbose: bool = True) -> dict:
    """
    Question: How big must a reward shift be for DAAF to outperform plain TS?
    
    Method: Single vendor, single drift event at round 500.
    Vary the magnitude of reward shift from 0.0 (no drift) to 0.35 (massive).
    The vendor's best policy starts as Tesseract (mean=0.88).
    Drift degrades Tesseract by `magnitude` and boosts Azure by `magnitude`.
    
    At magnitude 0: DAAF forgetting is pure cost (no drift to detect)
    At small magnitude: DAAF may not detect (below threshold)
    At large magnitude: DAAF detects and adapts faster than TS relearns
    """
    if verbose:
        print(f"\n{'='*70}")
        print("SWEEP 2: Drift Magnitude → DAAF Effectiveness")
        print(f"{'='*70}")
        print(f"  {'Δ Reward':>9s} {'TS Regret':>10s} {'TS Acc':>7s} "
              f"{'DAAF Regret':>12s} {'DAAF Acc':>9s} {'Regret Δ%':>10s} {'Acc Δ%':>10s}")
        print(f"  {'-'*9} {'-'*10} {'-'*7} {'-'*12} {'-'*9} {'-'*10} {'-'*10}")

    magnitudes = [0.0, 0.03, 0.06, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35]
    results = {}

    for mag in magnitudes:
        base_mean_tess = 0.88
        base_mean_azure = 0.72

        # After drift: tesseract degrades, azure improves
        post_tess = max(0.1, base_mean_tess - mag)
        post_azure = min(0.98, base_mean_azure + mag)

        vendor = VendorProfile(
            vendor_id="vendor_main", doc_type="invoice",
            policies={
                "table_heavy": PolicyConfig(true_mean=base_mean_tess, noise_std=0.05),
                "forms":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                "mixed_content":  PolicyConfig(true_mean=base_mean_azure, noise_std=0.05),
                "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
            },
            embedding=_make_cluster_embedding(1, 0),
            weight=1.0,
        )

        drift_events = []
        if mag > 0:
            drift_events.append(DriftEvent(
                vendor_id="vendor_main",
                at_round=500,
                new_policies={
                    "table_heavy": PolicyConfig(true_mean=post_tess, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=post_azure, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
            ))

        scenario = Scenario(
            name=f"drift_mag_{mag}",
            description=f"Single vendor, drift magnitude={mag}",
            vendors=[vendor],
            policy_ids=POLICY_IDS,
            n_rounds=1000,
            drift_events=drift_events,
        )

        ts_results = [run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, s)
                      for s in range(N_SEEDS)]
        daaf_results = [run_single(AHMNDAAFRunner(POLICY_IDS), scenario, s)
                        for s in range(N_SEEDS)]

        regret_stats = _measure_improvement(ts_results, daaf_results, "regret")
        acc_stats = _measure_improvement(ts_results, daaf_results, "accuracy")

        results[str(mag)] = {
            "magnitude": mag,
            "regret": regret_stats,
            "accuracy": acc_stats,
        }

        if verbose:
            r_sign = "+" if regret_stats["improvement_pct"] > 0 else ""
            a_sign = "+" if acc_stats["improvement_pct"] > 0 else ""
            ts_acc = float(np.mean([r.policy_accuracy for r in ts_results]))
            daaf_acc = float(np.mean([r.policy_accuracy for r in daaf_results]))
            print(f"  {mag:9.2f} {regret_stats['baseline_mean']:10.1f} {ts_acc:7.3f} "
                  f"{regret_stats['variant_mean']:12.1f} {daaf_acc:9.3f} "
                  f"{r_sign}{regret_stats['improvement_pct']:9.1f}% "
                  f"{a_sign}{acc_stats['improvement_pct']:9.1f}%")

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# SWEEP 3: Cold-Start Fraction → RABI Relevance
# ═══════════════════════════════════════════════════════════════════════════════

def sweep_cold_start_fraction(verbose: bool = True) -> dict:
    """
    Question: What fraction of vendors need to be "new" for RABI to matter?
    
    Method: Fix total 10 vendors, vary how many start vs arrive mid-experiment.
    Established vendors have 500 warmup rounds before first arrival.
    New vendors are in the same cluster (high similarity).
    
    At fraction 0: All vendors are established — RABI is irrelevant
    At high fraction: Most vendors are cold-start — RABI's impact is large
    """
    if verbose:
        print(f"\n{'='*70}")
        print("SWEEP 3: Cold-Start Fraction → RABI Relevance")
        print(f"{'='*70}")
        print(f"  {'Fraction':>9s} {'#New':>5s} {'TS Regret':>10s} {'RABI Regret':>12s} {'Improvement':>12s}")
        print(f"  {'-'*9} {'-'*5} {'-'*10} {'-'*12} {'-'*12}")

    fractions = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    total_vendors = 10
    results = {}

    for frac in fractions:
        n_new = int(round(frac * total_vendors))
        n_est = total_vendors - n_new

        vendors = []
        for i in range(n_est):
            vendors.append(VendorProfile(
                vendor_id=f"est_{i}", doc_type="invoice",
                policies={
                    "table_heavy": PolicyConfig(true_mean=0.85 + 0.01 * i, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=0.78, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(1, i, spread=0.05),
                weight=1.0,
            ))

        for i in range(n_new):
            vendors.append(VendorProfile(
                vendor_id=f"new_{i}", doc_type="invoice",
                policies={
                    "table_heavy": PolicyConfig(true_mean=0.84 + 0.01 * i, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.71, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=0.79, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(1, n_est + i, spread=0.05),
                appears_at_round=500 + i * 100,
                weight=2.0,
            ))

        scenario = Scenario(
            name=f"coldstart_frac_{frac}",
            description=f"Cold-start fraction={frac}",
            vendors=vendors,
            policy_ids=POLICY_IDS,
            n_rounds=500 + n_new * 100 + 500,  # warmup + arrivals + evaluation
        )

        ts_results = [run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, s)
                      for s in range(N_SEEDS)]
        rabi_results = [run_single(AHMNRABIRunner(POLICY_IDS), scenario, s)
                        for s in range(N_SEEDS)]

        stats = _measure_improvement(ts_results, rabi_results, "regret")
        stats["n_new"] = n_new
        stats["n_established"] = n_est
        results[str(frac)] = stats

        if verbose:
            sign = "+" if stats["improvement_pct"] > 0 else ""
            print(f"  {frac:9.1f} {n_new:5d} "
                  f"{stats['baseline_mean']:10.1f} {stats['variant_mean']:12.1f} "
                  f"{sign}{stats['improvement_pct']:11.1f}%")

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# SWEEP 4: Vendor Count / Sample Density → DAAF Effectiveness
# ═══════════════════════════════════════════════════════════════════════════════

def sweep_vendor_count(verbose: bool = True) -> dict:
    """
    Question: How concentrated must sample density be for DAAF to detect drift?
    
    Method: Keep total rounds=1000 fixed. Vary number of vendors (2→20).
    One vendor always drifts at round 500. As vendor count increases,
    the drifting vendor gets fewer samples → DAAF has less signal.
    All vendors equally weighted — no artificial concentration.
    
    At 2 vendors: DAAF gets ~500 samples per vendor — plenty to detect drift
    At 20 vendors: DAAF gets ~50 samples per vendor — may not have enough
    """
    if verbose:
        print(f"\n{'='*70}")
        print("SWEEP 4: Vendor Count → DAAF Sample Density")
        print(f"{'='*70}")
        print(f"  {'#Vendors':>9s} {'Samp/Vnd':>9s} {'TS Regret':>10s} {'TS Acc':>7s} "
              f"{'DAAF Regret':>12s} {'DAAF Acc':>9s} {'Regret Δ%':>10s}")
        print(f"  {'-'*9} {'-'*9} {'-'*10} {'-'*7} {'-'*12} {'-'*9} {'-'*10}")

    vendor_counts = [2, 3, 5, 8, 10, 15, 20]
    n_rounds = 1000
    results = {}

    for n_vendors in vendor_counts:
        vendors = []
        for i in range(n_vendors):
            vendors.append(VendorProfile(
                vendor_id=f"vendor_{i}", doc_type="invoice",
                policies={
                    "table_heavy": PolicyConfig(true_mean=0.88, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.70, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=0.75, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(i, 0),
                weight=1.0,  # EQUAL weight — no artificial concentration
            ))

        # Only vendor_0 drifts
        drift_events = [DriftEvent(
            vendor_id="vendor_0",
            at_round=500,
            new_policies={
                "table_heavy": PolicyConfig(true_mean=0.55, noise_std=0.07),
                "forms":   PolicyConfig(true_mean=0.60, noise_std=0.06),
                "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                "mixed_content":  PolicyConfig(true_mean=0.90, noise_std=0.04),
                "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
            },
        )]

        scenario = Scenario(
            name=f"drift_nvendors_{n_vendors}",
            description=f"Drift with {n_vendors} equal-weight vendors",
            vendors=vendors,
            policy_ids=POLICY_IDS,
            n_rounds=n_rounds,
            drift_events=drift_events,
        )

        ts_results = [run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, s)
                      for s in range(N_SEEDS)]
        daaf_results = [run_single(AHMNDAAFRunner(POLICY_IDS), scenario, s)
                        for s in range(N_SEEDS)]

        regret_stats = _measure_improvement(ts_results, daaf_results, "regret")
        acc_stats = _measure_improvement(ts_results, daaf_results, "accuracy")

        samples_per_vendor = n_rounds // n_vendors
        results[str(n_vendors)] = {
            "n_vendors": n_vendors,
            "samples_per_vendor": samples_per_vendor,
            "regret": regret_stats,
            "accuracy": acc_stats,
        }

        if verbose:
            r_sign = "+" if regret_stats["improvement_pct"] > 0 else ""
            ts_acc = float(np.mean([r.policy_accuracy for r in ts_results]))
            daaf_acc = float(np.mean([r.policy_accuracy for r in daaf_results]))
            print(f"  {n_vendors:9d} {samples_per_vendor:9d} "
                  f"{regret_stats['baseline_mean']:10.1f} {ts_acc:7.3f} "
                  f"{regret_stats['variant_mean']:12.1f} {daaf_acc:9.3f} "
                  f"{r_sign}{regret_stats['improvement_pct']:9.1f}%")

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# SWEEP 5: Reward Structure Mismatch → RABI Failure Mode
# ═══════════════════════════════════════════════════════════════════════════════

def sweep_reward_mismatch(verbose: bool = True) -> dict:
    """
    Question: What happens when RABI transfers from vendors with DIFFERENT
    optimal policies? (The worst case for RABI.)
    
    Method: 3 established vendors where Tesseract is best. 3 new vendors
    where Azure is actually best but embeddings are similar.
    Vary how different the new vendors' reward structure is.
    
    At mismatch 0: new vendors identical to established → RABI helps
    At high mismatch: new vendors have opposite reward rankings → RABI hurts
    """
    if verbose:
        print(f"\n{'='*70}")
        print("SWEEP 5: Reward Mismatch → RABI Failure Mode")
        print(f"{'='*70}")
        print(f"  {'Mismatch':>9s} {'New Best':>9s} {'TS Regret':>10s} {'RABI Regret':>12s} {'Improvement':>12s}")
        print(f"  {'-'*9} {'-'*9} {'-'*10} {'-'*12} {'-'*12}")

    # mismatch: 0.0 = identical ranking, 1.0 = completely reversed
    mismatches = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0]
    results = {}

    for mismatch in mismatches:
        # Established: Tesseract=0.88, Azure=0.70
        established = []
        for i in range(3):
            established.append(VendorProfile(
                vendor_id=f"est_{i}", doc_type="invoice",
                policies={
                    "table_heavy": PolicyConfig(true_mean=0.88, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=0.70, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                embedding=_make_cluster_embedding(1, i, spread=0.05),
                weight=1.0,
            ))

        # New vendors: interpolate between same-ranking and reversed-ranking
        # At mismatch=0: Tesseract=0.88, Azure=0.70 (same as established)
        # At mismatch=1: Tesseract=0.60, Azure=0.90 (reversed)
        new_tess = 0.88 - mismatch * 0.28   # 0.88→0.60
        new_azure = 0.70 + mismatch * 0.20  # 0.70→0.90
        new_best = "table_heavy" if new_tess > new_azure else "mixed_content"

        new_vendors = []
        for i in range(3):
            new_vendors.append(VendorProfile(
                vendor_id=f"new_{i}", doc_type="invoice",
                policies={
                    "table_heavy": PolicyConfig(true_mean=new_tess, noise_std=0.05),
                    "forms":   PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "scanned_text":  PolicyConfig(true_mean=0.65, noise_std=0.06),
                    "mixed_content":  PolicyConfig(true_mean=new_azure, noise_std=0.05),
                    "default":       PolicyConfig(true_mean=0.72, noise_std=0.05),
                },
                # HIGH similarity to established — RABI will definitely try to transfer
                embedding=_make_cluster_embedding(1, 3 + i, spread=0.05),
                appears_at_round=300 + i * 200,
                weight=3.0,
            ))

        scenario = Scenario(
            name=f"mismatch_{mismatch}",
            description=f"Reward mismatch={mismatch}",
            vendors=established + new_vendors,
            policy_ids=POLICY_IDS,
            n_rounds=1200,
        )

        ts_results = [run_single(ThompsonSamplingRunner(POLICY_IDS), scenario, s)
                      for s in range(N_SEEDS)]
        rabi_results = [run_single(AHMNRABIRunner(POLICY_IDS), scenario, s)
                        for s in range(N_SEEDS)]

        stats = _measure_improvement(ts_results, rabi_results, "regret")
        stats["new_best_policy"] = new_best
        stats["new_tess_mean"] = round(new_tess, 2)
        stats["new_azure_mean"] = round(new_azure, 2)
        results[str(mismatch)] = stats

        if verbose:
            sign = "+" if stats["improvement_pct"] > 0 else ""
            print(f"  {mismatch:9.1f} {new_best:>9s} "
                  f"{stats['baseline_mean']:10.1f} {stats['variant_mean']:12.1f} "
                  f"{sign}{stats['improvement_pct']:11.1f}%")

    return results

# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY & CONCLUSIONS
# ═══════════════════════════════════════════════════════════════════════════════

def print_summary(all_results: dict):
    """Print honest conclusions from the robustness sweeps."""
    print(f"\n{'═'*70}")
    print("ROBUSTNESS STUDY SUMMARY — Honest Assessment")
    print(f"{'═'*70}")

    # 1. RABI similarity boundary
    sim_data = all_results.get("neighbor_similarity", {})
    if sim_data:
        print("\n📊 RABI — Neighbor Similarity:")
        positive = [(v["spread"], v["avg_similarity"], v["improvement_pct"])
                    for v in sim_data.values() if v["improvement_pct"] > 1.0]
        negative = [(v["spread"], v["avg_similarity"], v["improvement_pct"])
                    for v in sim_data.values() if v["improvement_pct"] < -1.0]
        neutral = [(v["spread"], v["avg_similarity"], v["improvement_pct"])
                   for v in sim_data.values()
                   if -1.0 <= v["improvement_pct"] <= 1.0]

        if positive:
            best = max(positive, key=lambda x: x[2])
            worst_pos = min(positive, key=lambda x: x[1])
            print(f"   HELPS when cosine similarity > ~{worst_pos[1]:.2f} "
                  f"(best: +{best[2]:.1f}% at sim={best[1]:.2f})")
        if negative:
            worst = min(negative, key=lambda x: x[2])
            print(f"   HURTS when cosine similarity < ~{max(negative, key=lambda x: x[1])[1]:.2f} "
                  f"(worst: {worst[2]:.1f}% at sim={worst[1]:.2f})")
        if neutral:
            print(f"   NEUTRAL in {len(neutral)} settings (|improvement| < 1%)")

    # 2. DAAF drift boundary
    drift_data = all_results.get("drift_magnitude", {})
    if drift_data:
        print("\n📊 DAAF — Drift Magnitude:")
        for key, v in drift_data.items():
            mag = v["magnitude"]
            r_imp = v["regret"]["improvement_pct"]
            a_imp = v["accuracy"]["improvement_pct"]
            if mag == 0.0:
                print(f"   No drift (Δ=0.0): regret {'+' if r_imp > 0 else ''}{r_imp:.1f}%, "
                      f"acc {'+' if a_imp > 0 else ''}{a_imp:.1f}% "
                      f"{'← DAAF cost when unnecessary' if r_imp < 0 else ''}")
            elif abs(r_imp) > 2.0 or abs(a_imp) > 2.0:
                label = "HELPS" if (r_imp > 2.0 or a_imp > 2.0) else "HURTS"
                print(f"   Drift Δ={mag:.2f}: regret {'+' if r_imp > 0 else ''}{r_imp:.1f}%, "
                      f"acc {'+' if a_imp > 0 else ''}{a_imp:.1f}% ← {label}")

    # 3. Cold-start fraction
    cs_data = all_results.get("cold_start_fraction", {})
    if cs_data:
        print("\n📊 RABI — Cold-Start Fraction:")
        for key, v in cs_data.items():
            frac = float(key)
            imp = v["improvement_pct"]
            if frac == 0.0:
                print(f"   No cold-start (0%): {'+' if imp > 0 else ''}{imp:.1f}%"
                      f"{'  ← RABI irrelevant as expected' if abs(imp) < 2 else ''}")
            elif abs(imp) > 2.0:
                print(f"   {int(frac*100)}% new vendors: {'+' if imp > 0 else ''}{imp:.1f}%")

    # 4. Vendor count
    vc_data = all_results.get("vendor_count", {})
    if vc_data:
        print("\n📊 DAAF — Vendor Concentration:")
        for key, v in vc_data.items():
            n = v["n_vendors"]
            spv = v["samples_per_vendor"]
            r_imp = v["regret"]["improvement_pct"]
            print(f"   {n} vendors ({spv} samples/vendor): "
                  f"regret {'+' if r_imp > 0 else ''}{r_imp:.1f}%"
                  f"{'  ← too diluted for DAAF' if r_imp < -2 else ''}")

    # 5. Mismatch (RABI failure mode)
    mm_data = all_results.get("reward_mismatch", {})
    if mm_data:
        print("\n📊 RABI — Reward Mismatch (failure mode):")
        crossover = None
        for key in sorted(mm_data.keys(), key=float):
            v = mm_data[key]
            imp = v["improvement_pct"]
            if imp < 0 and crossover is None:
                crossover = float(key)
            if float(key) in [0.0, 0.3, 0.5, 0.7, 1.0]:
                print(f"   Mismatch={float(key):.1f}: {'+' if imp > 0 else ''}{imp:.1f}% "
                      f"(new best={v['new_best_policy']})")
        if crossover is not None:
            print(f"   ⚠ RABI starts HURTING at mismatch ≈ {crossover:.1f}")

    # Overall
    print(f"\n{'─'*70}")
    print("OVERALL HONEST ASSESSMENT:")
    print("  AHMN is NOT universally better than Thompson Sampling.")
    print("  RABI helps IFF: new vendors are genuinely similar to existing ones")
    print("    (same doc type/format) AND have similar optimal policies.")
    print("  DAAF helps IFF: drift is large enough to detect AND per-vendor")
    print("    sample density is sufficient (enough docs from the drifting vendor).")
    print("  When these conditions DON'T hold, AHMN is equivalent to or slightly")
    print("    worse than plain Thompson Sampling.")
    print(f"{'─'*70}")

def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║         AHMN Robustness Study — Honest Evaluation               ║")
    print("║         When does AHMN help? When does it hurt?                 ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    t_start = time.time()
    all_results = {}

    all_results["neighbor_similarity"] = sweep_neighbor_similarity()
    all_results["drift_magnitude"] = sweep_drift_magnitude()
    all_results["cold_start_fraction"] = sweep_cold_start_fraction()
    all_results["vendor_count"] = sweep_vendor_count()
    all_results["reward_mismatch"] = sweep_reward_mismatch()

    elapsed = time.time() - t_start

    print_summary(all_results)

    # Save results
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "output")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "robustness_results.json")

    # Convert numpy types for JSON serialization
    def serialize(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Not serializable: {type(obj)}")

    with open(out_path, "w") as f:
        json.dump({
            "config": {"n_seeds": N_SEEDS, "total_time_seconds": round(elapsed, 1)},
            "sweeps": all_results,
        }, f, indent=2, default=serialize)

    print(f"\nDone in {elapsed:.1f}s. Results saved to output/robustness_results.json")

if __name__ == "__main__":
    main()
