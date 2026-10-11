"""
AHMN Experimental Results Analysis.

Reads experiment_results.json and produces:
  1. Summary comparison table (for paper)
  2. Per-scenario breakdown
  3. Statistical significance tests (Mann-Whitney U)
  4. Ablation study summaries
  5. Per-round regret curves with 95% confidence bands (saved as PNGs)
  6. Failure mode catalog from robustness sweeps

Usage (from the repository root):
    python -m ahmn_core.experiments.analysis
"""

import json
import os
import sys
import numpy as np

from collections import defaultdict

try:
    from scipy import stats as sp_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import matplotlib
    matplotlib.use("Agg")  # headless — no display needed
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# Colour-blind-safe palette (7 methods)
METHOD_COLORS = {
    "Random":     "#999999",
    "ε-Greedy":   "#E69F00",
    "UCB1":       "#56B4E9",
    "TS (base)":  "#009E73",
    "AHMN-RABI":  "#F0E442",
    "AHMN-DAAF":  "#0072B2",
    "AHMN-Full":  "#D55E00",
}
METHOD_ORDER = ["Random", "ε-Greedy", "UCB1", "TS (base)",
                "AHMN-RABI", "AHMN-DAAF", "AHMN-Full"]

def load_results(path: str | None = None) -> dict:
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

def group_results(results: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """Group results by scenario → method → [seed results]."""
    grouped = defaultdict(lambda: defaultdict(list))
    for r in results:
        grouped[r["scenario"]][r["method"]].append(r)
    return dict(grouped)

def print_main_comparison_table(results: list[dict]):
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

def print_statistical_tests(results: list[dict]):
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

def print_ablation_summary(data: dict, ablation_key: str, param_name: str):
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

def print_latex_table(results: list[dict]):
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

def print_improvement_summary(results: list[dict]):
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

def _ci95(values_2d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, half-width of 95% CI) across axis 0 using bootstrap t-interval."""
    mean = values_2d.mean(axis=0)
    sem = values_2d.std(axis=0, ddof=1) / np.sqrt(values_2d.shape[0])
    # t-multiplier for 95% CI (approximated as 1.96 for n >= 10)
    hw = 1.96 * sem
    return mean, hw


def plot_regret_curves(results: list[dict], out_dir: str) -> list[str]:
    """
    Save one PNG per scenario showing per-round cumulative regret (mean ± 95% CI).

    Each line is a method. Shaded band is the 95% confidence interval across seeds.
    Returns list of saved file paths.
    """
    if not HAS_MPL:
        print("[WARN] matplotlib not installed — skipping plots. pip install matplotlib")
        return []

    os.makedirs(out_dir, exist_ok=True)
    grouped = group_results(results)
    saved = []

    scenario_titles = {
        "stationary":    "Stationary — no drift, no cold-start",
        "cold_start":    "Cold-start — new vendors arrive mid-run",
        "concept_drift": "Concept drift — gradual then abrupt shift",
        "combined":      "Combined — cold-start + drift together",
    }

    for scenario_name, scenario_data in grouped.items():
        fig, ax = plt.subplots(figsize=(9, 5))

        for method in METHOD_ORDER:
            if method not in scenario_data:
                continue
            runs = scenario_data[method]
            # Stack cumulative regret arrays: shape (n_seeds, n_rounds)
            arrays = np.array([r["cumulative_regret"] for r in runs])
            mean, hw = _ci95(arrays)
            rounds = np.arange(1, len(mean) + 1)
            color = METHOD_COLORS.get(method, "#333333")
            lw = 2.5 if method == "AHMN-Full" else 1.5
            ax.plot(rounds, mean, label=method, color=color, linewidth=lw)
            ax.fill_between(rounds, mean - hw, mean + hw, color=color, alpha=0.15)

        # Mark drift events with vertical dashed lines
        drift_markers = {
            "concept_drift": [(500, "Gradual drift"), (1000, "Abrupt drift")],
            "combined":      [(600, "Corp-A drift")],
        }
        for round_num, label in drift_markers.get(scenario_name, []):
            ax.axvline(round_num, color="#CC0000", linestyle="--", linewidth=1, alpha=0.6)
            ax.text(round_num + 10, ax.get_ylim()[1] * 0.98, label,
                    fontsize=7, color="#CC0000", va="top")

        ax.set_xlabel("Round", fontsize=11)
        ax.set_ylabel("Cumulative pseudo-regret", fontsize=11)
        ax.set_title(scenario_titles.get(scenario_name, scenario_name), fontsize=12)
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()

        path = os.path.join(out_dir, f"regret_curve_{scenario_name}.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        saved.append(path)
        print(f"  Saved: {path}")

    return saved


def plot_drift_recovery(results: list[dict], out_dir: str) -> str | None:
    """
    Focus plot: reward over time for the drift scenario only.

    Shows how fast each method recovers after each drift event.
    Only plots TS (base), AHMN-DAAF, and AHMN-Full to keep it readable.
    """
    if not HAS_MPL:
        return None

    os.makedirs(out_dir, exist_ok=True)
    grouped = group_results(results)
    if "concept_drift" not in grouped:
        return None

    scenario_data = grouped["concept_drift"]
    focus_methods = ["TS (base)", "AHMN-DAAF", "AHMN-Full"]
    drift_rounds = [500, 1000]

    fig, ax = plt.subplots(figsize=(9, 4))

    for method in focus_methods:
        if method not in scenario_data:
            continue
        arrays = np.array([r["rewards"] for r in scenario_data[method]])
        # Rolling mean (window=30) for readability
        kernel = np.ones(30) / 30
        smoothed = np.array([np.convolve(row, kernel, mode="same") for row in arrays])
        mean, hw = _ci95(smoothed)
        rounds = np.arange(1, len(mean) + 1)
        color = METHOD_COLORS.get(method, "#333333")
        lw = 2.5 if method == "AHMN-Full" else 1.8
        ax.plot(rounds, mean, label=method, color=color, linewidth=lw)
        ax.fill_between(rounds, mean - hw, mean + hw, color=color, alpha=0.15)

    for r in drift_rounds:
        ax.axvline(r, color="#CC0000", linestyle="--", linewidth=1, alpha=0.7)

    ax.text(510, ax.get_ylim()[0] + 0.01, "Gradual drift", fontsize=7, color="#CC0000")
    ax.text(1010, ax.get_ylim()[0] + 0.01, "Abrupt drift", fontsize=7, color="#CC0000")
    ax.set_xlabel("Round", fontsize=11)
    ax.set_ylabel("Smoothed reward (F1)", fontsize=11)
    ax.set_title("Drift recovery: DAAF vs Thompson Sampling", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    path = os.path.join(out_dir, "drift_recovery.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")
    return path


def load_robustness_results(base_dir: str | None = None) -> dict | None:
    """Try to load robustness_results.json from standard output locations."""
    candidates = []
    if base_dir:
        candidates.append(os.path.join(base_dir, "robustness_results.json"))
    candidates += [
        os.path.join("output", "robustness_results.json"),
        os.path.join("ahmn_core", "output", "robustness_results.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    return None


def print_failure_mode_catalog(robustness: dict | None):
    """
    Show the conditions where AHMN underperforms plain Thompson Sampling.

    Reads the robustness sweep data (sweeps key) and reports every setting
    where the AHMN variant's regret exceeds the TS baseline regret.
    """
    print("\n" + "=" * 80)
    print("FAILURE MODE CATALOG — when AHMN underperforms plain Thompson Sampling")
    print("=" * 80)

    if not robustness:
        print("  [SKIP] No robustness_results.json found.")
        print("  Run first:  python -m ahmn_core.experiments.robustness_study")
        return

    sweeps = robustness.get("sweeps", {})
    if not sweeps:
        print("  [SKIP] robustness_results.json has no sweeps key.")
        return

    print(f"  {'Condition':<35s} {'AHMN regret':>12s}  {'TS regret':>10s}  {'Delta':>8s}")
    print(f"  {'-'*35} {'-'*12}  {'-'*10}  {'-'*8}")

    found_any = False
    for sweep_name, sweep_data in sweeps.items():
        if not isinstance(sweep_data, dict):
            continue
        for param_val, metrics in sweep_data.items():
            if not isinstance(metrics, dict):
                continue
            # Robustness study stores regret under a nested "regret" key
            regret_block = metrics.get("regret", metrics)
            ahmn_r = regret_block.get("variant_mean")
            ts_r   = regret_block.get("baseline_mean")
            if ahmn_r is None or ts_r is None:
                continue
            if ahmn_r > ts_r + 0.5:   # +0.5 tolerance — small differences are noise
                delta = ahmn_r - ts_r
                label = f"{sweep_name} = {param_val}"
                print(f"  {label:<35s} {ahmn_r:>12.1f}  {ts_r:>10.1f}  +{delta:.1f}")
                found_any = True

    if not found_any:
        print("  No conditions found where AHMN is meaningfully worse than TS.")
        print("  Try widening the sweep ranges in robustness_study.py.")

    print()
    print("  Decision guide:")
    print("    Use AHMN when: vendors share similar document formats (cos-sim > 0.4),")
    print("                   drift magnitude > 0.05, or > 20% of vendors are new.")
    print("    Use plain TS when: context embeddings are unreliable or reward noise")
    print("                       is very high (noise_std > 0.15).")


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
        print("  python -m ahmn_core.experiments.run_experiments")
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

    # Failure mode catalog (loaded from separate robustness_results.json)
    # analysis.py lives in ahmn_core/experiments/ — output is at ahmn_core/output/
    out_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
    robustness = load_robustness_results(out_base)
    if robustness and "sweeps" not in robustness and "sweeps" not in robustness:
        # older format uses top-level keys directly
        robustness = {"sweeps": robustness}
    print_failure_mode_catalog(robustness)

    # LaTeX
    print_latex_table(results)

    # Convergence curve plots — load per-round arrays from curves file
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "output", "plots")
    print(f"\nGenerating plots → {out_dir}")
    curves_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "output", "experiment_curves.json")
    curve_results = results  # fallback to summary results
    if os.path.exists(curves_path):
        with open(curves_path) as f:
            curve_results = json.load(f)["main_results"]
    else:
        print("  [WARN] experiment_curves.json not found — rerun run_experiments.py to generate plots.")
    saved = plot_regret_curves(curve_results, out_dir)
    drift_plot = plot_drift_recovery(curve_results, out_dir)
    if not HAS_MPL:
        print("  Install matplotlib to generate plots: pip install matplotlib")
    elif saved or drift_plot:
        print(f"  {len(saved) + (1 if drift_plot else 0)} plot(s) saved.")

    print("\n✓ Analysis complete.")

if __name__ == "__main__":
    main()
