"""
AHMN Experimental Results Analysis.

Reads experiment_results.json and produces:
  1. Summary comparison table (for paper)
  2. Per-scenario breakdown
  3. Statistical significance tests (Mann-Whitney U)
  4. Ablation study summaries
  5. Data structures ready for matplotlib/seaborn plotting

Usage:
    cd ahmn_core
    python -m experiments.analysis
"""

import json
import os
import sys
import numpy as np
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# scipy for statistical tests
try:
    from scipy import stats as sp_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


def load_results(path: Optional[str] = None) -> Dict:
    """Load experiment results from JSON."""
    if path is None:
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "ahmn_core", "output", "experiment_results.json"
        )
        if not os.path.exists(path):
            # Try relative
            path = os.path.join("output", "experiment_results.json")
    
    with open(path) as f:
        return json.load(f)


def group_results(results: List[Dict]) -> Dict[str, Dict[str, List[Dict]]]:
    """Group results by scenario → method → [seed results]."""
    grouped = defaultdict(lambda: defaultdict(list))
    for r in results:
        grouped[r["scenario"]][r["method"]].append(r)
    return dict(grouped)


def print_main_comparison_table(results: List[Dict]):
    """
    Print the main comparison table suitable for a research paper.
    
    Table format:
    Method       | Scenario     | Regret (mean±std) | Final F1 | Accuracy | Convergence
    """
    grouped = group_results(results)
    
    method_order = ["Random", "ε-Greedy", "UCB1", "TS (base)",
                    "AHMN-RABI", "AHMN-DAAF", "AHMN-Full"]
    scenario_order = ["stationary", "cold_start", "concept_drift", "combined"]
    
    print("\n" + "=" * 100)
    print("TABLE 1: Main Performance Comparison (mean ± std over 30 seeds)")
    print("=" * 100)
    
    for scenario_name in scenario_order:
        if scenario_name not in grouped:
            continue
        
        scenario_data = grouped[scenario_name]
        print(f"\n  Scenario: {scenario_name}")
        print(f"  {'Method':<16s} {'Regret':>14s}  {'Final F1':>14s}  {'Accuracy':>10s}  {'Conv. Round':>12s}")
        print(f"  {'-'*16} {'-'*14}  {'-'*14}  {'-'*10}  {'-'*12}")
        
        for method in method_order:
            if method not in scenario_data:
                continue
            
            runs = scenario_data[method]
            regrets = [r["total_regret"] for r in runs]
            rewards = [r["final_avg_reward"] for r in runs]
            accs = [r["policy_accuracy"] for r in runs]
            convs = [r["convergence_round"] for r in runs if r["convergence_round"] is not None]
            
            reg_str = f"{np.mean(regrets):6.1f} ± {np.std(regrets):5.1f}"
            rew_str = f"{np.mean(rewards):.4f} ± {np.std(rewards):.4f}"
            acc_str = f"{np.mean(accs):.4f}"
            conv_str = f"{int(np.mean(convs)):>5d}" if convs else "  N/A"
            
            # Mark best method with asterisk
            marker = " "
            print(f"  {method:<16s} {reg_str:>14s}  {rew_str:>14s}  {acc_str:>10s}  {conv_str:>12s}{marker}")


def print_statistical_tests(results: List[Dict]):
    """
    Pairwise Mann-Whitney U tests: AHMN-Full vs. each baseline.
    
    Reports p-values for regret comparison.
    """
    if not HAS_SCIPY:
        print("\n[WARN] scipy not installed — skipping statistical tests.")
        print("       Install with: pip install scipy")
        return
    
    grouped = group_results(results)
    
    print("\n" + "=" * 80)
    print("TABLE 2: Statistical Significance — AHMN-Full vs. Baselines (Mann-Whitney U)")
    print("=" * 80)
    print(f"  {'Scenario':<16s} {'Baseline':<16s} {'U-statistic':>12s}  {'p-value':>10s}  {'Significant':>12s}")
    print(f"  {'-'*16} {'-'*16} {'-'*12}  {'-'*10}  {'-'*12}")
    
    baselines = ["Random", "ε-Greedy", "UCB1", "TS (base)", "AHMN-RABI", "AHMN-DAAF"]
    
    for scenario_name, scenario_data in grouped.items():
        if "AHMN-Full" not in scenario_data:
            continue
        
        ahmn_regrets = [r["total_regret"] for r in scenario_data["AHMN-Full"]]
        
        for baseline in baselines:
            if baseline not in scenario_data:
                continue
            
            base_regrets = [r["total_regret"] for r in scenario_data[baseline]]
            
            U, p = sp_stats.mannwhitneyu(ahmn_regrets, base_regrets, alternative="less")
            sig = "Yes (p<0.05)" if p < 0.05 else "No"
            
            print(f"  {scenario_name:<16s} {baseline:<16s} {U:>12.1f}  {p:>10.4f}  {sig:>12s}")


def print_ablation_summary(data: Dict, ablation_key: str, param_name: str):
    """Print ablation study results."""
    if ablation_key not in data:
        return
    
    ablation = data[ablation_key]
    
    print(f"\n  {param_name:<12s} {'Regret (mean±std)':>20s}  {'Final F1 (mean±std)':>20s}")
    print(f"  {'-'*12} {'-'*20}  {'-'*20}")
    
    for param_val, metrics in sorted(ablation.items(), key=lambda x: float(x[0])):
        reg_str = f"{metrics['regret_mean']:6.1f} ± {metrics['regret_std']:5.1f}"
        rew_str = f"{metrics['reward_mean']:.4f} ± {metrics['reward_std']:.4f}"
        print(f"  {param_val:<12s} {reg_str:>20s}  {rew_str:>20s}")


def print_latex_table(results: List[Dict]):
    """Generate a LaTeX-ready table for the paper."""
    grouped = group_results(results)
    
    method_order = ["Random", "ε-Greedy", "UCB1", "TS (base)",
                    "AHMN-RABI", "AHMN-DAAF", "AHMN-Full"]
    
    print("\n" + "=" * 80)
    print("LaTeX Table (copy-paste into paper)")
    print("=" * 80)
    print(r"\begin{table}[h]")
    print(r"\centering")
    print(r"\caption{Performance comparison across scenarios (mean $\pm$ std, 30 seeds)}")
    print(r"\label{tab:main_results}")
    print(r"\begin{tabular}{l|rr|rr}")
    print(r"\hline")
    print(r"\textbf{Method} & \multicolumn{2}{c|}{\textbf{Cumulative Regret}} & \multicolumn{2}{c}{\textbf{Final F1}} \\")
    print(r"                & Stationary & Drift & Stationary & Drift \\")
    print(r"\hline")
    
    for method in method_order:
        parts = [method.replace("ε", r"$\epsilon$")]
        for scenario in ["stationary", "concept_drift"]:
            if scenario in grouped and method in grouped[scenario]:
                runs = grouped[scenario][method]
                regrets = [r["total_regret"] for r in runs]
                rewards = [r["final_avg_reward"] for r in runs]
                parts.append(f"${np.mean(regrets):.1f} \\pm {np.std(regrets):.1f}$")
                parts.append(f"${np.mean(rewards):.3f} \\pm {np.std(rewards):.3f}$")
            else:
                parts.extend(["--", "--"])
        
        print(" & ".join(parts) + r" \\")
    
    print(r"\hline")
    print(r"\end{tabular}")
    print(r"\end{table}")


def print_improvement_summary(results: List[Dict]):
    """Print percentage improvements of AHMN-Full over baselines."""
    grouped = group_results(results)
    
    print("\n" + "=" * 80)
    print("TABLE 3: AHMN-Full Improvement Over Baselines (% reduction in regret)")
    print("=" * 80)
    
    baselines = ["Random", "ε-Greedy", "UCB1", "TS (base)"]
    
    for scenario_name, scenario_data in grouped.items():
        if "AHMN-Full" not in scenario_data:
            continue
        
        ahmn_mean = np.mean([r["total_regret"] for r in scenario_data["AHMN-Full"]])
        
        print(f"\n  Scenario: {scenario_name}")
        for baseline in baselines:
            if baseline not in scenario_data:
                continue
            base_mean = np.mean([r["total_regret"] for r in scenario_data[baseline]])
            if base_mean > 0:
                improvement = ((base_mean - ahmn_mean) / base_mean) * 100
                print(f"    vs {baseline:<12s}: {improvement:+.1f}% regret reduction "
                      f"({base_mean:.1f} → {ahmn_mean:.1f})")


def main():
    # Try loading from output directory  
    search_paths = [
        os.path.join("output", "experiment_results.json"),
        os.path.join("ahmn_core", "output", "experiment_results.json"),
    ]
    
    data = None
    for p in search_paths:
        if os.path.exists(p):
            with open(p) as f:
                data = json.load(f)
            print(f"Loaded results from {p}")
            break
    
    if data is None:
        print("ERROR: No experiment_results.json found. Run experiments first:")
        print("  python -m experiments.run_experiments")
        sys.exit(1)
    
    results = data["main_results"]
    
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║              AHMN Experimental Analysis Report                  ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"\nConfig: {data['experiment_config']}")
    
    # Main tables
    print_main_comparison_table(results)
    print_statistical_tests(results)
    print_improvement_summary(results)
    
    # Ablation studies
    print("\n" + "=" * 80)
    print("ABLATION STUDIES")
    print("=" * 80)
    
    print_ablation_summary(data, "ablation_rabi_temperature", "Temperature τ")
    print_ablation_summary(data, "ablation_daaf_window", "Window Size")
    print_ablation_summary(data, "ablation_similarity_threshold", "Sim. Thresh.")
    
    # LaTeX
    print_latex_table(results)
    
    print("\n✓ Analysis complete.")


if __name__ == "__main__":
    main()
